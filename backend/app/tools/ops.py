"""Read-only ops data: forecasts (BigQuery), unmet demand (Firestore), inventory position, transfer options.

BigQuery results are cached for 5 minutes, Firestore aggregates for ~15 seconds.
Missing BigQuery tables raise BQUnavailable; callers degrade gracefully.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Optional

from google.cloud import bigquery

from .. import config
from ..db import BQUnavailable, bq_query, bq_table, cache, clean_doc, fs, log
from . import catalog
from . import inventory as inv

BQ_TTL = 300.0
FS_TTL = 15.0

# ---------------------------------------------------------------------------
# BigQuery loaders
# ---------------------------------------------------------------------------


async def forecast_rows(store_id: str) -> list[dict]:
    """All categories, both variants, 42-day horizon from DEMO_TODAY (latest run only)."""

    async def load():
        sql = f"""
        SELECT category, CAST(forecast_date AS STRING) AS d, variant, forecast_value AS v, lower, upper, model
        FROM {bq_table('forecasts')}
        WHERE store_id = @store AND forecast_date BETWEEN @start AND @end
        QUALIFY ROW_NUMBER() OVER (PARTITION BY category, forecast_date, variant ORDER BY run_at DESC) = 1
        """
        return await bq_query(sql, [
            bigquery.ScalarQueryParameter("store", "STRING", store_id),
            bigquery.ScalarQueryParameter("start", "DATE", config.DEMO_TODAY),
            bigquery.ScalarQueryParameter("end", "DATE", config.day_offset(41)),
        ])

    return await cache.get_or_load(("bq_fc", store_id), BQ_TTL, load)


async def sales_by_day(store_id: str) -> list[dict]:
    """Last 56 days of observed units by date x category for one store."""

    async def load():
        sql = f"""
        SELECT CAST(date AS STRING) AS d, category, SUM(units_sold) AS u
        FROM {bq_table('sales_daily')}
        WHERE store_id = @store AND date BETWEEN @start AND @end
        GROUP BY 1, 2
        """
        return await bq_query(sql, [
            bigquery.ScalarQueryParameter("store", "STRING", store_id),
            bigquery.ScalarQueryParameter("start", "DATE", config.day_offset(-56)),
            bigquery.ScalarQueryParameter("end", "DATE", config.day_offset(-1)),
        ])

    return await cache.get_or_load(("bq_sales", store_id), BQ_TTL, load)


async def sku_velocity(category: str) -> dict[tuple[str, str], dict]:
    """(store_id, sku) -> {units_28d, stockout_days} for a category, last 28 days."""

    async def load():
        sql = f"""
        SELECT store_id, sku, SUM(units_sold) AS u, COUNTIF(stock_open <= 0) AS so_days
        FROM {bq_table('sales_daily')}
        WHERE category = @cat AND date BETWEEN @start AND @end
        GROUP BY 1, 2
        """
        rows = await bq_query(sql, [
            bigquery.ScalarQueryParameter("cat", "STRING", category),
            bigquery.ScalarQueryParameter("start", "DATE", config.day_offset(-28)),
            bigquery.ScalarQueryParameter("end", "DATE", config.day_offset(-1)),
        ])
        return {(r["store_id"], r["sku"]): {"units_28d": int(r["u"] or 0), "stockout_days": int(r["so_days"] or 0)} for r in rows}

    return await cache.get_or_load(("bq_vel", category), BQ_TTL, load)


# ---------------------------------------------------------------------------
# Firestore loaders
# ---------------------------------------------------------------------------


async def signals_for_store(store_id: str) -> list[dict]:
    from google.cloud.firestore_v1.base_query import FieldFilter

    async def load():
        q = fs().collection("demand_signals").where(filter=FieldFilter("store_id", "==", store_id))
        rows = [clean_doc(d.to_dict()) async for d in q.stream()]
        rows.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
        return rows

    return await cache.get_or_load(("signals", store_id), FS_TTL, load)


def _in_window(r: dict, days: int) -> bool:
    d = str(r.get("date") or "")[:10]
    return config.day_offset(-(days - 1)) <= d <= config.DEMO_TODAY


# ---------------------------------------------------------------------------
# Aggregations used by tools, planner and radar
# ---------------------------------------------------------------------------


def _gap_key(r: dict) -> tuple:
    if r.get("sku"):
        return (r.get("category"), r.get("sku"), "")
    a = r.get("attributes") or {}
    return (r.get("category"), None, (a.get("color") or a.get("material") or "").lower())


def _trend(by_day: dict[str, int]) -> str:
    # compare the last 3 complete days with the 4 before (today is still in progress)
    recent = sum(by_day.get(config.day_offset(-i), 0) for i in range(1, 4)) / 3
    prior = sum(by_day.get(config.day_offset(-i), 0) for i in range(4, 8)) / 4
    if recent > prior * 1.2 and recent - prior >= 0.5:
        return "rising"
    if recent < prior * 0.8 and prior - recent >= 0.5:
        return "falling"
    return "flat"


async def unmet_groups(store_id: str, category: Optional[str] = None, days: int = 7) -> dict:
    sigs = [r for r in await signals_for_store(store_id) if _in_window(r, days)
            and (category is None or r.get("category") == category)]
    prods = await catalog.products()
    groups: dict[tuple, dict] = {}
    totals = {"signals": len(sigs), "unmet_signals": 0, "unmet_units": 0, "unmet_value_inr": 0,
              "substituted": 0, "fulfilled": 0, "live_signals": 0}
    for r in sigs:
        if r.get("source") == "live":
            totals["live_signals"] += 1
        oc = r.get("outcome")
        if oc == "substituted":
            totals["substituted"] += 1
        elif oc == "fulfilled":
            totals["fulfilled"] += 1
        if oc != "unmet":
            continue
        qty = int(r.get("quantity") or 1)
        val = int(r.get("est_value_inr") or 0)
        totals["unmet_signals"] += 1
        totals["unmet_units"] += qty
        totals["unmet_value_inr"] += val
        k = _gap_key(r)
        g = groups.setdefault(k, {"category": k[0], "sku": k[1], "attributes": {}, "unmet_units_7d": 0,
                                  "unmet_value_7d_inr": 0, "signals": 0, "by_day": defaultdict(int), "reasons": defaultdict(int)})
        g["unmet_units_7d"] += qty
        g["unmet_value_7d_inr"] += val
        g["signals"] += 1
        g["by_day"][str(r.get("date"))[:10]] += qty
        if r.get("reason"):
            g["reasons"][r["reason"]] += 1
        for ak, av in (r.get("attributes") or {}).items():
            if av and ak in ("color", "material", "size", "occasion"):
                g["attributes"].setdefault(ak, defaultdict(int))[str(av).lower()] += 1
    out = []
    for k, g in groups.items():
        attrs = {ak: max(av.items(), key=lambda x: x[1])[0] for ak, av in g["attributes"].items()}
        p = prods.get(g["sku"]) if g["sku"] else None
        if p:
            label = p.get("name") or g["sku"]
        else:
            label = " ".join(x for x in [attrs.get("color", "").title(), attrs.get("material", ""),
                                          config.CATEGORY_LABEL.get(g["category"], g["category"] or "").lower()] if x).strip()
        out.append({
            "category": g["category"], "sku": g["sku"], "label": label, "attributes": attrs,
            "unmet_units_7d": g["unmet_units_7d"], "unmet_value_7d_inr": g["unmet_value_7d_inr"],
            "signals": g["signals"], "trend": _trend(g["by_day"]),
            "top_reason": max(g["reasons"].items(), key=lambda x: x[1])[0] if g["reasons"] else None,
            "by_day": dict(sorted(g["by_day"].items())),
        })
    out.sort(key=lambda x: -x["unmet_value_7d_inr"])
    return {"store_id": store_id, "category": category, "days": days, "totals": totals, "groups": out}


async def forecast_summary(store_id: str, category: Optional[str], days: int = 21) -> dict:
    rows = await forecast_rows(store_id)
    end = config.day_offset(days - 1)
    agg = {"sales_only": 0.0, "demand_sensed": 0.0, "lower": 0.0, "upper": 0.0}
    by_cat: dict[str, dict] = defaultdict(lambda: {"sales_only": 0.0, "demand_sensed": 0.0})
    n = 0
    for r in rows:
        if r["d"] > end or (category and r["category"] != category):
            continue
        v = float(r["v"] or 0)
        by_cat[r["category"]][r["variant"]] += v
        agg[r["variant"]] = agg.get(r["variant"], 0.0) + v
        if r["variant"] == "demand_sensed":
            agg["lower"] += float(r.get("lower") or 0)
            agg["upper"] += float(r.get("upper") or 0)
            n += 1
    so, ds = agg["sales_only"], agg["demand_sensed"]
    return {
        "store_id": store_id, "category": category, "horizon_days": days,
        "sales_only_units": round(so), "demand_sensed_units": round(ds),
        "gap_units": round(ds - so), "gap_pct": round((ds - so) / so * 100, 1) if so else None,
        "demand_sensed_range": [round(agg["lower"]), round(agg["upper"])] if n else None,
        "by_category": {k: {kk: round(vv) for kk, vv in v.items()} for k, v in by_cat.items()},
        "model": (rows[0].get("model") if rows else None),
    }


async def inventory_position(store_id: str, category: str, horizon_days: int = 21,
                             forecast: Optional[dict] = None, unmet: Optional[dict] = None) -> dict:
    """Per (sku, size) at the store: on hand, incoming, need over the horizon and shortfall."""
    prods = await catalog.products()
    cat_rows = await inv.inventory_for_category(category)
    here = [r for r in cat_rows if r.get("store_id") == store_id]
    try:
        vel = await sku_velocity(category)
    except Exception:
        vel = {}
    # SKU mix from chain-wide sales (robust to local stockouts)
    chain_units: dict[str, int] = defaultdict(int)
    for (sid, sku), v in vel.items():
        chain_units[sku] += v["units_28d"]
    total_chain = sum(chain_units.values()) or 0
    cat_skus = sorted({r["sku"] for r in cat_rows} | {s for s, p in prods.items() if p.get("category") == category})
    sizes_of = {s: (prods.get(s, {}).get("sizes") or ["FREE"]) for s in cat_skus}
    unmet_by_sku: dict[str, int] = defaultdict(int)
    if unmet:
        for g in unmet.get("groups", []):
            if g.get("sku"):
                unmet_by_sku[g["sku"]] += g["unmet_units_7d"]
    fc_units = (forecast or {}).get("demand_sensed_units")
    so_units = (forecast or {}).get("sales_only_units")
    items = []
    for sku in cat_skus:
        p = prods.get(sku, {})
        share = (chain_units.get(sku, 0) / total_chain) if total_chain else 1 / max(len(cat_skus), 1)
        local_units = (vel.get((store_id, sku)) or {}).get("units_28d", 0)
        local_so_days = (vel.get((store_id, sku)) or {}).get("stockout_days", 0)
        if fc_units:
            need_sku = fc_units * share
        else:
            need_sku = local_units / 28 * horizon_days
        # captured unmet asks extrapolated over the horizon add to the need when the item is out locally
        unmet7 = unmet_by_sku.get(sku, 0)
        need_sku = max(need_sku, unmet7 / 7 * horizon_days * 0.6)
        sizes = sizes_of[sku]
        for size in sizes:
            row = next((r for r in here if r["sku"] == sku and r.get("size") == size), None)
            on_hand = int((row or {}).get("on_hand") or 0)
            incoming = int((row or {}).get("incoming") or 0)
            eta = (row or {}).get("incoming_eta")
            rp = int((row or {}).get("reorder_point") or 0)
            need = need_sku / len(sizes)
            incoming_in_time = incoming if (eta and eta <= config.day_offset(horizon_days - 1)) else 0
            shortfall = max(0, math.ceil(need + rp * 0.5 - on_hand - incoming_in_time))
            items.append({
                "sku": sku, "size": size, "name": p.get("name"), "price_inr": int(p.get("price_inr") or 0),
                "on_hand": on_hand, "incoming": incoming, "incoming_eta": eta, "reorder_point": rp,
                "need_21d": round(need, 1), "shortfall": shortfall, "unmet_7d": unmet7 if len(sizes) == 1 else None,
                "local_units_28d": local_units, "local_stockout_days_28d": local_so_days,
            })
    items.sort(key=lambda x: (-(x["shortfall"] * x["price_inr"]), x["sku"]))
    out_now = sum(1 for i in items if i["on_hand"] <= 0)
    return {"store_id": store_id, "category": category, "horizon_days": horizon_days,
            "forecast_basis": "demand_sensed" if fc_units else "recent_sales",
            "category_need_21d": round(fc_units) if fc_units else None,
            "sales_only_21d": round(so_units) if so_units else None,
            "skus_out_of_stock": out_now, "positions": items}


async def transfer_options(store_id: str, category: str, skus: Optional[list[str]] = None,
                           horizon_days: int = 21) -> dict:
    """Surplus at other stores = on hand above that store's own reorder point (moving it does not
    trigger a reorder there). Same-state sources are flagged: intra-state branch transfers need no GST invoice."""
    cat_rows = await inv.inventory_for_category(category)
    try:
        vel = await sku_velocity(category)
    except Exception:
        vel = {}
    opts = []
    for r in cat_rows:
        sid = r.get("store_id")
        if sid == store_id or (skus and r.get("sku") not in skus):
            continue
        on_hand = int(r.get("on_hand") or 0)
        if on_hand <= 0:
            continue
        rp = int(r.get("reorder_point") or 0)
        surplus = on_hand - rp
        if surplus >= 2:
            sizes = len(set(x.get("size") for x in cat_rows if x.get("sku") == r.get("sku") and x.get("store_id") == sid)) or 1
            units_28d = (vel.get((sid, r["sku"])) or {}).get("units_28d")
            opts.append({"sku": r["sku"], "size": r.get("size"), "from_store_id": sid,
                         "from_store": config.store_name(sid), "on_hand": on_hand, "reorder_point": rp,
                         "surplus": surplus, "same_state": _state(sid) == _state(store_id),
                         "source_units_28d": round(units_28d / sizes) if units_28d is not None else None,
                         "distance_km": round(inv._distance_km(store_id, sid)) if sid != "ONLINE" else None})
    opts.sort(key=lambda o: (not o["same_state"], -o["surplus"]))
    return {"store_id": store_id, "category": category,
            "rule": "surplus = on_hand - reorder_point at the source store", "options": opts}


_STATE = {"CHN": "TN", "CBE": "TN", "BLR": "KA", "HYD": "TS", "ONLINE": "DC"}


def _state(store_id: str) -> str:
    return _STATE.get((store_id or "").split("-")[0], "?")


# ---------------------------------------------------------------------------
# Radar (GET /api/radar)
# ---------------------------------------------------------------------------


async def radar(store_id: str, category: Optional[str]) -> dict:
    import asyncio

    series_cat = category or "sarees"
    sigs_task = asyncio.create_task(signals_for_store(store_id))
    inv_task = asyncio.create_task(inv.inventory_for_store(store_id))
    fc_task = asyncio.create_task(forecast_rows(store_id))
    sales_task = asyncio.create_task(sales_by_day(store_id))
    sigs = await sigs_task
    inv_rows = await inv_task
    try:
        fc = await fc_task
    except Exception:
        fc = None
    try:
        sales = await sales_task
    except Exception:
        sales = None

    unmet = await unmet_groups(store_id, category, 7)
    tot = unmet["totals"]
    stockouts = sum(1 for r in inv_rows if int(r.get("on_hand") or 0) <= 0 and (category is None or r.get("category") == category))
    today_sigs = sum(1 for r in sigs if str(r.get("date"))[:10] == config.DEMO_TODAY)
    gap21 = 0.0
    if fc:
        for r in fc:
            if r["d"] <= config.day_offset(20) and (category is None or r["category"] == category):
                gap21 += float(r["v"] or 0) * (1 if r["variant"] == "demand_sensed" else -1)

    onhand_by_sku: dict[str, int] = defaultdict(int)
    for r in inv_rows:
        onhand_by_sku[r["sku"]] += max(int(r.get("on_hand") or 0), 0)
    prods = await catalog.products()
    top = []
    for g in unmet["groups"][:6]:
        if g["sku"]:
            oh = onhand_by_sku.get(g["sku"], 0)
        else:
            color = (g["attributes"].get("color") or "").lower()
            oh = sum(v for s, v in onhand_by_sku.items() if prods.get(s, {}).get("category") == g["category"]
                     and (not color or color in (prods.get(s, {}).get("color") or "").lower()))
        top.append({"category": g["category"], "sku": g["sku"], "label": g["label"], "attributes": g["attributes"],
                    "unmet_units_7d": g["unmet_units_7d"], "unmet_value_7d_inr": g["unmet_value_7d_inr"],
                    "on_hand": oh, "trend": g["trend"]})

    # series: 56 past days + 42 forecast days
    actual = {r["d"]: int(r["u"] or 0) for r in (sales or []) if r["category"] == series_cat}
    fcs: dict[str, dict] = defaultdict(dict)
    for r in fc or []:
        if r["category"] == series_cat:
            fcs[r["d"]][r["variant"]] = r
    unmet_day: dict[str, int] = defaultdict(int)
    for r in sigs:
        if r.get("category") == series_cat and r.get("outcome") == "unmet":
            unmet_day[str(r.get("date"))[:10]] += int(r.get("quantity") or 1)
    series = []
    for i in range(-56, 42):
        d = config.day_offset(i)
        f = fcs.get(d, {})
        so, ds = f.get("sales_only"), f.get("demand_sensed")
        series.append({
            "date": d,
            "actual_units": (actual.get(d, 0) if sales is not None else None) if i < 0 else None,
            "forecast_sales_only": round(float(so["v"]), 2) if so else None,
            "forecast_demand_sensed": round(float(ds["v"]), 2) if ds else None,
            "lower": round(float(ds["lower"]), 2) if ds and ds.get("lower") is not None else None,
            "upper": round(float(ds["upper"]), 2) if ds and ds.get("upper") is not None else None,
            "unmet_units": unmet_day.get(d, 0) if i <= 0 else None,
        })

    recent = [r for r in sigs][:20]
    revenue_protected = await _revenue_protected(store_id)
    return {
        "store_id": store_id,
        "as_of": config.DEMO_TODAY,
        "days_to_diwali": config.DAYS_TO_DIWALI,
        "kpis": {
            "unmet_value_7d_inr": int(tot["unmet_value_inr"]),
            "unmet_units_7d": int(tot["unmet_units"]),
            "stockouts_now": int(stockouts),
            "signals_today": int(today_sigs),
            "forecast_gap_units_21d": int(round(gap21)),
            "revenue_protected_inr": int(revenue_protected),
        },
        "top_gaps": top,
        "assortment_gaps": assortment_gaps(sigs),  # store-wide: what the store does not sell
        "series": series,
        "recent_signals": recent,
    }


async def _revenue_protected(store_id: str) -> int:
    """§9.7: sum of expected_revenue_protected_inr over executed actions for the store (reset deletes actions)."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    total = 0
    try:
        # store_id on an action is its destination store; approve sets status "executed"
        q = fs().collection("actions").where(filter=FieldFilter("store_id", "==", store_id))
        async for d in q.stream():
            a = d.to_dict() or {}
            if a.get("status") in ("executed", "approved"):
                total += int(a.get("expected_revenue_protected_inr") or 0)
    except Exception as e:
        log("WARNING", "revenue protected query failed", error=type(e).__name__, detail=str(e)[:160])
    return total


_LOOKED_FOR = re.compile(r"^\s*(?:looked|asked|searched|wanted|came)\s+(?:for\s+)?(?:an?\s+|the\s+)?(.+?)(?:;|,| but | - |$)", re.I)


def gap_label(r: dict) -> str:
    """Label for a not_carried ask: attributes.item, else the item in the summary ('Looked for X; not carried'),
    else subcategory / attribute combination, else the category."""
    a = r.get("attributes") or {}
    item = (a.get("item") or "").strip()
    if not item:
        m = _LOOKED_FOR.match(r.get("summary") or "")
        if m and 3 <= len(m.group(1)) <= 60:
            item = m.group(1).strip()
    if not item:
        item = " ".join(x for x in [a.get("color", ""), a.get("material", ""), a.get("subcategory", ""),
                                    (f"size {a['size']}" if a.get("size") else "")] if x)
        cat = config.CATEGORY_LABEL.get(r.get("category"), r.get("category") or "").lower()
        item = f"{cat} ({item})" if item else cat
    item = re.sub(r"\s+", " ", item).strip()
    return item[:1].upper() + item[1:]


def assortment_gaps(sigs: list[dict], category: Optional[str] = None, days: int = 7, limit: int = 5) -> list[dict]:
    """§9.7: what customers ask for that the store does not sell (not_carried signals, last 7 days)."""
    groups: dict[tuple, dict] = {}
    for r in sigs:
        if r.get("reason") != "not_carried" or not _in_window(r, days):
            continue
        if category and r.get("category") != category:
            continue
        label = gap_label(r)
        key = (r.get("category"), label.lower())
        g = groups.setdefault(key, {"label": label, "category": r.get("category"),
                                    "asks_7d": 0, "est_value_7d_inr": 0, "examples": []})
        g["asks_7d"] += int(r.get("quantity") or 1)
        g["est_value_7d_inr"] += int(r.get("est_value_inr") or 0)
        ex = (r.get("summary") or "").strip()
        if ex and ex not in g["examples"] and len(g["examples"]) < 3:
            g["examples"].append(ex[:120])
    out = sorted(groups.values(), key=lambda g: (-g["asks_7d"], -g["est_value_7d_inr"]))
    return out[:limit]
