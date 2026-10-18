"""Market trends via Gemini + Google Search grounding (contracts §9.4). Cached 60 min per (city, category)."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

from .. import config
from ..db import cache, log

TTL = 3600.0
TIMEOUT_S = 10.0


async def market_trends(city: str, category: str, timeout: float = TIMEOUT_S) -> dict:
    """{"insights": [str] (<= 3, <= 140 chars), "sources": [{"title", "url"}] (<= 4)}. Raises on failure/timeout."""
    key = ("trends", (city or "India").lower(), category)
    hit = cache.get(key)
    if hit is not None:
        return hit
    res = await asyncio.wait_for(_fetch(city, category), timeout)
    if res["insights"]:
        cache.set(key, res, TTL)
    return res


async def _fetch(city: str, category: str) -> dict:
    from google.genai import types

    from ..db import genai_client

    t0 = time.monotonic()
    label = config.CATEGORY_LABEL.get(category, category).lower()
    where = f"{city} and South India" if city else "South India"
    prompt = (
        f"Use Google Search. What {label} are shoppers buying for Diwali 2026 (festive season Oct-Nov 2026) in {where}: "
        f"trending colours, fabrics, styles and price points? Reply with exactly 3 bullet lines starting with '- ', "
        f"each under 130 characters, concrete and specific to retail buying. No intro, no outro."
    )
    r = await genai_client().aio.models.generate_content(
        model=config.MODEL_AGENT,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
            temperature=0.3,
        ),
    )
    text = r.text or ""
    insights = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        line = re.sub(r"\*\*|__", "", line)
        line = re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", line)  # citation markers
        if len(line) >= 15:
            insights.append(line if len(line) <= 140 else line[:137].rsplit(" ", 1)[0] + "...")
    sources = []
    try:
        gm = r.candidates[0].grounding_metadata
        for ch in (gm.grounding_chunks or []) if gm else []:
            web = getattr(ch, "web", None)
            if web and web.uri and all(s["url"] != web.uri for s in sources):
                sources.append({"title": (web.title or web.domain or "Source")[:80], "url": web.uri})
            if len(sources) >= 4:
                break
    except Exception:
        pass
    log("INFO", "trends fetched", latency_ms=int((time.monotonic() - t0) * 1000), insights=len(insights),
        sources=len(sources), category=category)
    return {"insights": insights[:3], "sources": sources}


def city_of(store_id: str) -> str:
    return (config.STORES.get(store_id) or {}).get("city") or ""


def evidence_for(product: Optional[dict], trends: dict) -> Optional[dict]:
    """A trend Evidence for a proposal: the insight mentioning the product's colour/fabric/style, else the first one."""
    insights = trends.get("insights") or []
    if not insights:
        return None
    pick = insights[0]
    if product:
        words = {w for f in (product.get("color"), product.get("material"), product.get("subcategory"))
                 for w in re.sub(r"[^a-z ]", " ", (f or "").lower()).split() if len(w) > 3}
        for ins in insights:
            if any(w in ins.lower() for w in words):
                pick = ins
                break
    src = (trends.get("sources") or [{}])[0]
    return {"kind": "trend", "text": pick[:140], "value": None, "url": src.get("url")}
