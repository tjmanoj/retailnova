"""Collect the headline numbers used by the deck and README into evals/RESULTS.json.

Sources:
  evals/backtest_summary.json   - backtest (synthetic, true demand known)
  evals/concierge_results.json  - concierge eval against the deployed API
  --measure-plan                - optionally time /api/plan on the deployed API (3 runs, median)

Cost uses measured average tokens per model call (Cloud Monitoring, 18 Oct 2026) and list prices below.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://retailnova-api-569310655517.asia-south1.run.app"

USD_INR = 84.0
# Average tokens per call measured from Cloud Monitoring token_count / invocation_count on 18 Oct 2026.
TOKENS = {"flash": {"in": 2186, "out": 240}, "lite": {"in": 1287, "out": 122}}
# USD per 1M tokens (list prices).
PRICE = {"flash": {"in": 1.50, "out": 7.50}, "lite": {"in": 0.30, "out": 2.50}}
# Calls per shopper turn: tool loop on Flash (about 2) + signal extraction and hedging on Flash-Lite (about 1.5).
CALLS_PER_TURN = {"flash": 2.0, "lite": 1.5}


def pct(agg: dict, key: str) -> float | None:
    v = agg.get(key)
    return round(v["rate"] * 100, 1) if isinstance(v, dict) and "rate" in v else None


def turn_cost_usd() -> float:
    total = 0.0
    for m, n in CALLS_PER_TURN.items():
        t, p = TOKENS[m], PRICE[m]
        total += n * (t["in"] * p["in"] + t["out"] * p["out"]) / 1e6
    return total


def measure_plan(runs: int = 3) -> float:
    times = []
    for _ in range(runs):
        body = json.dumps({"store_id": "CHN-TNG", "category": "sarees", "session_id": str(uuid.uuid4())}).encode()
        req = urllib.request.Request(API + "/api/plan", data=body, headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                if raw.startswith(b"event: done"):
                    break
        times.append(time.time() - t0)
    return round(statistics.median(times), 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure-plan", action="store_true")
    args = ap.parse_args()

    bt = json.loads((ROOT / "backtest_summary.json").read_text())
    cr = json.loads((ROOT / "concierge_results.json").read_text())
    agg = cr["aggregates"]
    lat = agg.get("latency", {})

    per_turn_inr = turn_cost_usd() * USD_INR
    pilot_turns = 100_000
    results = {
        "backtest": {k: bt[k] for k in (
            "wape_sales_only", "wape_demand_sensed", "stockout_days_sales_only", "stockout_days_demand_sensed",
            "lost_revenue_sales_only_inr", "lost_revenue_demand_sensed_inr", "lost_revenue_reduction_pct", "sensitivity_note")},
        "concierge": {
            "n_cases": agg.get("case_pass_rate", {}).get("den"),
            "case_pass_rate": pct(agg, "case_pass_rate"),
            "grounding_rate": pct(agg, "grounding_rate"),
            "stock_grounding": pct(agg, "stock_grounding"),
            "constraint_adherence": pct(agg, "constraint_adherence"),
            "refusal_accuracy": pct(agg, "refusal_accuracy"),
            "oos_honesty": pct(agg, "oos_honesty"),
            "signal_accuracy": pct(agg, "signal_accuracy"),
        },
        "latency": {
            # Sequential 10-turn benchmark, wall clock (what a user feels); falls back to the case run.
            "chat_p50_s": round(cr.get("latency_bench_summary", {}).get("wall_total_s", {}).get("p50")
                                or lat.get("done_latency_ms", {}).get("p50", 0) / 1000, 1) or None,
            "chat_p95_s": round(cr.get("latency_bench_summary", {}).get("wall_total_s", {}).get("p95")
                                or lat.get("done_latency_ms", {}).get("p95", 0) / 1000, 1) or None,
            "first_event_p50_s": lat.get("first_event_s", {}).get("p50"),
            "plan_s": measure_plan() if args.measure_plan else None,
        },
        "cost": {
            "per_1k_chats_inr": round(per_turn_inr * 1000, -1),
            "pilot_gemini_inr": round(per_turn_inr * pilot_turns, -3),
            "pilot_run_inr": 4000,      # 1 warm + autoscaled Cloud Run instances, Hosting egress (estimate)
            "pilot_data_inr": 3000,     # Firestore reads/writes + BigQuery scheduled forecasts (estimate)
            "proto_gemini_inr": 500,    # build + test traffic to date, incl. 75 catalog images (estimate from token counts)
            "proto_run_inr": 100,
            "proto_data_inr": 50,
        },
        "notes": "Backtest is a simulation (synthetic data). Concierge metrics from the deployed API. Cost: measured tokens x list price.",
    }
    c = results["cost"]
    c["pilot_total_inr"] = c["pilot_gemini_inr"] + c["pilot_run_inr"] + c["pilot_data_inr"]
    c["proto_total_inr"] = c["proto_gemini_inr"] + c["proto_run_inr"] + c["proto_data_inr"]
    # Prefer the conservative figures when a separate prod latency benchmark exists (evals/latency_bench.py).
    lb = ROOT / "latency_bench.json"
    if lb.exists():
        b = json.loads(lb.read_text())
        L = results["latency"]
        L["chat_p50_s"] = round(max(L["chat_p50_s"] or 0, b["wall_total_s"]["p50"]), 1)
        L["chat_p95_s"] = round(max(L["chat_p95_s"] or 0, b["wall_total_s"]["p95"]), 1)
    if results["latency"]["plan_s"] is None:
        prev = ROOT / "RESULTS.json"
        if prev.exists():
            results["latency"]["plan_s"] = json.loads(prev.read_text()).get("latency", {}).get("plan_s")
    (ROOT / "RESULTS.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
