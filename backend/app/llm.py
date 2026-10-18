"""Gemini helpers: resilient ADK model (primary -> fallback), JSON generation, embeddings.

Reliability policy:
- 429/503 are retried by the genai client with exponential backoff (2 retries).
- If the primary model has not produced its first chunk within a timeout, or fails,
  the call is re-issued on the fallback model (Flash-Lite).
- A small circuit breaker routes calls straight to the fallback for a short time
  after repeated primary failures, so a degraded endpoint does not slow every turn.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import time
from collections import OrderedDict, deque
from typing import Any, AsyncGenerator, Optional

from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from . import config
from .db import genai_client, log

DUMMY_SIGNATURE = b"skip_thought_signature_validator"
HEDGE_AFTER_S = float(__import__("os").getenv("HEDGE_AFTER_S", "2.5"))

# Per-turn state shared with the model wrapper (mutable dict inside a ContextVar).
turn_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar("turn_ctx", default=None)


class CircuitBreaker:
    """Opens when the primary lost >= `threshold` of its last `size` calls (within `window_s`)."""

    def __init__(self, window_s: float = 300, threshold: int = 2, size: int = 4, open_s: float = 180):
        self.outcomes: deque[tuple[float, bool]] = deque(maxlen=size)
        self.window = window_s
        self.threshold = threshold
        self.open_s = open_s
        self.open_until = 0.0

    def is_open(self) -> bool:
        return time.monotonic() < self.open_until

    def _record(self, ok: bool) -> None:
        now = time.monotonic()
        self.outcomes.append((now, ok))
        fails = sum(1 for t, o in self.outcomes if not o and now - t <= self.window)
        if fails >= self.threshold:
            self.open_until = now + self.open_s
            self.outcomes.clear()
            log("WARNING", "primary model circuit opened", open_s=self.open_s)

    def fail(self) -> None:
        self._record(False)

    def ok(self) -> None:
        self._record(True)


breaker = CircuitBreaker()


def _is_retryable(e: BaseException) -> bool:
    """Transient errors worth retrying before any output was produced."""
    import httpx

    if isinstance(e, (asyncio.TimeoutError, TimeoutError, httpx.TransportError)):
        return True
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    return code in (408, 429, 499, 500, 502, 503, 504)


def _prepare_for_fallback(llm_request: LlmRequest, fallback_model: str) -> None:
    llm_request.model = fallback_model
    cfg = llm_request.config
    if cfg is not None:
        cfg.thinking_config = None
    # Thought signatures are model specific; use the documented bypass value so
    # earlier function calls in the same turn are accepted by the fallback model.
    for c in llm_request.contents or []:
        new_parts = []
        for p in c.parts or []:
            if p.thought and not p.function_call:
                continue
            if p.function_call is not None:
                p.thought_signature = DUMMY_SIGNATURE
            elif p.thought_signature:
                p.thought_signature = None
            new_parts.append(p)
        c.parts = new_parts


async def _close(agen) -> None:
    try:
        await agen.aclose()
    except BaseException:
        pass


async def _cancel(task: asyncio.Task | None) -> None:
    if task and not task.done():
        task.cancel()
        try:
            await task
        except BaseException:
            pass


DIRECT_FIRST_CHUNK_TIMEOUT_S = 10.0


class ResilientGemini(Gemini):
    """ADK Gemini model with hedged requests and transient-error retries.

    - The primary model starts first. If it has not produced its first chunk after
      `hedge_after` seconds (or fails), the fallback model starts in parallel and the
      first one to respond wins.
    - Once the fallback is used in a turn, the rest of that turn stays on it
      (thought signatures are model specific).
    - Every path has a first-chunk timeout and retries transient transport errors
      (e.g. a stale keep-alive connection) with a fresh stream; nothing has been
      emitted to the user before the first chunk, so a retry is safe.
    """

    fallback_model: str = config.MODEL_LITE
    hedge_after: float = HEDGE_AFTER_S

    def _stream(self, req: LlmRequest, stream: bool):
        return Gemini.generate_content_async(self, req, stream)

    async def _first_chunk(self, req: LlmRequest, stream: bool, timeout: float, attempts: int = 3):
        last: BaseException | None = None
        for i in range(attempts):
            agen = self._stream(req, stream)
            try:
                first = await asyncio.wait_for(agen.__anext__(), timeout)
                return agen, first
            except StopAsyncIteration:
                return agen, None
            except Exception as e:
                await _close(agen)
                last = e
                if not _is_retryable(e) or i == attempts - 1:
                    raise
                log("WARNING", "model call retry", model=req.model, attempt=i + 1, error=type(e).__name__,
                    detail=str(e)[:160])
                await asyncio.sleep(0.25 * (i + 1))
        raise last or RuntimeError("model call failed")

    async def _direct(self, req: LlmRequest, stream: bool) -> AsyncGenerator[LlmResponse, None]:
        agen, first = await self._first_chunk(req, stream, DIRECT_FIRST_CHUNK_TIMEOUT_S)
        if first is None:
            return
        yield first
        async for r in agen:
            yield r

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        tctx = turn_ctx.get()
        models = tctx.setdefault("models", set()) if tctx is not None else set()
        primary = llm_request.model or self.model
        if breaker.is_open() or bool(tctx and tctx.get("fallback")):
            _prepare_for_fallback(llm_request, self.fallback_model)
            if tctx is not None:
                tctx["fallback"] = True
            models.add(self.fallback_model)
            async for r in self._direct(llm_request, stream):
                yield r
            return

        t0 = time.monotonic()
        fb_request = llm_request.model_copy(deep=True)
        _prepare_for_fallback(fb_request, self.fallback_model)
        p_gen = self._stream(llm_request, stream)
        p_task = asyncio.create_task(p_gen.__anext__())
        f_gen = None
        f_task = None
        winner = None
        first = None
        try:
            done, _ = await asyncio.wait({p_task}, timeout=self.hedge_after)
            if p_task in done and p_task.exception() is None:
                winner, first = "primary", p_task.result()
            else:
                if p_task in done:
                    log("WARNING", "primary model error; using fallback", model=primary,
                        error=type(p_task.exception()).__name__, detail=str(p_task.exception())[:200])
                f_gen = self._stream(fb_request, stream)
                f_task = asyncio.create_task(f_gen.__anext__())
                pending = {t for t in (p_task, f_task) if not t.done()}
                if f_task.done():
                    pending.add(f_task)
                deadline = time.monotonic() + DIRECT_FIRST_CHUNK_TIMEOUT_S
                while pending and winner is None:
                    done, pending = await asyncio.wait(pending, timeout=max(0.1, deadline - time.monotonic()),
                                                       return_when=asyncio.FIRST_COMPLETED)
                    if not done:
                        break
                    for t in (f_task, p_task):  # prefer the fallback on a tie
                        if t in done and t.exception() is None:
                            winner, first = ("fallback" if t is f_task else "primary"), t.result()
                            break
        except StopAsyncIteration:
            await _cancel(f_task)
            await _cancel(p_task)
            return
        except BaseException:
            await _cancel(f_task)
            await _cancel(p_task)
            if f_gen is not None:
                await _close(f_gen)
            await _close(p_gen)
            raise

        if winner == "primary":
            breaker.ok()
            models.add(primary)
            await _cancel(f_task)
            if f_gen is not None:
                await _close(f_gen)
            yield first
            async for r in p_gen:
                yield r
            return

        breaker.fail()
        if tctx is not None:
            tctx["fallback"] = True
        models.add(self.fallback_model)
        await _cancel(p_task)
        await _close(p_gen)
        if winner == "fallback":
            log("WARNING", "fallback model answered first", model=primary,
                waited_ms=int((time.monotonic() - t0) * 1000))
            yield first
            async for r in f_gen:
                yield r
            return
        # Neither answered in time (or both failed): fresh fallback stream with retries.
        await _cancel(f_task)
        if f_gen is not None:
            await _close(f_gen)
        log("WARNING", "hedged call failed; retrying fallback", model=primary,
            waited_ms=int((time.monotonic() - t0) * 1000))
        async for r in self._direct(fb_request, stream):
            yield r


def agent_model() -> ResilientGemini:
    return ResilientGemini(
        model=config.MODEL_AGENT,
        retry_options=types.HttpRetryOptions(
            attempts=3, initial_delay=0.6, max_delay=4, exp_base=2, http_status_codes=[429, 503]
        ),
    )


def low_thinking_config(**kw: Any) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="LOW"), **kw
    )


# ---------------------------------------------------------------------------
# Direct structured generation (planner, extractor)
# ---------------------------------------------------------------------------

async def generate_json(
    contents: Any,
    schema: Any,
    *,
    model: str,
    timeout: float,
    system_instruction: Optional[str] = None,
    thinking_low: bool = True,
    fallback: bool = True,
    temperature: float | None = None,
    hedge_after: float = 6.0,
) -> tuple[Any, str]:
    """Returns (parsed_json, model_used).

    Hedged: the primary starts first; if it has not answered after `hedge_after`
    seconds (or fails), Flash-Lite starts in parallel and the first valid answer wins.
    """
    client = genai_client()

    def cfg_for(m: str) -> types.GenerateContentConfig:
        cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            system_instruction=system_instruction,
            temperature=temperature,
        )
        if thinking_low and m != config.MODEL_LITE:
            cfg.thinking_config = types.ThinkingConfig(thinking_level="LOW")
        return cfg

    async def call(m: str):
        for i in range(2):
            try:
                r = await asyncio.wait_for(
                    client.aio.models.generate_content(model=m, contents=contents, config=cfg_for(m)), timeout)
                break
            except Exception as e:
                if i == 1 or not _is_retryable(e):
                    raise
                log("WARNING", "structured call retry", model=m, error=type(e).__name__)
                await asyncio.sleep(0.3)
        text = r.text or ""
        return json.loads(text) if text else None

    use_fb = fallback and model != config.MODEL_LITE
    if not use_fb or breaker.is_open():
        m = config.MODEL_LITE if (use_fb and breaker.is_open()) else model
        return await call(m), m

    tasks = {asyncio.create_task(call(model)): model}
    done, _ = await asyncio.wait(set(tasks), timeout=hedge_after)
    p_task = next(iter(tasks))
    if p_task in done and p_task.exception() is None:
        breaker.ok()
        return p_task.result(), model
    tasks[asyncio.create_task(call(config.MODEL_LITE))] = config.MODEL_LITE
    pending = {t for t in tasks if not t.done()}
    last_err: BaseException | None = p_task.exception() if p_task.done() else None
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if t.exception() is None:
                for o in pending:
                    o.cancel()
                m = tasks[t]
                if m == model:
                    breaker.ok()
                else:
                    breaker.fail()
                    log("WARNING", "structured generation answered by fallback", model=model)
                return t.result(), m
            last_err = t.exception()
            log("WARNING", "structured generation failed", model=tasks[t], error=type(last_err).__name__,
                detail=str(last_err)[:200])
    raise last_err or RuntimeError("generation failed")


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

_embed_cache: "OrderedDict[str, list[float]]" = OrderedDict()


async def embed_query(text: str) -> list[float]:
    key = text.strip().lower()[:500]
    if key in _embed_cache:
        _embed_cache.move_to_end(key)
        return _embed_cache[key]
    for i, t in enumerate((3.0, 4.0)):
        try:
            r = await asyncio.wait_for(
                genai_client().aio.models.embed_content(
                    model=config.MODEL_EMBED,
                    contents=text[:2000],
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=config.EMBED_DIM),
                ),
                t,
            )
            break
        except Exception as e:
            if i == 1 or not _is_retryable(e):
                raise
            log("WARNING", "embedding retry", error=type(e).__name__)
    vec = list(r.embeddings[0].values)
    _embed_cache[key] = vec
    if len(_embed_cache) > 512:
        _embed_cache.popitem(last=False)
    return vec


async def warm_up() -> None:
    """Warm the Gemini client + auth without blocking startup."""
    t0 = time.monotonic()
    try:
        await embed_query("maroon silk saree")
        await asyncio.wait_for(
            genai_client().aio.models.generate_content(model=config.MODEL_LITE, contents="ok"), 20
        )
        log("INFO", "gemini warm-up done", latency_ms=int((time.monotonic() - t0) * 1000))
    except Exception as e:
        log("WARNING", "gemini warm-up failed", error=type(e).__name__, detail=str(e)[:200])
