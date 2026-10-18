"""Input size and per-session rate limits (contracts §5, Limits)."""
from __future__ import annotations

import base64
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from . import config


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


class RateLimiter:
    def __init__(self, limit: int, window_s: int):
        self.limit = limit
        self.window = window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise ApiError(
                429,
                "rate_limited",
                "You're going a little fast. Please wait a few minutes and try again.",
            )
        q.append(now)
        if len(self.hits) > 20000:  # bound memory
            for k in list(self.hits.keys())[:5000]:
                if not self.hits[k]:
                    del self.hits[k]

    def reset(self) -> None:
        self.hits.clear()


chat_limiter = RateLimiter(*config.CHAT_RATE)
plan_limiter = RateLimiter(*config.PLAN_RATE)


def check_message(message: str) -> None:
    if len(message or "") > config.MAX_MESSAGE_CHARS:
        raise ApiError(
            413,
            "message_too_long",
            f"That message is a bit long. Please keep it under {config.MAX_MESSAGE_CHARS} characters.",
        )


def decode_image(image_b64: str | None) -> bytes | None:
    if not image_b64:
        return None
    s = image_b64
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    # base64 inflates by 4/3; reject early before decoding very large payloads
    if len(s) * 3 // 4 > config.MAX_IMAGE_BYTES + 16:
        raise ApiError(413, "image_too_large", "That photo is too large. Please use an image under 1.5 MB.")
    try:
        raw = base64.b64decode(s, validate=False)
    except Exception:
        raise ApiError(400, "bad_image", "We couldn't read that image. Please try a JPEG, PNG or WebP photo.")
    if len(raw) > config.MAX_IMAGE_BYTES:
        raise ApiError(413, "image_too_large", "That photo is too large. Please use an image under 1.5 MB.")
    return raw
