"""Seed Firestore (database "(default)") from data/out/ (run data/generate.py and data/gen_embeddings.py first).

Collections written (idempotent `set` writes, batches of <= 400):
  stores, products (with `embedding` as a 768-dim Vector), inventory, inventory_snapshot (identical copy),
  customers, demand_signals (source "simulated"; stale simulated docs are deleted), and meta/demo LAST.
`meta/demo.seeded_at` is written last on purpose: other services poll it to know the data is ready.

Run with `source scripts/env.sh` first:  .venv/bin/python data/load_firestore.py
Targeted update (no full reseed, live demo state untouched): rewrite only some inventory docs in BOTH `inventory`
and `inventory_snapshot`, and bump meta/demo.snapshot_version:
  .venv/bin/python data/load_firestore.py --patch-inventory CBE-RSP__SAR-001__FREE HYD-BNJ__SAR-005__FREE
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_HERE = _Path(__file__).resolve().parent
_sys.path[:] = [p for p in _sys.path if _Path(p or ".").resolve() != _HERE]
_sys.path.insert(0, str(_HERE.parent))

import datetime as dt  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402
from google.cloud.firestore_v1.vector import Vector  # noqa: E402

from data.catalog_spec import PRODUCT_FIELDS, PRODUCTS, STORE_FIELDS, STORES  # noqa: E402

OUT = _HERE / "out"
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "retailnova-ai")
BATCH = 400


def native(v):
    """numpy / pandas values -> plain Python for Firestore."""
    if isinstance(v, dict):
        return {k: native(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [native(x) for x in v]
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if math.isnan(v) else float(v)
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NaT:
        return None
    return v


def write_all(db: firestore.Client, coll: str, docs: list[tuple[str, dict]]) -> int:
    n = 0
    for i in range(0, len(docs), BATCH):
        b = db.batch()
        for doc_id, data in docs[i:i + BATCH]:
            b.set(db.collection(coll).document(doc_id), data)
        for attempt in range(5):
            try:
                b.commit()
                break
            except Exception as e:  # transient contention / deadline
                if attempt == 4:
                    raise
                print(f"  retry {coll} batch {i // BATCH}: {str(e)[:100]}")
                time.sleep(2 ** attempt)
        n += len(docs[i:i + BATCH])
    print(f"  {coll:<20} {n:>5} docs")
    return n


def delete_ids(db: firestore.Client, coll: str, ids: list[str]) -> None:
    for i in range(0, len(ids), BATCH):
        b = db.batch()
        for doc_id in ids[i:i + BATCH]:
            b.delete(db.collection(coll).document(doc_id))
        b.commit()


def patch_inventory(doc_ids: list[str]) -> None:
    manifest = json.loads((OUT / "manifest.json").read_text())
    db = firestore.Client(project=PROJECT)
    inv = pd.read_parquet(OUT / "inventory.parquet").set_index("doc_id")
    for doc_id in doc_ids:
        rec = native(inv.loc[doc_id].to_dict())
        rec["updated_at"] = dt.datetime.fromisoformat(rec["updated_at"].replace("Z", "+00:00"))
        for coll in ("inventory", "inventory_snapshot"):
            before = (db.collection(coll).document(doc_id).get().to_dict() or {})
            db.collection(coll).document(doc_id).set(rec)
            print(f"  {coll}/{doc_id}: on_hand {before.get('on_hand')} -> {rec['on_hand']}, "
                  f"reorder_point {before.get('reorder_point')} -> {rec['reorder_point']}")
    db.collection("meta").document("demo").set({"snapshot_version": f"sim-{manifest['hash'][:12]}"}, merge=True)
    print(f"  meta/demo snapshot_version -> sim-{manifest['hash'][:12]}")


def main() -> None:
    if len(_sys.argv) > 2 and _sys.argv[1] == "--patch-inventory":
        patch_inventory(_sys.argv[2:])
        return
    manifest = json.loads((OUT / "manifest.json").read_text())
    emb = json.loads((OUT / "embeddings.json").read_text())["items"]
    missing = [p["sku"] for p in PRODUCTS if p["sku"] not in emb]
    assert not missing, f"missing embeddings for {missing}: run data/gen_embeddings.py"
    db = firestore.Client(project=PROJECT)
    print(f"seeding Firestore project {PROJECT} (generator hash {manifest['hash'][:12]})")

    write_all(db, "stores", [(s["store_id"], {k: s[k] for k in STORE_FIELDS}) for s in STORES])

    prods = []
    for p in PRODUCTS:
        d = {k: p[k] for k in PRODUCT_FIELDS}
        vec = emb[p["sku"]]["vector"]
        assert len(vec) == 768
        d["embedding"] = Vector(vec)
        prods.append((p["sku"], d))
    write_all(db, "products", prods)

    inv = pd.read_parquet(OUT / "inventory.parquet")
    inv_docs = []
    for rec in inv.to_dict("records"):
        doc_id = rec.pop("doc_id")
        rec = native(rec)
        rec["updated_at"] = dt.datetime.fromisoformat(rec["updated_at"].replace("Z", "+00:00"))
        inv_docs.append((doc_id, rec))
    write_all(db, "inventory", inv_docs)
    write_all(db, "inventory_snapshot", inv_docs)

    cust = pd.read_parquet(OUT / "customers.parquet")
    write_all(db, "customers", [(r["customer_id"], native(r)) for r in cust.to_dict("records")])

    sigs = json.loads((OUT / "demand_signals.json").read_text())
    keep = {s["signal_id"] for s in sigs}
    stale = [d.id for d in db.collection("demand_signals")
             .where(filter=FieldFilter("source", "==", "simulated")).select([]).stream() if d.id not in keep]
    if stale:
        delete_ids(db, "demand_signals", stale)
        print(f"  deleted {len(stale)} stale simulated demand_signals")
    write_all(db, "demand_signals", [(s["signal_id"], s) for s in sigs])

    # meta/demo LAST: seeded_at tells the API and UI that the data is ready.
    db.collection("meta").document("demo").set({
        "demo_today": "2026-10-18", "diwali_date": "2026-11-08",
        "snapshot_version": f"sim-{manifest['hash'][:12]}", "reset_at": None,
        "seeded_at": firestore.SERVER_TIMESTAMP,
    })
    meta = db.collection("meta").document("demo").get().to_dict()
    print(f"  meta/demo            seeded_at={meta['seeded_at']}  snapshot_version={meta['snapshot_version']}")


if __name__ == "__main__":
    main()
