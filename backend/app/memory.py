"""Shopper preference memory ("Nova remembers you"), keyed by session_id (contracts §9.6).

Backends (same API):
- "memory_bank": Agent Platform Memory Bank (asia-south1). Facts are generated asynchronously from the
  shopper's message, scoped to {app_name: "retailnova", user_id: session_id}, and retrieved with a fast
  similarity search. The bank is configured (scripts/memory_engine.py) to keep shopping preferences only.
- "firestore": profiles/{session_id}, preferences extracted by Flash-Lite and merged.

Only shopping preferences are stored: colours, fabrics, sizes, budget, occasions, categories, store.
Names, phone numbers, e-mails and addresses are scrubbed before anything leaves the request.

Env:
  MEMORY_BACKEND = memory_bank | firestore | off   (default: memory_bank when MEMORY_ENGINE is usable)
  MEMORY_ENGINE  = projects/.../locations/<loc>/reasoningEngines/<id>   (from scripts/memory_engine.py)
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from . import config
from .db import fs, log, now_iso

APP_SCOPE = "retailnova"
DEFAULT_ENGINE = "projects/569310655517/locations/asia-south1/reasoningEngines/5431525868562284544"
MEMORY_ENGINE = os.getenv("MEMORY_ENGINE", DEFAULT_ENGINE).strip()


def _resolve_backend() -> Optional[str]:
    want = os.getenv("MEMORY_BACKEND", "").strip().lower()
    if want in ("off", "none", "false", "0", "disabled"):
        return None
    if want == "firestore":
        return "firestore"
    bank_ok = bool(MEMORY_ENGINE) and "/reasoningEngines/" in MEMORY_ENGINE and \
        importlib.util.find_spec("agentplatform") is not None
    return "memory_bank" if bank_ok else "firestore"


BACKEND: Optional[str] = _resolve_backend()

# ---------------------------------------------------------------------------
# Text helpers: preference cues, personal-data scrub, fact -> key/value
# ---------------------------------------------------------------------------

COLOURS = ["maroon", "red", "pink", "rani pink", "magenta", "peach", "orange", "mustard", "yellow", "gold", "golden",
           "silver", "green", "mint", "teal", "emerald", "bottle green", "blue", "royal blue", "navy", "sky blue",
           "turquoise", "purple", "lavender", "violet", "wine", "black", "white", "ivory", "cream", "beige",
           "brown", "rust", "copper", "grey", "gray", "off white", "multicolour", "multicolor", "pastel"]
FABRICS = ["silk", "pattu", "cotton", "georgette", "chiffon", "linen", "organza", "chanderi", "banarasi",
           "kanchipuram", "velvet", "rayon", "crepe", "satin", "khadi", "brocade", "tussar", "handloom", "zari",
           "net", "leather", "brass", "silk blend"]
OCCASIONS = ["wedding", "diwali", "deepavali", "puja", "pooja", "festive", "festival", "party", "office",
             "engagement", "reception", "sangeet", "haldi", "mehendi", "navratri", "pongal", "onam", "birthday",
             "anniversary", "housewarming", "gifting", "gift", "casual", "temple"]
CATEGORIES = {"saree": "sarees", "sari": "sarees", "pudavai": "sarees", "kurta set": "kurta_sets",
              "anarkali": "kurta_sets", "kurta": "kurta", "sherwani": "mens_ethnic", "dhoti": "mens_ethnic",
              "veshti": "mens_ethnic", "jutti": "footwear", "juttis": "footwear", "mojari": "footwear",
              "sandal": "footwear", "footwear": "footwear", "diya": "home_decor", "decor": "home_decor",
              "hamper": "gifting", "gift": "gifting"}

_CUE_WORDS = (["love", "like", "likes", "prefer", "prefers", "favourite", "favorite", "usually", "always", "never",
               "budget", "size", "tak", "under", "around", "upto", "pasand", "pidikkum", "pidikum", "wear",
               "my style", "allergic", "avoid"] + COLOURS + FABRICS + OCCASIONS)
_CUE_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(set(_CUE_WORDS), key=len, reverse=True)) + r")\b"
                     r"|₹\s*\d|\brs\.?\s*\d|\b\d{3,6}\b", re.I)


def has_preference_cue(text: str) -> bool:
    return bool(text) and bool(_CUE_RE.search(text))


_PHONE_RE = re.compile(r"\+?\d(?:[\s-]?\d){8,}")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_NAME_RE = re.compile(r"\b(my name is|i am called|call me|mera naam|en peyar|en per)\s+[A-Za-z]+(\s+[A-Z][a-z]+)?", re.I)
_ADDR_RE = re.compile(r"\b(my address is|i live at|address:)[^.!?\n]*", re.I)


def scrub(text: str) -> str:
    t = _PHONE_RE.sub("[number removed]", text or "")
    t = _EMAIL_RE.sub("[email removed]", t)
    t = _ADDR_RE.sub("", t)
    t = _NAME_RE.sub("", t)
    return t.strip()[:1000]


def _find_all(words: list[str], text: str) -> list[str]:
    low = text.lower()
    out = []
    for w in sorted(words, key=len, reverse=True):
        if re.search(rf"\b{re.escape(w)}\b", low) and not any(w in o for o in out):
            out.append(w)
    return out


_BUDGET_RE = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]{3,7})|([\d,]{3,7})\s*(?:rupees|rs\b|inr|₹)|"
                        r"budget[^\d]{0,25}([\d,]{3,7})|(?:under|around|upto|up to|below|within|tak)\s*([\d,]{3,7})"
                        r"|([\d,]{3,7})\s*(?:tak|ke andar|kulla|budget)", re.I)
_SIZE_RE = re.compile(r"\bsize\b[^.;\n]{0,25}?\b(xxl|xl|l|m|s|free|\d{1,2})\b|\b(xxl|xl)\b", re.I)


def preferences_from_text(text: str) -> list[dict]:
    """Heuristic key/value preferences from natural-language facts."""
    prefs: list[dict] = []
    seen = set()

    def add(k: str, v: str) -> None:
        if (k, v) not in seen:
            seen.add((k, v))
            prefs.append({"key": k, "value": v})

    for c in _find_all(COLOURS, text):
        add("colour", c)
    for f in _find_all(FABRICS, text):
        add("fabric", f)
    for o in _find_all(OCCASIONS, text):
        add("occasion", "diwali" if o == "deepavali" else o)
    for word, cat in CATEGORIES.items():
        if re.search(rf"\b{re.escape(word)}s?\b", text.lower()):
            add("category", cat)
    for m in _BUDGET_RE.finditer(text):
        num = next((g for g in m.groups() if g), "").replace(",", "")
        if num.isdigit() and 300 <= int(num) <= 500000:
            add("budget_inr", num)
            break
    for m in _SIZE_RE.finditer(text):
        s = (m.group(1) or m.group(2) or "").upper()
        if s:
            add("size", s)
    for sid, st in config.STORES.items():
        if st["type"] == "store" and st["name"].lower().replace(".", "") in text.lower().replace(".", ""):
            add("store", sid)
    return prefs


def summarize(prefs: list[dict], facts: Optional[list[str]] = None) -> str:
    by: dict[str, list[str]] = {}
    for p in prefs:
        by.setdefault(p["key"], []).append(p["value"])
    parts = []
    if by.get("colour"):
        parts.append("likes " + ", ".join(by["colour"]))
    if by.get("fabric"):
        parts.append("prefers " + ", ".join(by["fabric"]))
    if by.get("budget_inr"):
        parts.append(f"budget around ₹{int(by['budget_inr'][-1]):,}")
    if by.get("size"):
        parts.append("size " + "/".join(by["size"]))
    if by.get("occasion"):
        parts.append("shops for " + ", ".join(by["occasion"]))
    if by.get("store"):
        parts.append("usually shops at " + ", ".join(config.store_name(s) for s in by["store"]))
    if parts:
        s = "; ".join(parts)
        return s[0].upper() + s[1:] + "."
    return " ".join((facts or [])[:3])[:240]


# ---------------------------------------------------------------------------
# Memory Bank backend
# ---------------------------------------------------------------------------

_clients: dict[int, Any] = {}


def _mb_client():
    loop = asyncio.get_running_loop()
    c = _clients.get(id(loop))
    if c is None:
        import agentplatform

        loc = MEMORY_ENGINE.split("/locations/")[1].split("/")[0]
        c = agentplatform.Client(project=config.PROJECT, location=loc).aio
        _clients.clear()
        _clients[id(loop)] = c
    return c


def _scope(session_id: str) -> dict[str, str]:
    return {"app_name": APP_SCOPE, "user_id": session_id}


async def _mb_facts(session_id: str, query: str = "") -> list[tuple[str, Optional[datetime], str]]:
    c = _mb_client()
    if query:
        pager = await c.memory_banks.memories.retrieve(
            name=MEMORY_ENGINE, scope=_scope(session_id),
            similarity_search_params={"search_query": query[:300], "top_k": 8})
    else:
        pager = await c.memory_banks.memories.retrieve(
            name=MEMORY_ENGINE, scope=_scope(session_id), simple_retrieval_params={"page_size": 20})
    out = []
    async for r in pager:
        m = getattr(r, "memory", None)
        if m is not None and getattr(m, "fact", None):
            out.append((m.fact, getattr(m, "update_time", None), getattr(m, "name", "")))
        if len(out) >= 20:
            break
    return out


async def _mb_remember(session_id: str, text: str) -> None:
    from google.genai import types as gt

    c = _mb_client()
    await c.memory_banks.memories.generate(
        name=MEMORY_ENGINE,
        direct_contents_source={"events": [{"content": gt.Content(role="user", parts=[gt.Part(text=text)])}]},
        scope=_scope(session_id),
        config={"wait_for_completion": False},
    )


async def _mb_forget(session_id: str) -> int:
    c = _mb_client()
    facts = await _mb_facts(session_id)
    names = [n for _, _, n in facts if n]
    await asyncio.gather(*[c.memory_banks.memories.delete(name=n) for n in names], return_exceptions=True)
    return len(names)


# ---------------------------------------------------------------------------
# Firestore backend
# ---------------------------------------------------------------------------

_FS_SYSTEM = """Extract only lasting, explicitly stated shopping preferences from the shopper's message for an
Indian festive fashion, decor and gifting store: colours, fabrics/materials, sizes, budget in rupees, occasions,
product categories and preferred store. Ignore one-off product questions without a stated preference.
Return empty lists / null when nothing is stated. Never extract names, phone numbers, e-mails or addresses."""


async def _fs_extract(text: str) -> list[dict]:
    from pydantic import BaseModel

    from .llm import generate_json

    class PrefDraft(BaseModel):
        colours: list[str] = []
        fabrics: list[str] = []
        sizes: list[str] = []
        budget_max_inr: Optional[int] = None
        occasions: list[str] = []
        categories: list[str] = []
        preferred_store: Optional[str] = None

    d, _ = await generate_json(f"Shopper message: {text}", PrefDraft, model=config.MODEL_LITE, timeout=8,
                               system_instruction=_FS_SYSTEM, thinking_low=False, fallback=False, temperature=0.0)
    d = d or {}
    prefs = []
    for key, field in (("colour", "colours"), ("fabric", "fabrics"), ("size", "sizes"), ("occasion", "occasions"),
                       ("category", "categories")):
        for v in (d.get(field) or [])[:5]:
            if isinstance(v, str) and 0 < len(v) <= 40:
                prefs.append({"key": key, "value": v.strip().lower() if key != "size" else v.strip().upper()})
    if d.get("budget_max_inr") and 300 <= int(d["budget_max_inr"]) <= 500000:
        prefs.append({"key": "budget_inr", "value": str(int(d["budget_max_inr"]))})
    st = (d.get("preferred_store") or "").strip()
    if st:
        sid = next((s for s, v in config.STORES.items() if st.upper() == s or st.lower() in v["name"].lower()), None)
        if sid:
            prefs.append({"key": "store", "value": sid})
    return prefs


def _merge(old: list[dict], new: list[dict]) -> list[dict]:
    single = {"budget_inr", "store"}
    out = [p for p in old if not (p["key"] in single and any(n["key"] == p["key"] for n in new))]
    for n in new:
        if n not in out:
            out.append(n)
    by: dict[str, list[dict]] = {}
    for p in out:
        by.setdefault(p["key"], []).append(p)
    return [p for k in by for p in by[k][-5:]]


async def _fs_get(session_id: str) -> dict:
    snap = await fs().collection("profiles").document(session_id).get()
    return snap.to_dict() if snap.exists else {}


async def _fs_remember(session_id: str, text: str) -> None:
    new = await _fs_extract(text)
    if not new:
        return
    old = (await _fs_get(session_id)).get("preferences") or []
    prefs = _merge(old, new)
    await fs().collection("profiles").document(session_id).set({
        "session_id": session_id, "summary": summarize(prefs), "preferences": prefs,
        "source": "firestore", "updated_at": now_iso(),
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def recall(session_id: str, query: str = "", timeout: float = 1.5) -> Optional[dict]:
    """Remembered preferences for this shopper, or None. Never raises; bounded by `timeout`."""
    if not BACKEND or not session_id:
        return None

    async def _run() -> Optional[dict]:
        if BACKEND == "memory_bank":
            facts = await _mb_facts(session_id, query or "shopping preferences: colours, fabrics, budget, size")
            if not facts:
                return None
            texts = [f for f, _, _ in facts]
            prefs = preferences_from_text(" ".join(texts))
            return {"summary": summarize(prefs, texts), "preferences": prefs, "facts": texts}
        doc = await _fs_get(session_id)
        if not doc.get("preferences"):
            return None
        return {"summary": doc.get("summary") or summarize(doc["preferences"]), "preferences": doc["preferences"]}

    try:
        return await asyncio.wait_for(_run(), timeout)
    except asyncio.TimeoutError:
        log("WARNING", "memory recall timed out", backend=BACKEND, timeout_s=timeout)
    except Exception as e:
        log("WARNING", "memory recall failed", backend=BACKEND, error=type(e).__name__, detail=str(e)[:160])
    return None


_pending: dict[str, set[asyncio.Task]] = {}


def remember_async(session_id: str, user_message: str, assistant_reply: str = "") -> None:
    """Fire-and-forget: store preferences stated in this turn. Never raises.

    Only the shopper's own words are sent (the assistant's suggestions are not the shopper's preferences),
    after scrubbing personal data, and only when the message contains a preference cue.
    """
    if not BACKEND or not session_id or not has_preference_cue(user_message or ""):
        return
    text = scrub(user_message)
    if not text:
        return

    async def _run() -> None:
        try:
            if BACKEND == "memory_bank":
                await asyncio.wait_for(_mb_remember(session_id, text), 20)
            else:
                await asyncio.wait_for(_fs_remember(session_id, text), 20)
        except Exception as e:
            log("WARNING", "memory write failed", backend=BACKEND, error=type(e).__name__, detail=str(e)[:160])

    try:
        task = asyncio.get_running_loop().create_task(_run())
        tasks = _pending.setdefault(session_id, set())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    except RuntimeError:
        pass  # no running loop


async def get_profile(session_id: str) -> dict:
    """GET /api/profile payload: {session_id, summary, preferences, source, updated_at}."""
    empty = {"session_id": session_id, "summary": "", "preferences": [], "source": BACKEND, "updated_at": None}
    if not BACKEND or not session_id:
        return empty
    try:
        if BACKEND == "memory_bank":
            facts = await asyncio.wait_for(_mb_facts(session_id), 5)
            if not facts:
                return empty
            texts = [f for f, _, _ in facts]
            prefs = preferences_from_text(" ".join(texts))
            updated = max((u for _, u, _ in facts if u), default=None)
            return {"session_id": session_id, "summary": summarize(prefs, texts), "preferences": prefs,
                    "source": "memory_bank", "updated_at": _iso(updated)}
        doc = await asyncio.wait_for(_fs_get(session_id), 5)
        if not doc:
            return empty
        return {"session_id": session_id, "summary": doc.get("summary", ""), "preferences": doc.get("preferences", []),
                "source": "firestore", "updated_at": doc.get("updated_at")}
    except Exception as e:
        log("WARNING", "profile read failed", backend=BACKEND, error=type(e).__name__, detail=str(e)[:160])
        return empty


async def forget(session_id: str) -> dict:
    """Delete this shopper's memories (Memory Bank and Firestore). Returns {"forgotten": True}."""
    if session_id:
        for t in list(_pending.pop(session_id, set())):
            t.cancel()
        if BACKEND == "memory_bank":
            try:
                n = await asyncio.wait_for(_mb_forget(session_id), 10)
                log("INFO", "memories forgotten", backend="memory_bank", n=n)
            except Exception as e:
                log("WARNING", "memory bank forget failed", error=type(e).__name__, detail=str(e)[:160])
            _forget_later(session_id)
        try:
            await fs().collection("profiles").document(session_id).delete()
        except Exception as e:
            log("WARNING", "profile delete failed", error=type(e).__name__)
    return {"forgotten": True}


def _forget_later(session_id: str, delays: tuple[float, ...] = (15.0, 30.0)) -> None:
    """Memory generation runs server-side for ~10-20 s; delete again later so an in-flight write
    submitted just before "forget" does not survive it."""

    async def _run() -> None:
        for d in delays:
            await asyncio.sleep(d)
            try:
                n = await asyncio.wait_for(_mb_forget(session_id), 10)
                if n:
                    log("INFO", "late memories forgotten", backend="memory_bank", n=n)
            except Exception:
                pass

    try:
        task = asyncio.get_running_loop().create_task(_run())
        _later.add(task)
        task.add_done_callback(_later.discard)
    except RuntimeError:
        pass


_later: set[asyncio.Task] = set()


async def warm() -> None:
    """Open the Memory Bank / Firestore connection at startup so the first recall is fast."""
    try:
        if BACKEND == "memory_bank":
            await asyncio.wait_for(_mb_facts("warmup", "warmup"), 15)
        elif BACKEND == "firestore":
            await asyncio.wait_for(_fs_get("warmup"), 15)
    except Exception as e:
        log("WARNING", "memory warm-up failed", error=type(e).__name__)
