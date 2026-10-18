"""Manager Q&A: ADK LlmAgent over the read-only ops tools, streamed as SSE."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncIterator, Optional

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

from .. import config
from ..db import BQUnavailable, log
from ..llm import agent_model, low_thinking_config, turn_ctx
from ..sse import EventChannel
from ..tools import catalog, ops

APP_NAME = "retailnova_manager"


def _store(s: Optional[str]) -> str:
    s = (s or "").strip().upper()
    return s if s in config.STORES else config.DEFAULT_STORE


def _cat(c: Optional[str]) -> Optional[str]:
    return catalog.normalize_category(c)


async def get_baseline_forecast(store_id: str, category: str, days: int = 21) -> dict:
    """BigQuery TimesFM forecast for a store and category: sales-only vs demand-sensed units over the next N days.

    Args:
      store_id: e.g. "CHN-TNG".
      category: sarees, kurta_sets, mens_ethnic, home_decor, gifting or footwear.
      days: horizon in days (default 21, i.e. until Diwali).
    """
    try:
        return await ops.forecast_summary(_store(store_id), _cat(category), max(1, min(days, 42)))
    except (BQUnavailable, asyncio.TimeoutError):
        return {"error": "forecast table not available yet"}


async def get_unmet_demand(store_id: str, category: Optional[str] = None, days: int = 7) -> dict:
    """Unmet demand captured from shopper conversations at a store over the last N days, grouped by SKU/attributes.

    Args:
      store_id: e.g. "CHN-TNG".
      category: optional category filter.
      days: look-back window (default 7).
    """
    u = await ops.unmet_groups(_store(store_id), _cat(category), max(1, min(days, 30)))
    return {"totals": u["totals"], "top_gaps": [{k: g[k] for k in ("category", "sku", "label", "attributes", "unmet_units_7d",
                                                                    "unmet_value_7d_inr", "trend", "top_reason")} for g in u["groups"][:8]]}


async def get_inventory_position(store_id: str, category: str) -> dict:
    """On-hand stock vs 21-day need for each SKU/size of a category at a store, with shortfalls.

    Args:
      store_id: e.g. "CHN-TNG".
      category: sarees, kurta_sets, mens_ethnic, home_decor, gifting or footwear.
    """
    sid, cat = _store(store_id), _cat(category) or "sarees"
    try:
        f = await ops.forecast_summary(sid, cat, 21)
    except Exception:
        f = None
    u = await ops.unmet_groups(sid, cat, 7)
    p = await ops.inventory_position(sid, cat, 21, f, u)
    return {"store_id": sid, "category": cat, "skus_out_of_stock": p["skus_out_of_stock"],
            "positions": [{k: x[k] for k in ("sku", "size", "name", "price_inr", "on_hand", "incoming", "need_21d", "shortfall")}
                          for x in p["positions"][:10]]}


async def get_transfer_options(store_id: str, category: str, sku: Optional[str] = None) -> dict:
    """Other stores' surplus stock (above their reorder point) that could be transferred to this store.

    Args:
      store_id: destination store, e.g. "CHN-TNG".
      category: category to check.
      sku: optional SKU filter.
    """
    t = await ops.transfer_options(_store(store_id), _cat(category) or "sarees", [sku.upper()] if sku else None)
    return {**t, "options": t["options"][:10]}


INSTRUCTION = """You are Nova Ops, an analyst for store managers at Nova Bazaar (Indian festive retail).
Today is 2026-10-18; Diwali is 2026-11-08 (21 days away). Answer the manager's question using the tools; never invent
numbers. Unmet demand = shoppers who asked but could not buy at that store (captured from conversations).
The demand-sensed forecast adds captured unmet demand to sales; sales-only forecasts under-predict items that sold out.
Answer in 3-6 short sentences or bullets with concrete numbers, SKUs and store names, and end with one recommended next
step (for example: "Generate an action plan" for transfers and reorders). Refuse unrelated requests politely."""


def _instruction(ctx: ReadonlyContext) -> str:
    sid = ctx.state.get("store_id", config.DEFAULT_STORE)
    return INSTRUCTION + f"\nThe manager's store is {config.store_name(sid)} ({sid})."


_runner: InMemoryRunner | None = None


def runner() -> InMemoryRunner:
    global _runner
    if _runner is None:
        agent = LlmAgent(
            name="manager_qa",
            model=agent_model(),
            instruction=_instruction,
            tools=[get_baseline_forecast, get_unmet_demand, get_inventory_position, get_transfer_options],
            generate_content_config=low_thinking_config(temperature=0.3),
        )
        _runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    return _runner


LABELS = {
    "get_baseline_forecast": "Reading the BigQuery forecast",
    "get_unmet_demand": "Aggregating unmet demand",
    "get_inventory_position": "Checking inventory position",
    "get_transfer_options": "Looking for surplus at other stores",
}


def run_ask(store_id: str, question: str, session_id: Optional[str], t0: Optional[float] = None) -> AsyncIterator[str]:
    ch = EventChannel()
    ch.emit("activity", {"id": "a0", "tool": "understand", "label": "Reading your question", "status": "start"})
    asyncio.create_task(_produce(ch, store_id, question, session_id, t0))
    return ch.stream()


async def _produce(ch: EventChannel, store_id: str, question: str, session_id: Optional[str],
                   t0: Optional[float] = None) -> None:
    t0 = t0 or time.monotonic()
    sid = f"mgr_{session_id or uuid.uuid4().hex}"
    tctx = {"fallback": False, "models": set()}
    turn_ctx.set(tctx)
    status = "ok"
    any_text = False
    guardrail = None
    try:
        from .. import guard

        if guard.ENABLED:
            g = await guard.screen(question)
            if g["verdict"] == "blocked":
                guardrail = guard.guardrail(g)
                ch.emit("activity", {"id": "a0", "tool": "understand", "label": "Reading your question", "status": "end"})
                ch.emit("text", {"delta": "I can only help with store operations: demand, forecasts, inventory and actions. "
                                          "Try asking about unmet demand or a Diwali action plan."})
                latency = int((time.monotonic() - t0) * 1000)
                ch.emit("done", {"latency_ms": latency, "model": config.MODEL_AGENT, "session_id": session_id,
                                 "guardrail": guardrail})
                ch.close()
                log("WARNING", "guardrail blocked ask", categories=g.get("categories"), latency_ms=latency)
                return
            if g["verdict"] == "allowed":
                guardrail = guard.guardrail(g)
    except Exception as e:
        log("WARNING", "ask guard failed", error=type(e).__name__)
    try:
        r = runner()
        if await r.session_service.get_session(app_name=APP_NAME, user_id=sid, session_id=sid) is None:
            await r.session_service.create_session(app_name=APP_NAME, user_id=sid, session_id=sid)
        first = True
        partial_seen = False

        async def consume():
            nonlocal first, partial_seen, any_text
            async for ev in r.run_async(user_id=sid, session_id=sid,
                                        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
                                        state_delta={"store_id": store_id},
                                        run_config=RunConfig(streaming_mode=StreamingMode.SSE)):
                if first:
                    first = False
                    ch.emit("activity", {"id": "a0", "tool": "understand", "label": "Reading your question", "status": "end"})
                if not ev.content or not ev.content.parts:
                    continue
                if ev.partial:
                    delta = "".join(p.text for p in ev.content.parts if p.text and not p.thought)
                    if delta:
                        partial_seen = True
                        any_text = True
                        ch.emit("text", {"delta": delta})
                    continue
                if not partial_seen:
                    full = "".join(p.text for p in ev.content.parts if p.text and not p.thought)
                    if full:
                        any_text = True
                        ch.emit("text", {"delta": full})
                for fc in ev.get_function_calls():
                    ch.emit("activity", {"id": fc.id or fc.name, "tool": fc.name, "label": LABELS.get(fc.name, "Working on it"), "status": "start"})
                for fr in ev.get_function_responses():
                    ch.emit("activity", {"id": fr.id or fr.name, "tool": fr.name, "label": LABELS.get(fr.name, "Working on it"), "status": "end"})
                partial_seen = False

        await asyncio.wait_for(consume(), timeout=config.CHAT_TURN_TIMEOUT_S)
        if not any_text:
            ch.emit("text", {"delta": "I couldn't find enough data to answer that. Try asking about unmet demand, forecasts or transfers."})
    except asyncio.TimeoutError:
        status = "timeout"
        ch.emit("error", {"message": "Sorry, that took too long. Please try again.", "retryable": True})
    except Exception as e:
        status = "error"
        log("ERROR", "ask failed", error=type(e).__name__, detail=str(e)[:300])
        ch.emit("error", {"message": "Sorry, something went wrong. Please try again.", "retryable": True})
    models = tctx.get("models") or set()
    model = config.MODEL_LITE if (tctx.get("fallback") and len(models) == 1) else config.MODEL_AGENT
    latency = int((time.monotonic() - t0) * 1000)
    done = {"latency_ms": latency, "model": model, "session_id": session_id}
    if guardrail:
        done["guardrail"] = guardrail
    ch.emit("done", done)
    ch.close()
    log("INFO", "ask", route="/api/ask", latency_ms=latency, status=status, model=model)
