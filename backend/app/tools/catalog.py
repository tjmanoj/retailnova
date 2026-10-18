"""Catalog: product cache, semantic search (Firestore vector search) and ProductCards."""
from __future__ import annotations

import math
import re
from typing import Optional

from .. import config
from ..db import cache, clean_doc, fs, log
from ..llm import embed_query
from . import inventory as inv

PRODUCTS_TTL = 600.0


async def products() -> dict[str, dict]:
    """sku -> product (embedding kept as a plain list under `_vec`)."""

    async def load():
        out = {}
        async for d in fs().collection("products").stream():
            raw = d.to_dict() or {}
            vec = raw.get("embedding")
            p = clean_doc(raw)
            p["_vec"] = list(vec) if vec is not None else None
            out[p.get("sku") or d.id] = p
        if not out:
            raise RuntimeError("catalog is empty")
        return out

    return await cache.get_or_load("products", PRODUCTS_TTL, load)


async def product(sku: str) -> Optional[dict]:
    return (await products()).get((sku or "").upper().strip())


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).strip()


_CATEGORY_ALIASES = {
    "saree": "sarees", "sari": "sarees", "sarees": "sarees", "pudavai": "sarees",
    "kurta_set": "kurta_sets", "kurta sets": "kurta_sets", "kurta_sets": "kurta_sets", "women kurta": "kurta_sets",
    "mens": "mens_ethnic", "men": "mens_ethnic", "mens_ethnic": "mens_ethnic", "men's ethnic": "mens_ethnic",
    "home_decor": "home_decor", "decor": "home_decor", "home decor": "home_decor",
    "gifting": "gifting", "gift": "gifting", "gifts": "gifting",
    "footwear": "footwear", "shoes": "footwear", "juttis": "footwear",
}


def normalize_category(c: Optional[str]) -> Optional[str]:
    if not c:
        return None
    k = c.strip().lower()
    if k in config.CATEGORY_IDS:
        return k
    return _CATEGORY_ALIASES.get(k)


def _color_match(p: dict, color: Optional[str]) -> bool:
    if not color:
        return True
    c = _norm(color)
    fields = " ".join([_norm(p.get("color")), _norm(p.get("color_family")), _norm(p.get("name"))])
    return any(tok and tok in fields for tok in c.split())


def _passes(p: dict, category, color, max_price, size, strict_color=True) -> bool:
    if category and p.get("category") != category:
        return False
    if max_price and int(p.get("price_inr") or 0) > int(max_price):
        return False
    if size and size.upper() not in [s.upper() for s in p.get("sizes") or []] and "FREE" not in (p.get("sizes") or []):
        return False
    if strict_color and not _color_match(p, color):
        return False
    return True


async def vector_search(query_text: str, limit: int = 12) -> list[tuple[str, float]]:
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from google.cloud.firestore_v1.vector import Vector

    import time as _t
    t0 = _t.monotonic()
    vec = await embed_query(query_text)
    t1 = _t.monotonic()
    q = fs().collection("products").select(["sku"]).find_nearest(
        vector_field="embedding",
        query_vector=Vector(vec),
        distance_measure=DistanceMeasure.COSINE,
        limit=limit,
        distance_result_field="_distance",
    )
    out = []
    async for d in q.stream():
        dd = d.to_dict() or {}
        out.append((dd.get("sku") or d.id, float(dd.get("_distance") or 0.0)))
    log("INFO", "vector search", embed_ms=int((t1 - t0) * 1000), nearest_ms=int((_t.monotonic() - t1) * 1000), hits=len(out))
    return out, vec


async def search(
    query: str,
    store_id: str,
    category: Optional[str] = None,
    color: Optional[str] = None,
    max_price_inr: Optional[int] = None,
    size: Optional[str] = None,
    k: int = 6,
) -> list[dict]:
    """Semantic search, post-filtered by constraints. Returns product dicts ranked best first."""
    category = normalize_category(category)
    size = size.upper().strip() if size else None
    if size in ("FREE SIZE", "ONE SIZE"):
        size = "FREE"
    cat = await products()
    text = " ".join(x for x in [query, color or "", config.CATEGORY_LABEL.get(category or "", "")] if x).strip()
    qvec = None
    try:
        hits, qvec = await vector_search(text, limit=12)
    except Exception as e:  # embedding / vector search unavailable -> keyword ranking on the cached catalog
        log("WARNING", "vector search failed; keyword ranking", error=type(e).__name__, detail=str(e)[:160])
        hits = []
    ranked = [cat[s] for s, _ in hits if s in cat]
    filtered = [p for p in ranked if _passes(p, category, color, max_price_inr, size)]
    if len(filtered) < 3:
        # Supplement from the full catalog (72 SKUs), ranked by cosine similarity (or keywords).
        pool = [p for p in cat.values() if p not in filtered and _passes(p, category, color, max_price_inr, size)]
        if len(filtered) + len(pool) < 2 and color:
            pool += [p for p in cat.values() if p not in filtered and p not in pool
                     and _passes(p, category, None, max_price_inr, size)]
        if qvec is not None:
            pool.sort(key=lambda p: -_cos(qvec, p["_vec"]) if p.get("_vec") else 0)
        else:
            pool.sort(key=lambda p: -_keyword_score(text, p))
        filtered += pool[: max(0, k - len(filtered))]
    return filtered[:k]


def _keyword_score(text: str, p: dict) -> float:
    q = set(_norm(text).split())
    hay = " ".join([_norm(p.get("name")), _norm(p.get("color")), _norm(p.get("material")), _norm(p.get("subcategory")),
                    " ".join(_norm(t) for t in p.get("tags") or []), _norm(p.get("category"))])
    words = set(hay.split())
    return sum(2 if w in words else (1 if w in hay else 0) for w in q if len(w) > 2)


async def alternatives(sku: str, store_id: str, size: Optional[str] = None, k: int = 4) -> list[dict]:
    """Similar products in the same category that are in stock at the store (or anywhere)."""
    cat = await products()
    base = cat.get(sku)
    if not base:
        return []
    pool = [p for p in cat.values() if p["sku"] != sku and p.get("category") == base.get("category")]
    if base.get("_vec"):
        pool.sort(key=lambda p: -_cos(base["_vec"], p["_vec"]) if p.get("_vec") else 0)
    else:
        pool.sort(key=lambda p: abs(int(p.get("price_inr") or 0) - int(base.get("price_inr") or 0)))
    invs = await inv.inventory_for_skus([p["sku"] for p in pool[:12]])
    here = [p for p in pool[:12] if inv.qty_at(invs.get(p["sku"], []), store_id, size if size in (p.get("sizes") or []) else None) > 0]
    anywhere = [p for p in pool[:12] if p not in here and sum(inv.qty_at(invs.get(p["sku"], []), s) for s in config.STORE_ORDER) > 0]
    return (here + anywhere)[:k]


def compact(p: dict, rows: list[dict], store_id: str, size: Optional[str]) -> dict:
    """A small, model-friendly view of a product with stock facts."""
    sz = size if size and size in (p.get("sizes") or []) else None
    here = inv.qty_at(rows, store_id, sz)
    sizes_here = sorted({r["size"] for r in rows if r.get("store_id") == store_id and int(r.get("on_hand") or 0) > 0})
    others = []
    for sid in config.STORE_ORDER:
        if sid == store_id:
            continue
        q = inv.qty_at(rows, sid, sz)
        if q > 0:
            others.append((inv.rank_other_store(store_id, sid, q), q, f"{config.store_name(sid)} ({sid}): {q}"))
    others.sort()
    healthy = [s for _, q, s in others if q >= 4]
    others = healthy or [s + " (only a few left)" for _, q, s in others]
    store = config.store_name(store_id)
    if here <= 0:
        if sz and sizes_here:
            status = f"SIZE {sz} OUT OF STOCK at {store} (sizes in stock there: {', '.join(sizes_here)})"
        else:
            status = f"OUT OF STOCK at {store}" + (f" in size {sz}" if sz else "")
    elif here < 4:
        status = f"LOW: only {here} left at {store}" + (f" in size {sz}" if sz else "")
    else:
        status = f"IN STOCK at {store}: {here}" + (f" in size {sz}" if sz else "")
    out = {
        "sku": p["sku"],
        "name": p.get("name"),
        "price_inr": p.get("price_inr"),
        "mrp_inr": p.get("mrp_inr"),
        "color": p.get("color"),
        "material": p.get("material"),
        "sizes": p.get("sizes"),
        "status_at_your_store": status,
        "stock_here": here,
        "other_stores_with_stock": others[:3] if here <= 0 or here < 4 else others[:2],
    }
    return out


async def build_cards(skus: list[str], store_id: str, size: Optional[str], reason: Optional[str]) -> list[dict]:
    cat = await products()
    invs = await inv.inventory_for_skus(skus)
    cards = []
    for s in skus:
        p = cat.get(s)
        if not p:
            continue
        rows = invs.get(s, [])
        sz = size if size and size in (p.get("sizes") or []) else None
        badge, here = inv.badge_for(rows, store_id, sz)
        category = p.get("category") or config.PREFIX_TO_CATEGORY.get(s.split("-")[0], "sarees")
        cards.append(
            {
                "sku": s,
                "name": p.get("name") or s,
                "category": category,
                "color": p.get("color") or "",
                "material": p.get("material") or "",
                "price_inr": int(p.get("price_inr") or 0),
                "mrp_inr": int(p.get("mrp_inr") or p.get("price_inr") or 0),
                "image_url": p.get("image_url") or f"/products/{s}.webp",
                "image_alt": p.get("image_alt") or p.get("name") or s,
                "sizes": p.get("sizes") or [],
                "availability": inv.store_stock(rows),
                "requested_store_id": store_id,
                "requested_store_on_hand": here,
                "badge": badge,
                "reason": (reason or None) and reason[:140],
            }
        )
    return cards
