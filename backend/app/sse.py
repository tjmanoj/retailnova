"""Server-Sent Events helpers (contracts §5, SSE convention)."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi.responses import StreamingResponse

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

_DONE = object()


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class EventChannel:
    """A queue that producers push SSE events into and the response drains.

    Guarantees the stream ends with exactly one `done` event.
    """

    def __init__(self) -> None:
        self._q: asyncio.Queue = asyncio.Queue()
        self.closed = False
        self.done_sent = False

    def emit(self, event: str, data: Any) -> None:
        if self.closed:
            return
        if event == "done":
            if self.done_sent:
                return
            self.done_sent = True
        self._q.put_nowait(sse(event, data))

    def close(self) -> None:
        if not self.closed:
            self._q.put_nowait(_DONE)
            self.closed = True

    async def stream(self) -> AsyncIterator[str]:
        while True:
            item = await self._q.get()
            if item is _DONE:
                return
            yield item


def sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream", headers=SSE_HEADERS)
