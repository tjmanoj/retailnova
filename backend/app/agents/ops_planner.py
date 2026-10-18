"""Ops Planner: parallel data fan-out -> Gemini structured proposals -> persisted actions (SSE)."""
from __future__ import annotations

import asyncio
import json
import math
import re
import time
from typing import AsyncIterator, Literal, Optional

from pydantic import BaseModel, Field

from .. import config
from ..db import BQUnavailable, fs, log, new_id, now_iso
from ..llm import genai_client, generate_json
from ..models import ActionProposal, PlanStep
from ..sse import EventChannel
from ..tools import catalog, ops

STEP_LABELS = {
    "forecast": "Forecast (BigQuery TimesFM)",
    "unmet_demand": "Unmet demand from conversations",
    "inventory": "Inventory position",
    "transfers": "Transfer options",
    "trends": "Festive trend check (Google Search)",
    "planner": "Drafting actions",
}


class EvidenceDraft(BaseModel):
    kind: Literal["forecast", "signals", "inventory", "trend"]
    text: str
    value: Optional[float] = None


class ProposalDraft(BaseModel):
    type: Literal["transfer", "reorder"]
    sku: str
    size: str = "FREE"
    quantity: int
    from_store_id: Optional[str] = None
    rationale: str
    evidence: list[EvidenceDraft] = []
    confidence: float = Field(default=0.7, ge=0, le=1)


class PlanDraft(BaseModel):
    summary: str
    proposals: list[ProposalDraft]


PLANNER_SYSTEM = """You are the Ops Planner for Nova Bazaar, an Indian festive retailer. A store manager must get the right
stock into the store before Diwali (2026-11-08). You get data gathered from BigQuery forecasts, captured unmet shopper
demand, live inventory and transfer options. Propose 2-4 concrete actions:
- transfer: move stock from another store's surplus (arrives in 2 days). Prefer same-state sources (no GST invoice for
  intra-state branch transfers). Quantity must not exceed that option's surplus.
- reorder: order from the supplier for the remaining shortfall (arrives after supplier lead days; must land before Diwali).
Prioritise SKUs with the largest revenue at risk (shortfall x price) and strong, rising unmet demand. When a transfer
covers only part of a shortfall, also propose a reorder for the rest. Use only SKUs, sizes, stores and numbers present in
the data. Each rationale: one or two sentences, <= 280 chars, citing numbers. Evidence: 2-3 items (kinds: forecast,
signals, inventory) with the key number in `value`. Summary: 2-3 sentences for the manager, plain English."""


def _infer_category(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    for word, cat in [("saree", "sarees"), ("sari", "sarees"), ("pudavai", "sarees"), ("kurta set", "kurta_sets"),
                      ("women", "kurta_sets"), ("men", "mens_ethnic"), ("kurta", "mens_ethnic"), ("decor", "home_decor"),
                      ("diya", "home_decor"), ("gift", "gifting"), ("footwear", "footwear"), ("jutti", "footwear"),
                      ("shoe", "footwear")]:
        if word in t:
            return cat
    return None


def _step(id_: str, status: str, summary: str = "", data: Optional[dict] = None,
          started_at: Optional[str] = None) -> dict:
    return PlanStep(id=id_, label=STEP_LABELS[id_], status=status, summary=summary, data=data,
                    started_at=started_at, finished_at=None if status == "running" else now_iso()).model_dump()


def _inr(v: float) -> str:
    v = int(round(v))
    if v >= 100000:
        return f"₹{v / 100000:.1f}L"
    if v >= 1000:
        return f"₹{v / 1000:.0f}k"
    return f"₹{v}"


def run_plan(store_id: str, category: Optional[str], horizon_days: int, question: Optional[str]) -> AsyncIterator[str]:
    ch = EventChannel()
    asyncio.create_task(_produce(ch, store_id, category, horizon_days, question))
    return ch.stream()


async def _produce(ch: EventChannel, store_id: str, category: Optional[str], horizon_days: int,
                   question: Optional[str]) -> None:
    t0 = time.monotonic()
    plan_id = new_id("plan")
    steps: dict[str, dict] = {}
    model_used = config.MODEL_AGENT
    try:
        category = category or _infer_category(question)
        if not category:
            try:
                g = await ops.unmet_groups(store_id, None, 7)
                category = g["groups"][0]["category"] if g["groups"] else "sarees"
            except Exception:
                category = "sarees"
        horizon_days = max(7, min(int(horizon_days or 21), 42))

        def emit(id_, status, summary="", data=None):
            started = steps.get(id_, {}).get("started_at") or now_iso()
            s = _step(id_, status, summary, data, started_at=started)
            steps[id_] = s
            ch.emit("step", {"step": s})

        for sid in ("forecast", "unmet_demand", "inventory", "transfers"):
            emit(sid, "running")
        if config.ENABLE_TRENDS:
            emit("trends", "running")
        else:
            emit("trends", "skipped", "Market-trend check with Google Search is off in this demo.")

        results: dict[str, Optional[dict]] = {}

        async def s_forecast():
            try:
                f = await ops.forecast_summary(store_id, category, horizon_days)
                results["forecast"] = f
                if not f["sales_only_units"] and not f["demand_sensed_units"]:
                    emit("forecast", "error", "No forecast rows found for this store and category.")
                    return
                emit("forecast", "done",
                     f"Next {horizon_days} days: sales-only {f['sales_only_units']} units vs demand-sensed "
                     f"{f['demand_sensed_units']} ({'+' if f['gap_units'] >= 0 else ''}{f['gap_units']} units).",
                     {k: f[k] for k in ("sales_only_units", "demand_sensed_units", "gap_units", "gap_pct", "demand_sensed_range")})
            except (BQUnavailable, asyncio.TimeoutError) as e:
                results["forecast"] = None
                emit("forecast", "error", "Forecast table is not available yet; planning from recent sales and signals.")
                log("WARNING", "forecast step unavailable", detail=str(e)[:160])
            except Exception as e:
                results["forecast"] = None
                emit("forecast", "error", "Could not read forecasts.")
                log("WARNING", "forecast step failed", error=type(e).__name__, detail=str(e)[:160])

        async def s_unmet():
            try:
                u = await ops.unmet_groups(store_id, category, 7)
                results["unmet"] = u
                tot = u["totals"]
                top = u["groups"][0] if u["groups"] else None
                summ = f"{tot['unmet_units']} unmet units in 7 days ({_inr(tot['unmet_value_inr'])})"
                if top:
                    summ += f", led by {top['label']} ({top['unmet_units_7d']}, {top['trend']})."
                emit("unmet_demand", "done", summ,
                     {"totals": tot, "top": [{k: g[k] for k in ("sku", "label", "unmet_units_7d", "unmet_value_7d_inr", "trend")} for g in u["groups"][:5]]})
            except Exception as e:
                results["unmet"] = None
                emit("unmet_demand", "error", "Could not read demand signals.")
                log("WARNING", "unmet step failed", error=type(e).__name__, detail=str(e)[:160])

        async def s_inventory():
            try:
                # shares the cached forecast / signal loaders with the other steps
                try:
                    f = await ops.forecast_summary(store_id, category, horizon_days)
                except Exception:
                    f = None
                u = await ops.unmet_groups(store_id, category, 7)
                p = await ops.inventory_position(store_id, category, horizon_days, f, u)
                results["inventory"] = p
                short = [x for x in p["positions"] if x["shortfall"] > 0]
                top = short[0] if short else None
                summ = f"{p['skus_out_of_stock']} SKU-sizes out of stock; {len(short)} short for the next {horizon_days} days"
                if top:
                    summ += f"; {top['sku']}: {top['on_hand']} on hand vs {round(top['need_21d'])} needed."
                emit("inventory", "done", summ,
                     {"out_of_stock": p["skus_out_of_stock"],
                      "top_shortfalls": [{k: x[k] for k in ("sku", "size", "on_hand", "incoming", "need_21d", "shortfall")} for x in short[:5]]})
            except Exception as e:
                results["inventory"] = None
                emit("inventory", "error", "Could not read inventory.")
                log("WARNING", "inventory step failed", error=type(e).__name__, detail=str(e)[:200])

        async def s_transfers():
            try:
                t = await ops.transfer_options(store_id, category, None, horizon_days)
                results["transfers"] = t
                opts = t["options"]
                if opts:
                    o = opts[0]
                    summ = f"{len(opts)} surplus options; best: {o['surplus']} x {o['sku']} at {o['from_store']}" + \
                           (" (same state)." if o["same_state"] else ".")
                else:
                    summ = "No other store has surplus above its reorder point."
                emit("transfers", "done", summ, {"options": opts[:6]})
            except Exception as e:
                results["transfers"] = None
                emit("transfers", "error", "Could not compute transfer options.")
                log("WARNING", "transfers step failed", error=type(e).__name__, detail=str(e)[:160])

        async def s_trends():
            if not config.ENABLE_TRENDS:
                return
            try:
                from google.genai import types

                r = await asyncio.wait_for(genai_client().aio.models.generate_content(
                    model=config.MODEL_AGENT,
                    contents=f"In 2 short sentences: what {config.CATEGORY_LABEL.get(category, category).lower()} "
                             f"styles and colours are trending for Diwali 2026 in South India?",
                    config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())],
                                                       thinking_config=types.ThinkingConfig(thinking_level="LOW"))), 12)
                results["trends"] = {"text": (r.text or "")[:400]}
                emit("trends", "done", (r.text or "")[:200])
            except Exception as e:
                emit("trends", "error", "Trend check unavailable right now.")
                log("WARNING", "trends step failed", error=type(e).__name__)

        await asyncio.gather(s_forecast(), s_unmet(), s_inventory(), s_transfers(), s_trends())

        # ---- planner ----
        emit("planner", "running")
        proposals, summary, model_used = await _plan(store_id, category, horizon_days, question, results)
        n_t = sum(1 for p in proposals if p["type"] == "transfer")
        n_r = sum(1 for p in proposals if p["type"] == "reorder")
        emit("planner", "done", f"{len(proposals)} actions proposed ({n_t} transfer, {n_r} reorder).",
             {"model": model_used})

        # persist
        created = now_iso()
        actions = []
        for p in proposals:
            a = ActionProposal(plan_id=plan_id, created_at=created, status="proposed", store_id=store_id,
                               category=category, **p)
            actions.append(a.model_dump())
        try:
            batch = fs().batch()
            for a in actions:
                batch.set(fs().collection("actions").document(a["action_id"]), a)
            batch.set(fs().collection("plans").document(plan_id), {
                "plan_id": plan_id, "store_id": store_id, "category": category, "question": question,
                "created_at": created, "steps": list(steps.values()), "proposal_ids": [a["action_id"] for a in actions],
                "summary": summary, "model": model_used,
            })
            await batch.commit()
        except Exception as e:
            log("ERROR", "plan persist failed", error=type(e).__name__, detail=str(e)[:200])
            ch.emit("error", {"message": "Plan was generated but could not be saved. Please retry.", "retryable": True})
        for a in actions:
            ch.emit("proposal", {"proposal": a})
        ch.emit("text", {"delta": summary})
    except Exception as e:
        log("ERROR", "plan failed", error=type(e).__name__, detail=str(e)[:300])
        ch.emit("error", {"message": "Sorry, the plan could not be completed. Please try again.", "retryable": True})
    latency = int((time.monotonic() - t0) * 1000)
    ch.emit("done", {"latency_ms": latency, "model": model_used, "plan_id": plan_id})
    ch.close()
    log("INFO", "plan", route="/api/plan", latency_ms=latency, store_id=store_id, category=category, model=model_used)


async def _plan(store_id: str, category: str, horizon: int, question: Optional[str],
                results: dict) -> tuple[list[dict], str, str]:
    prods = await catalog.products()
    inv_pos = (results.get("inventory") or {}).get("positions") or []
    short = [x for x in inv_pos if x["shortfall"] > 0][:8]
    unmet = results.get("unmet") or {"groups": [], "totals": {}}
    tr = (results.get("transfers") or {}).get("options") or []
    focus_skus = {x["sku"] for x in short} | {g["sku"] for g in unmet["groups"][:5] if g.get("sku")}
    tr_focus = [o for o in tr if o["sku"] in focus_skus][:12]
    lead = config.SUPPLIER_LEAD_DAYS.get(category, 7)
    data = {
        "today": config.DEMO_TODAY, "diwali": config.DIWALI_DATE, "store": f"{config.store_name(store_id)} ({store_id})",
        "category": category, "horizon_days": horizon, "transfer_days": config.TRANSFER_DAYS,
        "supplier_lead_days": lead, "manager_question": question,
        "forecast": {k: v for k, v in (results.get("forecast") or {}).items() if k != "by_category"} or "unavailable",
        "unmet_demand_7d": {"totals": unmet.get("totals"),
                            "top": [{k: g.get(k) for k in ("sku", "label", "attributes", "unmet_units_7d", "unmet_value_7d_inr", "trend", "top_reason")}
                                    for g in unmet["groups"][:6]]},
        "shortfalls": [{k: x[k] for k in ("sku", "size", "name", "price_inr", "on_hand", "incoming", "incoming_eta",
                                           "reorder_point", "need_21d", "shortfall", "unmet_7d")} for x in short],
        "transfer_options": tr_focus,
        "trend": (results.get("trends") or {}).get("text"),
    }
    model_used = config.MODEL_AGENT
    draft = None
    try:
        draft, model_used = await asyncio.wait_for(
            generate_json(json.dumps(data, ensure_ascii=False, default=str), PlanDraft,
                          model=config.MODEL_AGENT, timeout=config.PLANNER_TIMEOUT_S,
                          system_instruction=PLANNER_SYSTEM, temperature=0.2),
            config.PLANNER_TOTAL_TIMEOUT_S)
    except Exception as e:
        log("WARNING", "planner model failed; using rule-based plan", error=type(e).__name__)
    proposals = _validate(draft, store_id, category, short, tr_focus or tr, prods, unmet, results, horizon) if draft else []
    summary = (draft or {}).get("summary") if draft else None
    if not proposals:
        proposals = _rule_based(store_id, category, short, tr, prods, unmet, results, horizon)
        model_used = "rules" if not draft else model_used
        summary = summary or None
    if not summary:
        tot = sum(p["expected_revenue_protected_inr"] for p in proposals)
        summary = (f"{len(proposals)} actions for {config.CATEGORY_LABEL.get(category, category).lower()} at "
                   f"{config.store_name(store_id)} protect about {_inr(tot)} before Diwali.")
    return proposals, summary, model_used


def _evidence_defaults(sku: str, size: str, pos: Optional[dict], unmet: dict, results: dict) -> list[dict]:
    ev = []
    g = next((g for g in unmet.get("groups", []) if g.get("sku") == sku), None)
    if g:
        ev.append({"kind": "signals", "text": f"{g['unmet_units_7d']} unmet asks in 7 days ({g['trend']})", "value": float(g["unmet_units_7d"])})
    if pos:
        ev.append({"kind": "inventory", "text": f"{pos['on_hand']} on hand vs {round(pos['need_21d'])} needed in 21 days", "value": float(pos["on_hand"])})
    f = results.get("forecast")
    if f and f.get("gap_units") is not None:
        ev.append({"kind": "forecast", "text": f"Demand-sensed forecast is {f['gap_units']:+d} units vs sales-only", "value": float(f["gap_units"])})
    return ev[:3]


def _revenue(qty: int, price: int, need: float, arrive_day: int, horizon: int) -> int:
    covered = max(0.0, need * max(horizon - arrive_day, 0) / horizon)
    return int(min(qty, math.ceil(covered) if need else qty) * price)


def _validate(draft: dict, store_id: str, category: str, short: list[dict], tr: list[dict], prods: dict,
              unmet: dict, results: dict, horizon: int) -> list[dict]:
    out = []
    used_surplus: dict[tuple, int] = {}
    pos_by = {(x["sku"], x["size"]): x for x in short}
    all_pos = {(x["sku"], x["size"]): x for x in (results.get("inventory") or {}).get("positions", [])}
    lead = config.SUPPLIER_LEAD_DAYS.get(category, 7)
    for p in (draft.get("proposals") or [])[:5]:
        try:
            d = ProposalDraft(**p)
        except Exception:
            continue
        sku = d.sku.upper().strip()
        prod = prods.get(sku)
        if not prod or prod.get("category") != category:
            continue
        size = (d.size or "FREE").upper().strip()
        if size not in (prod.get("sizes") or ["FREE"]):
            size = (prod.get("sizes") or ["FREE"])[0]
        qty = int(d.quantity or 0)
        if qty <= 0:
            continue
        pos = pos_by.get((sku, size)) or all_pos.get((sku, size))
        need = float(pos["need_21d"]) if pos else 0.0
        price = int(prod.get("price_inr") or 0)
        if d.type == "transfer":
            cands = [o for o in tr if o["sku"] == sku and o["size"] == size]
            o = next((o for o in cands if o["from_store_id"] == (d.from_store_id or "").upper()), None) or (cands[0] if cands else None)
            if not o:
                continue
            key = (sku, size, o["from_store_id"])
            avail = o["surplus"] - used_surplus.get(key, 0)
            qty = min(qty, avail)
            if qty <= 0:
                continue
            used_surplus[key] = used_surplus.get(key, 0) + qty
            out.append({
                "action_id": new_id("act"), "type": "transfer", "sku": sku, "size": size, "quantity": qty,
                "from_store_id": o["from_store_id"], "supplier_lead_days": None,
                "eta_date": config.day_offset(config.TRANSFER_DAYS),
                "rationale": d.rationale[:300], "evidence": [e.model_dump() for e in d.evidence][:3] or _evidence_defaults(sku, size, pos, unmet, results),
                "confidence": round(float(d.confidence), 2),
                "expected_revenue_protected_inr": _revenue(qty, price, need, config.TRANSFER_DAYS, horizon),
            })
        else:
            qty = min(qty, 500)
            out.append({
                "action_id": new_id("act"), "type": "reorder", "sku": sku, "size": size, "quantity": qty,
                "from_store_id": None, "supplier_lead_days": lead, "eta_date": config.day_offset(lead),
                "rationale": d.rationale[:300], "evidence": [e.model_dump() for e in d.evidence][:3] or _evidence_defaults(sku, size, pos, unmet, results),
                "confidence": round(float(d.confidence), 2),
                "expected_revenue_protected_inr": _revenue(qty, price, need, lead, horizon),
            })
    return out


def _rule_based(store_id: str, category: str, short: list[dict], tr: list[dict], prods: dict,
                unmet: dict, results: dict, horizon: int) -> list[dict]:
    """Deterministic fallback: for the top shortfalls, transfer same-state surplus, reorder the rest."""
    out = []
    lead = config.SUPPLIER_LEAD_DAYS.get(category, 7)
    unmet_skus = [g["sku"] for g in unmet.get("groups", []) if g.get("sku")]
    ranked = sorted(short, key=lambda x: (x["sku"] not in unmet_skus[:3], -(x["shortfall"] * x["price_inr"])))
    for pos in ranked[:2]:
        sku, size, gap = pos["sku"], pos["size"], pos["shortfall"]
        price = pos["price_inr"]
        cands = [o for o in tr if o["sku"] == sku and o["size"] == size]
        if cands:
            o = cands[0]
            q = min(o["surplus"], gap)
            if q > 0:
                out.append({"action_id": new_id("act"), "type": "transfer", "sku": sku, "size": size, "quantity": q,
                            "from_store_id": o["from_store_id"], "supplier_lead_days": None,
                            "eta_date": config.day_offset(config.TRANSFER_DAYS),
                            "rationale": f"Move {q} spare units from {o['from_store']} (above its reorder point) to cover "
                                         f"the immediate gap at {config.store_name(store_id)}."[:300],
                            "evidence": _evidence_defaults(sku, size, pos, unmet, results), "confidence": 0.75,
                            "expected_revenue_protected_inr": _revenue(q, price, pos["need_21d"], config.TRANSFER_DAYS, horizon)})
                gap -= q
        if gap > 0:
            q = int(math.ceil(gap / 5) * 5)
            out.append({"action_id": new_id("act"), "type": "reorder", "sku": sku, "size": size, "quantity": q,
                        "from_store_id": None, "supplier_lead_days": lead, "eta_date": config.day_offset(lead),
                        "rationale": f"Reorder {q} units to cover the remaining {horizon}-day shortfall; arrives "
                                     f"{config.day_offset(lead)}, before Diwali."[:300],
                        "evidence": _evidence_defaults(sku, size, pos, unmet, results), "confidence": 0.7,
                        "expected_revenue_protected_inr": _revenue(q, price, pos["need_21d"], lead, horizon)})
    return out
