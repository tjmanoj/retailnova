"""Inventory reads, availability summaries, reservations and the waitlist."""
from __future__ import annotations

import asyncio
import time
import math
from datetime import timedelta
from typing import Optional

from .. import config
from ..db import cache, clean_doc, fs, log, new_id, now_iso, now_utc

INV_TTL = 8.0


def inv_doc_id(store_id: str, sku: str, size: str) -> str:
    return f"{store_id}__{sku}__{size}"


class _InventorySnapshot:
    """Whole `inventory` collection (~1.4k docs) held in memory, stale-while-revalidate.

    Reads are served from memory; if the copy is older than INV_TTL a background
    refresh starts. Writes made by this service (approve, reset) force a reload.
    """

    def __init__(self) -> None:
        self.rows: list[dict] | None = None
        self.by_sku: dict[str, list[dict]] = {}
        self.loaded_at = 0.0
        self._lock = asyncio.Lock()
        self._refreshing: asyncio.Task | None = None

    async def _load(self) -> None:
        rows = [clean_doc(d.to_dict()) async for d in fs().collection("inventory").stream()]
        by_sku: dict[str, list[dict]] = {}
        for r in rows:
            by_sku.setdefault(r.get("sku"), []).append(r)
        self.rows, self.by_sku, self.loaded_at = rows, by_sku, time.monotonic()

    async def get(self) -> "_InventorySnapshot":
        if self.rows is None:
            async with self._lock:
                if self.rows is None:
                    await self._load()
        elif time.monotonic() - self.loaded_at > INV_TTL and (self._refreshing is None or self._refreshing.done()):
            self._refreshing = asyncio.create_task(self._refresh())
        return self

    async def _refresh(self) -> None:
        try:
            await self._load()
        except Exception as e:
            log("WARNING", "inventory refresh failed", error=type(e).__name__)

    def invalidate(self) -> None:
        self.rows = None


_snap = _InventorySnapshot()


async def inventory_for_skus(skus: list[str]) -> dict[str, list[dict]]:
    """sku -> inventory rows (all stores, all sizes)."""
    s = await _snap.get()
    return {k: s.by_sku.get(k, []) for k in dict.fromkeys(skus)}


async def inventory_for_store(store_id: str) -> list[dict]:
    s = await _snap.get()
    return [r for r in s.rows if r.get("store_id") == store_id]


async def inventory_for_category(category: str) -> list[dict]:
    s = await _snap.get()
    return [r for r in s.rows if r.get("category") == category]


async def warm_inventory() -> None:
    await _snap.get()


def invalidate_inventory() -> None:
    _snap.invalidate()


def store_stock(rows: list[dict], size: Optional[str] = None) -> list[dict]:
    """Rows for one sku -> StoreStock for every store (physical + ONLINE), in contract order."""
    by_store: dict[str, dict] = {
        sid: {"store_id": sid, "store_name": config.store_name(sid), "on_hand": 0, "sizes_in_stock": []}
        for sid in config.STORE_ORDER
    }
    for r in rows:
        sid = r.get("store_id")
        if sid not in by_store:
            by_store[sid] = {"store_id": sid, "store_name": config.store_name(sid), "on_hand": 0, "sizes_in_stock": []}
        oh = int(r.get("on_hand") or 0)
        by_store[sid]["on_hand"] += max(oh, 0)
        if oh > 0 and r.get("size") not in by_store[sid]["sizes_in_stock"]:
            by_store[sid]["sizes_in_stock"].append(r.get("size"))
    for v in by_store.values():
        v["sizes_in_stock"] = _sort_sizes(v["sizes_in_stock"])
    return list(by_store.values())


_SIZE_ORDER = ["FREE", "XS", "S", "M", "L", "XL", "XXL", "6", "7", "8", "9", "10"]


def _sort_sizes(sizes: list[str]) -> list[str]:
    return sorted(sizes, key=lambda s: _SIZE_ORDER.index(s) if s in _SIZE_ORDER else 99)


def qty_at(rows: list[dict], store_id: str, size: Optional[str] = None) -> int:
    return sum(
        max(int(r.get("on_hand") or 0), 0)
        for r in rows
        if r.get("store_id") == store_id and (size is None or r.get("size") == size)
    )


def badge_for(rows: list[dict], store_id: str, size: Optional[str]) -> tuple[str, int]:
    here = qty_at(rows, store_id, size)
    if here >= 4:
        return "in_stock", here
    if here > 0:
        return "low", here
    elsewhere = sum(
        max(int(r.get("on_hand") or 0), 0)
        for r in rows
        if r.get("store_id") != store_id and (size is None or r.get("size") == size)
    )
    return ("other_store" if elsewhere > 0 else "out_of_stock"), here


def _distance_km(a: str, b: str) -> float:
    sa, sb = config.STORES.get(a), config.STORES.get(b)
    if not sa or not sb or sa.get("lat") is None or sb.get("lat") is None:
        return 99999.0
    lat1, lon1, lat2, lon2 = map(math.radians, [sa["lat"], sa["lng"], sb["lat"], sb["lng"]])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


_STATE = {"CHN": "TN", "CBE": "TN", "BLR": "KA", "HYD": "TS"}


def rank_other_store(store_id: str, other: str, qty: int) -> tuple:
    """Sort key for 'where else is it': healthy stock first, then same state, then distance; ONLINE last."""
    same_state = _STATE.get(store_id.split("-")[0]) == _STATE.get(other.split("-")[0])
    return (other == "ONLINE", qty < 4, not same_state, _distance_km(store_id, other))


def nearest_with_stock(rows: list[dict], store_id: str, size: Optional[str]) -> Optional[dict]:
    """Best *other* store with stock: healthy stock (>= 4) first, same state, nearest; ONLINE last."""
    cands = []
    for sid in config.STORE_ORDER:
        if sid == store_id:
            continue
        q = qty_at(rows, sid, size)
        if q > 0:
            cands.append((rank_other_store(store_id, sid, q), sid, q))
    if not cands:
        return None
    cands.sort()
    _, sid, q = cands[0]
    d = _distance_km(store_id, sid)
    out = {"store_id": sid, "store_name": config.store_name(sid), "on_hand": q}
    if d < 99999:
        out["distance_km"] = round(d)
    return out


# ---------------------------------------------------------------------------
# Writes: reservations / waitlist
# ---------------------------------------------------------------------------

async def create_waitlist(session_id: str, sku: str, size: str, store_id: str) -> dict:
    wid = new_id("wl")
    doc = {
        "waitlist_id": wid,
        "session_id": session_id,
        "sku": sku,
        "size": size or "FREE",
        "store_id": store_id,
        "created_at": now_utc(),
        "status": "waiting",
    }
    await fs().collection("waitlist").document(wid).set(doc)
    log("INFO", "waitlist created", sku=sku, store_id=store_id)
    return {"waitlist_id": wid, **{k: v for k, v in doc.items() if k != "created_at"}, "created_at": now_iso()}


async def create_reservation(session_id: str, sku: str, size: str, store_id: str, hours: int = 48) -> dict:
    rid = new_id("rsv")
    hold_until = now_utc() + timedelta(hours=hours)
    doc = {
        "reservation_id": rid,
        "session_id": session_id,
        "sku": sku,
        "size": size or "FREE",
        "store_id": store_id,
        "created_at": now_utc(),
        "hold_until": hold_until,
        "status": "held",
    }
    await fs().collection("reservations").document(rid).set(doc)
    log("INFO", "reservation created", sku=sku, store_id=store_id)
    return {"reservation_id": rid, "hold_until": hold_until.isoformat().replace("+00:00", "Z")}
