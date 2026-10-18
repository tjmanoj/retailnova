"""Approve / reject proposals, waitlist notifications, demo reset."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Optional

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from . import config
from .db import cache, clean_doc, fs, log, new_id, now_iso, now_utc
from .limits import ApiError
from .tools import catalog
from .tools import inventory as inv


async def approve(action_id: str) -> dict:
    db = fs()
    a_ref = db.collection("actions").document(action_id)

    @firestore.async_transactional
    async def txn(transaction):
        snap = await a_ref.get(transaction=transaction)
        if not snap.exists:
            raise ApiError(404, "not_found", "That action no longer exists. Try generating a new plan.")
        a = snap.to_dict()
        if a.get("status") != "proposed":
            raise ApiError(409, "already_decided", f"This action is already {a.get('status')}.")
        sku, size, qty = a["sku"], a.get("size") or "FREE", int(a["quantity"])
        dst_ref = db.collection("inventory").document(inv.inv_doc_id(a["store_id"], sku, size))
        dst = await dst_ref.get(transaction=transaction)
        dstd = dst.to_dict() if dst.exists else None
        changes = []
        now = now_utc()
        if a["type"] == "transfer":
            src_ref = db.collection("inventory").document(inv.inv_doc_id(a["from_store_id"], sku, size))
            src = await src_ref.get(transaction=transaction)
            src_on = int((src.to_dict() or {}).get("on_hand") or 0) if src.exists else 0
            move = max(0, min(qty, src_on))
            if move <= 0:
                raise ApiError(409, "no_stock", f"{config.store_name(a['from_store_id'])} no longer has stock to transfer.")
            dst_on = int((dstd or {}).get("on_hand") or 0)
            transaction.update(src_ref, {"on_hand": src_on - move, "updated_at": now})
            if dstd is not None:
                transaction.update(dst_ref, {"on_hand": dst_on + move, "updated_at": now})
            else:
                transaction.set(dst_ref, {"store_id": a["store_id"], "sku": sku, "size": size, "category": a["category"],
                                          "on_hand": move, "incoming": 0, "incoming_eta": None, "reorder_point": 0,
                                          "updated_at": now})
            changes = [
                {"store_id": a["from_store_id"], "sku": sku, "size": size, "delta": -move, "on_hand_after": src_on - move},
                {"store_id": a["store_id"], "sku": sku, "size": size, "delta": move, "on_hand_after": dst_on + move},
            ]
            a["quantity_moved"] = move
        elif a["type"] == "reorder":
            dst_on = int((dstd or {}).get("on_hand") or 0)
            inc = int((dstd or {}).get("incoming") or 0) + qty
            eta = a.get("eta_date")
            if dstd is not None:
                transaction.update(dst_ref, {"incoming": inc, "incoming_eta": eta, "updated_at": now})
            else:
                transaction.set(dst_ref, {"store_id": a["store_id"], "sku": sku, "size": size, "category": a["category"],
                                          "on_hand": 0, "incoming": inc, "incoming_eta": eta, "reorder_point": 0,
                                          "updated_at": now})
            changes = [{"store_id": a["store_id"], "sku": sku, "size": size, "delta": 0, "on_hand_after": dst_on,
                        "incoming_delta": qty, "incoming_after": inc, "incoming_eta": eta}]
        decided = now_iso()
        transaction.update(a_ref, {"status": "executed", "decided_at": decided})
        a["status"] = "executed"
        a["decided_at"] = decided
        return a, changes

    a, changes = await txn(db.transaction())
    inv.invalidate_inventory()
    cache.invalidate("radar")
    n = 0
    try:
        n = await _notify_waitlist(a)
    except Exception as e:
        log("WARNING", "waitlist notification failed", error=type(e).__name__, detail=str(e)[:200])
    a.pop("quantity_moved", None)
    log("INFO", "action approved", action_type=a["type"], sku=a["sku"], notifications=n)
    return {"action": clean_doc(a), "inventory_changes": changes, "notifications_created": n}


async def _notify_waitlist(a: dict) -> int:
    db = fs()
    q = db.collection("waitlist").where(filter=FieldFilter("sku", "==", a["sku"]))
    rows = [(d.reference, d.to_dict()) async for d in q.stream()]
    waiting = [(r, w) for r, w in rows if w.get("status") == "waiting"
               and (a.get("size") in (None, "FREE") or w.get("size") in (a.get("size"), None, "FREE"))]
    if a["type"] == "reorder":
        waiting = [(r, w) for r, w in waiting if not w.get("eta_notified")]
    same = [(r, w) for r, w in waiting if w.get("store_id") == a["store_id"]]
    targets = same or waiting
    if not targets:
        return 0
    p = await catalog.product(a["sku"])
    name = (p or {}).get("name") or a["sku"]
    store = config.store_name(a["store_id"])
    batch = db.batch()
    n = 0
    seen_sessions = set()
    cap = int(a.get("quantity_moved") or a.get("quantity") or 1) if a["type"] == "transfer" else 10_000
    for ref, w in sorted(targets, key=lambda x: str(x[1].get("created_at")))[:cap]:
        sess = w.get("session_id")
        if not sess:
            continue
        nid = new_id("ntf")
        kind = "reserved" if a["type"] == "transfer" else "transfer_eta"
        if (sess, kind) in seen_sessions:
            batch.update(ref, {"status": "notified"} if kind == "reserved" else {"eta_notified": True})
            continue
        if a["type"] == "transfer":
            kind = "reserved"
            msg = f"Good news! {name} is reserved for you at {store}. We'll hold it for 48 hours."
            rid = new_id("rsv")
            batch.set(db.collection("reservations").document(rid), {
                "reservation_id": rid, "session_id": sess, "sku": a["sku"], "size": a.get("size") or "FREE",
                "store_id": a["store_id"], "created_at": now_utc(), "hold_until": now_utc() + timedelta(hours=48),
                "status": "held"})
            batch.update(ref, {"status": "notified"})
        else:
            kind = "transfer_eta"
            msg = f"Good news! {name} is on its way to {store}, expected by {a.get('eta_date')}. We'll tell you when it lands."
            batch.update(ref, {"eta_notified": True})
        seen_sessions.add((sess, kind))
        batch.set(db.collection("notifications").document(nid), {
            "notification_id": nid, "session_id": sess, "kind": kind, "sku": a["sku"], "store_id": a["store_id"],
            "message": msg, "created_at": now_iso(), "read": False})
        n += 1
    await batch.commit()
    return n


async def reject(action_id: str) -> dict:
    ref = fs().collection("actions").document(action_id)
    snap = await ref.get()
    if not snap.exists:
        raise ApiError(404, "not_found", "That action no longer exists.")
    a = snap.to_dict()
    if a.get("status") != "proposed":
        raise ApiError(409, "already_decided", f"This action is already {a.get('status')}.")
    decided = now_iso()
    await ref.update({"status": "rejected", "decided_at": decided})
    a.update({"status": "rejected", "decided_at": decided})
    return {"action": clean_doc(a)}


async def notifications_for(session_id: str) -> list[dict]:
    q = fs().collection("notifications").where(filter=FieldFilter("session_id", "==", session_id))
    rows = [clean_doc(d.to_dict()) async for d in q.stream()]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Demo reset
# ---------------------------------------------------------------------------

async def _commit_in_batches(ops: list) -> int:
    db = fs()
    n = 0
    chunks = [ops[i : i + 400] for i in range(0, len(ops), 400)]

    async def commit(chunk):
        b = db.batch()
        for kind, ref, data in chunk:
            if kind == "set":
                b.set(ref, data)
            else:
                b.delete(ref)
        await b.commit()

    for i in range(0, len(chunks), 4):
        await asyncio.gather(*[commit(c) for c in chunks[i : i + 4]])
    for c in chunks:
        n += len(c)
    return n


async def reset_demo() -> dict:
    db = fs()
    ops: list = []
    async for d in db.collection("inventory_snapshot").stream():
        ops.append(("set", db.collection("inventory").document(d.id), d.to_dict()))
    q = db.collection("demand_signals").where(filter=FieldFilter("source", "==", "live"))
    async for d in q.select([]).stream():
        ops.append(("del", d.reference, None))
    for coll in ("waitlist", "reservations", "plans", "actions", "notifications"):
        async for d in db.collection(coll).select([]).stream():
            ops.append(("del", d.reference, None))
    n = await _commit_in_batches(ops)
    reset_at = now_utc()
    await db.document("meta/demo").set({"reset_at": reset_at}, merge=True)
    for prefix in ("signals", "radar", "meta"):  # BigQuery caches stay (that data does not change)
        cache.invalidate(prefix)
    inv.invalidate_inventory()
    log("INFO", "demo reset", writes=n)
    return {"reset_at": reset_at.isoformat().replace("+00:00", "Z")}
