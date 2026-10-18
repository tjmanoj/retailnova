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


CATEGORY_BOOST = 0.05      # cosine-distance bonus for the requested category
CROSS_CATEGORY_MARGIN = 0.03  # another category's item must beat the best in-category match by this much
COLOR_BOOST = 0.10     # exact colour matches rank first when colour had to be relaxed


async def search(
    query: str,
    store_id: str,
    category: Optional[str] = None,
    color: Optional[str] = None,
    max_price_inr: Optional[int] = None,
    size: Optional[str] = None,
    k: int = 6,
) -> list[dict]:
    """Semantic search with hard budget/size/colour filters. Returns product dicts ranked best first.

    `category` is a ranking boost, not a hard filter: a product from another category is kept when it
    matches the query clearly better than anything in the requested category (e.g. a brass diya set,
    which is home decor, asked for "for gifting"), or when the category has fewer than 3 matches.
    """
    category = normalize_category(category)
    size = size.upper().strip() if size else None
    if size in ("FREE SIZE", "ONE SIZE"):
        size = "FREE"
    cat = await products()
    text = " ".join(x for x in [query, color or ""] if x).strip()
    qvec = None
    try:
        hits, qvec = await vector_search(text, limit=12)
    except Exception as e:  # embedding / vector search unavailable -> keyword ranking on the cached catalog
        log("WARNING", "vector search failed; keyword ranking", error=type(e).__name__, detail=str(e)[:160])
        hits = []
    # Cosine distance computed locally against the cached product embeddings (same metric as the
    # Firestore vector index; the projected find_nearest results do not carry the distance field).
    hit_rank = {s: i for i, (s, _) in enumerate(hits)}

    def dist(p: dict) -> float:
        if qvec is not None and p.get("_vec"):
            return 1.0 - _cos(qvec, p["_vec"])
        if p["sku"] in hit_rank:
            return 0.2 + 0.01 * hit_rank[p["sku"]]
        return 1.0 - min(1.0, _keyword_score(text, p) / 10.0)

    def candidates(col: Optional[str]) -> list[dict]:
        return [p for p in cat.values() if _passes(p, None, col, max_price_inr, size)]

    pool = candidates(color)
    if category:
        in_cat = [p for p in pool if p.get("category") == category]
        if color and len(in_cat) < 3:  # relax colour inside the category first (labelled as alternatives)
            in_cat += [p for p in candidates(None) if p.get("category") == category and p not in in_cat]
        best = min((dist(p) for p in in_cat), default=None)
        # Other categories only when clearly better than anything in the requested one (or it has nothing).
        others = [p for p in pool if p.get("category") != category
                  and (best is None or dist(p) < best - CROSS_CATEGORY_MARGIN)]
        pool = in_cat + others
    elif color and len(pool) < 2:
        pool = candidates(None)

    def score(p: dict) -> float:
        s = dist(p)
        if category and p.get("category") == category:
            s -= CATEGORY_BOOST
        if color and color_matches_strict(p, color):
            s -= COLOR_BOOST
        return s

    pool.sort(key=score)
    return pool[:k]


_STOP = {"the", "and", "with", "for", "set", "of", "a", "an", "in", "s", "women", "men", "mens", "womens"}


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def main_name(p: dict) -> str:
    """Product name without its trailing detail ('Maroon Kanchipuram Silk Saree, gold zari border' -> first part)."""
    return re.split(r",| with | \(", (p.get("name") or "").lower())[0].strip()


def mention_positions(text: str, skus: list[str], prods: dict) -> dict[str, int]:
    """SKU -> first position where `text` names it (by SKU id or by its main product name)."""
    low = re.sub(r"[^a-z0-9]", " ", (text or "").lower())  # same length as text
    pos: dict[str, int] = {}
    for s in dict.fromkeys(skus):
        p = prods.get(s)
        if not p:
            continue
        hits = []
        m = re.search(r"\b" + r"\s*".join(re.escape(x) for x in s.lower().split("-")) + r"\b", low)
        if m:
            hits.append(m.start())
        words = re.sub(r"[^a-z0-9]", " ", main_name(p)).split()
        if words:
            m = re.search(r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b", low)
            if m:
                hits.append(m.start())
        if hits:
            pos[s] = min(hits)
    return pos


def catalog_match(message: str, prods: dict) -> Optional[str]:
    """A catalog SKU the shopper's own words name: its SKU id, or every content word of its main name."""
    msg = message or ""
    for m in re.finditer(r"\b([A-Za-z]{3})-(\d{3})\b", msg):
        sku = f"{m.group(1).upper()}-{m.group(2)}"
        if sku in prods:
            return sku
    toks = {_stem(w) for w in re.sub(r"[^a-z0-9]", " ", msg.lower()).split()}
    best, best_n = None, 0
    for s, p in prods.items():
        words = [_stem(w) for w in re.sub(r"[^a-z0-9]", " ", main_name(p)).split() if w not in _STOP and len(w) > 2]
        if len(words) >= 2 and all(w in toks for w in words) and len(words) > best_n:
            best, best_n = s, len(words)
    return best


def invalid_sku_ids(message: str, prods: dict) -> list[str]:
    """SKU-shaped ids in the message that are not in the catalog (e.g. 'SAR-999')."""
    out = []
    for m in re.finditer(r"\b([A-Za-z]{3})-(\d{3})\b", message or ""):
        sku = f"{m.group(1).upper()}-{m.group(2)}"
        if m.group(1).upper() in config.PREFIX_TO_CATEGORY and sku not in prods:
            out.append(sku)
    return out


def color_matches_strict(p: dict, color: Optional[str]) -> bool:
    """Requested colour appears in the product's own colour or name (colour family not counted)."""
    if not color:
        return True
    fields = " ".join([_norm(p.get("color")), _norm(p.get("name"))])
    return any(tok and tok in fields for tok in _norm(color).split())


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
            others.append((inv.rank_other_store(store_id, sid, q), q, f"{store_label(sid)} ({sid}): {q}"))
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


def store_label(sid: str) -> str:
    """'RS Puram, Coimbatore' (city added for physical stores)."""
    st = config.STORES.get(sid) or {}
    return f"{st.get('name', sid)}, {st['city']}" if st.get("city") else st.get("name", sid)


async def build_cards(skus: list[str], store_id: str, size: Optional[str], reason: Optional[str],
                      requested_color: Optional[str] = None) -> list[dict]:
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
                "reason": _card_reason(p, reason, requested_color),
            }
        )
    return cards


def _card_reason(p: dict, reason: Optional[str], requested_color: Optional[str]) -> Optional[str]:
    if requested_color and not color_matches_strict(p, requested_color):
        alt = f"Alternative: different colour ({p.get('color') or 'other'})"
        return (alt + (f". {reason}" if reason else ""))[:140]
    return (reason or None) and reason[:140]


_COLOR_WORDS: set[str] | None = None


async def color_in_text(text: str) -> Optional[str]:
    """A catalog colour word mentioned in free text ('pink kurta set' -> 'pink')."""
    global _COLOR_WORDS
    if _COLOR_WORDS is None:
        words = set()
        for p in (await products()).values():
            for f in (p.get("color"), p.get("color_family")):
                words |= {w for w in _norm(f).split() if len(w) > 2}
        _COLOR_WORDS = words
    for w in _norm(text).split():
        if w in _COLOR_WORDS:
            return w
    return None
