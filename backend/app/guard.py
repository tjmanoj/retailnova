"""Model Armor screening of user text (contracts §9.5).

`screen(text)` calls `sanitizeUserPrompt` on the RetailNova template and returns
{"verdict": "allowed"|"blocked"|"error", "categories": [str], "latency_ms": int}.
It fails open: any error or timeout returns verdict "error" (logged), and callers continue.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional

from .db import log

ENABLED = os.getenv("ENABLE_MODEL_ARMOR", "true").strip().lower() in ("1", "true", "yes", "on")
TEMPLATE = os.getenv(
    "MODEL_ARMOR_TEMPLATE",
    "projects/retailnova-ai/locations/asia-south1/templates/retailnova-shield",
)
MAX_CHARS = 2000

_creds = None
_token_lock: Optional[asyncio.Lock] = None
_client = None
_client_loop = None


def _endpoint() -> str:
    # projects/{p}/locations/{loc}/templates/{id} -> regional endpoint
    loc = TEMPLATE.split("/locations/")[1].split("/")[0]
    return f"https://modelarmor.{loc}.rep.googleapis.com/v1/{TEMPLATE}:sanitizeUserPrompt"


async def _token() -> str:
    global _creds, _token_lock
    if _token_lock is None:
        _token_lock = asyncio.Lock()
    async with _token_lock:
        if _creds is None:
            import google.auth

            _creds, _ = await asyncio.to_thread(
                google.auth.default, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        expiry = getattr(_creds, "expiry", None)  # naive datetime in UTC
        if expiry is not None:
            from datetime import timezone

            expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
        stale = not _creds.token or not _creds.valid or (expiry is not None and expiry.timestamp() - time.time() < 120)
        if stale:
            from google.auth.transport.requests import Request

            await asyncio.to_thread(_creds.refresh, Request())
        return _creds.token


def _http():
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        import httpx

        _client = httpx.AsyncClient(timeout=5.0, limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=60))
        _client_loop = loop
    return _client


_SHORT = {
    "pi_and_jailbreak": "prompt_injection",
    "malicious_uris": "malicious_uri",
    "csam": "csam",
    "sdp": "sensitive_data",
}


def _categories(result: dict) -> list[str]:
    cats: list[str] = []
    for key, wrapper in (result.get("filterResults") or {}).items():
        if not isinstance(wrapper, dict):
            continue
        for inner in wrapper.values():  # e.g. {"piAndJailbreakFilterResult": {...}}
            if not isinstance(inner, dict):
                continue
            if key == "rai":
                for rtype, r in (inner.get("raiFilterTypeResults") or {}).items():
                    if (r or {}).get("matchState") == "MATCH_FOUND":
                        cats.append(f"rai:{rtype}")
            elif inner.get("matchState") == "MATCH_FOUND":
                cats.append(_SHORT.get(key, key))
    return cats


async def screen(text: str, timeout: float = 0.8) -> dict[str, Any]:
    """Screen one user prompt. Never raises; fails open with verdict "error"."""
    t0 = time.monotonic()
    if not ENABLED or not (text or "").strip():
        return {"verdict": "allowed", "categories": [], "latency_ms": 0, "skipped": True}
    try:
        async def call() -> dict:
            tok = await _token()
            r = await _http().post(
                _endpoint(),
                headers={"Authorization": f"Bearer {tok}"},
                json={"userPromptData": {"text": text[:MAX_CHARS]}},
            )
            r.raise_for_status()
            return r.json()

        data = await asyncio.wait_for(call(), timeout)
        res = data.get("sanitizationResult") or {}
        ms = int((time.monotonic() - t0) * 1000)
        if res.get("filterMatchState") == "MATCH_FOUND":
            cats = _categories(res)
            log("INFO", "model armor blocked", categories=cats, latency_ms=ms)
            return {"verdict": "blocked", "categories": cats, "latency_ms": ms}
        if res.get("invocationResult") not in (None, "SUCCESS"):
            log("WARNING", "model armor partial result; allowing", invocation=res.get("invocationResult"), latency_ms=ms)
            return {"verdict": "error", "categories": [], "latency_ms": ms}
        return {"verdict": "allowed", "categories": [], "latency_ms": ms}
    except Exception as e:  # fail open
        ms = int((time.monotonic() - t0) * 1000)
        log("WARNING", "model armor unavailable; failing open", error=type(e).__name__, detail=str(e)[:160], latency_ms=ms)
        return {"verdict": "error", "categories": [], "latency_ms": ms}


async def warm() -> None:
    """Fetch credentials and open the connection at startup (the first call costs ~0.8 s)."""
    if ENABLED:
        r = await screen("warm up", timeout=6.0)
        log("INFO", "model armor warm-up", verdict=r["verdict"], latency_ms=r["latency_ms"])


def guardrail(result: dict) -> dict:
    """The `done.guardrail` payload (contracts §9.5)."""
    out = {"provider": "model_armor", "verdict": "blocked" if result.get("verdict") == "blocked" else "allowed"}
    if result.get("verdict") == "blocked":
        out["categories"] = result.get("categories") or []
    return out


_REFUSALS = {
    "en": "Sorry, I can't help with that. I'm Nova, your festive shopping assistant: ask me about sarees, kurtas, "
          "gifts or Diwali decor and I'll find options in stock near you.",
    "hinglish": "Maaf kijiye, main isme madad nahi kar sakti. Main Nova hoon, aapki festive shopping assistant: sarees, "
                "kurtas, gifts ya Diwali decor ke baare mein poochiye, main aapke store mein options dhoond doongi.",
    "tanglish": "Mannikkavum, idhula naan udhava mudiyaadhu. Naan Nova, ungal festive shopping assistant: sarees, "
                "kurtas, gifts illa Diwali decor pathi kelunga, ungal kadai-la irukkura options kaatturen.",
    "ta": "மன்னிக்கவும், இதில் என்னால் உதவ முடியாது. நான் நோவா, உங்கள் பண்டிகை ஷாப்பிங் உதவியாளர்: புடவைகள், "
          "குர்தாக்கள், பரிசுகள் அல்லது தீபாவளி அலங்காரம் பற்றி கேளுங்கள்.",
}


def refusal(lang: str) -> str:
    """Short, polite, localised refusal that steers back to festive shopping (en / hinglish / tanglish / ta)."""
    return _REFUSALS.get((lang or "en").lower(), _REFUSALS["en"])
