"""Store assist (§9.3): staff log a walk-in customer's request by text or voice -> DemandSignal."""
from __future__ import annotations

import time
from typing import Optional

from .. import config
from ..db import log
from ..limits import ApiError
from ..tools import catalog, inventory as inv
from ..turn import TurnState


async def run_assist(store_id: str, text: Optional[str], audio: Optional[bytes], audio_mime: Optional[str],
                     t0: Optional[float] = None) -> dict:
    t0 = t0 or time.monotonic()
    transcript = None
    language = None
    if audio:
        from ..voice import transcribe

        try:
            tr = await transcribe(audio, audio_mime)
        except Exception as e:
            log("WARNING", "assist transcription failed", error=type(e).__name__)
            tr = {"text": "", "language": "en"}
        transcript, language = tr["text"] or None, tr["language"]
    note = " ".join(x for x in [(text or "").strip(), transcript or ""] if x).strip()
    if not note:
        raise ApiError(400, "empty_request", "Please type or record what the customer asked for.")

    from .concierge import _guard_mod, _lang

    g = _guard_mod()
    if g:
        res = await g.screen(note)
        if res["verdict"] == "blocked":
            log("WARNING", "guardrail blocked assist", categories=res.get("categories"))
            return {"signal": None, "transcript": transcript,
                    "message": "This note can't be logged. Please describe what the customer asked for.",
                    "guardrail": {"provider": "model_armor", "verdict": "blocked", "categories": res.get("categories", [])}}

    # Candidate products with live stock at this store, for the extractor and the stock check.
    t = TurnState(session_id="", store_id=store_id, channel="store_assist")
    budget = _budget(note)
    results = await catalog.search(note, store_id, max_price_inr=int(budget * 1.15) if budget else None, k=6)
    if not results:
        results = await catalog.search(note, store_id, k=6)
    invs = await inv.inventory_for_skus([p["sku"] for p in results])
    items = [catalog.compact(p, invs.get(p["sku"], []), store_id, None) for p in results]
    t.see([p["sku"] for p in results])
    t.tool_log.append({"tool": "search_products", "args": {"query": note}, "results": items})
    if language:
        t.extra["language"] = language

    from .extractor import safe_extract, store_signal

    sig = await safe_extract(t, note)
    if sig:
        sig["session_id"] = None
        sig["channel"] = "store_assist"
        if language:
            sig["language"] = language
        sig = await store_signal(sig)
    ms = int((time.monotonic() - t0) * 1000)
    log("INFO", "assist", route="/api/assist", latency_ms=ms, store_id=store_id, voice=bool(audio),
        logged=bool(sig), outcome=(sig or {}).get("outcome"))
    return {"signal": sig, "transcript": transcript, "message": _message(sig, store_id, _lang(note))}


def _budget(text: str) -> Optional[int]:
    """'budget 5000', '₹8,000', 'under 3000', '5000 tak' -> rupees (500..200000), else None."""
    import re

    for m in re.finditer(r"(?:₹|rs\.?|inr|budget|under|upto|up to|about|around|below)\s*([0-9][0-9,]{2,7})|([0-9][0-9,]{2,7})\s*(?:tak|rupees|rs)",
                         text.lower()):
        v = int((m.group(1) or m.group(2)).replace(",", ""))
        if 500 <= v <= 200000:
            return v
    return None


def _message(sig: Optional[dict], store_id: str, lang: str) -> str:
    store = config.store_name(store_id)
    if not sig:
        return "Noted, but there was no clear product request to log. Add what the customer wanted (item, colour, size, budget)."
    what = (sig.get("summary") or config.CATEGORY_LABEL.get(sig["category"], sig["category"])).rstrip(". ")
    sku = f" ({sig['sku']})" if sig.get("sku") else ""
    extra = ""
    if sig["outcome"] == "fulfilled":
        extra = f" Marked fulfilled: {store} has it in stock."
    elif sig.get("reason") == "not_carried":
        extra = " Added to assortment gaps (we don't carry it)."
    elif (sig.get("attributes") or {}).get("stock_check"):
        extra = f" Note: the {sig['attributes']['stock_check']} at {store}; please check the shelf."
    return f"Logged{sku}: {what}.{extra} It now shows on the Demand Radar."
