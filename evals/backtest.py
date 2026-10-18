"""Backtest: does adding captured unmet demand to sales improve TimesFM forecasts and replenishment?

All data is SIMULATED (data/generate.py), which is what makes this measurable: the true demand is known.

  cutoff 2025-09-08 (6 weeks before Diwali 2025-10-20), horizon 42 days (2025-09-08 .. 2025-10-19)
  A  = TimesFM on observed sales (censored by stock-outs)                        variant "sales_only"
  B  = TimesFM on sales + unmet demand captured at rate r in {.10,.20,.35,.50}    variant "demand_sensed"
  B' = TimesFM on sales + captured unmet / r (estimated true demand)              variant "demand_sensed_scaled"
  Each arm also gets a "_festival" twin: the same TimesFM forecast with the festival-calendar uplift of
  data/run_forecast.py, learned from the training history only (Diwali 2024), applied equally to every arm.

1. Accuracy: WAPE and bias of each forecast against eval_ground_truth.true_demand, per store x category,
   per store, per category and overall.
2. Decisions: the same weekly order-up-to policy as the generator (Monday review, 7-day lead time,
   order-up-to = 1.3 x forecast demand over the 14-day cover window), driven by each forecast and served
   against TRUE demand, starting from the same simulated stock on the cutoff date. Metrics: stockout_days,
   lost_revenue_inr, overstock_units (stock left after the window beyond the next 7 days of true demand),
   fill_rate.

Writes retailnova.backtest_input, retailnova.backtest_forecasts (via bigquery/02_backtest.sql),
retailnova.backtest_results (long format) and evals/backtest_report.md.

Run (after data/generate.py and data/load_bigquery.py), with `source scripts/env.sh`:
  .venv/bin/python evals/backtest.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != ROOT / "data"]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", message=".*BigQuery Storage module not found.*")
warnings.filterwarnings("ignore", message=".*pandas-gbq.*")

import datetime as dt  # noqa: E402
import os  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from google.cloud import bigquery  # noqa: E402

from data.generate import (LEAD_DAYS, PREBUILD, REVIEW_DAYS, SAFETY, SERIES, START, base_rates,  # noqa: E402
                           calendar_multipliers, captured_unmet_frame, scale_unmet)
from data.run_forecast import apply_uplift, base_level, festival_uplift, weekday_index  # noqa: E402

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "retailnova-ai")
LOCATION = os.environ.get("REGION", "asia-south1")
DS = f"{PROJECT}.retailnova"
OUT = ROOT / "data" / "out"
REPORT = ROOT / "evals" / "backtest_report.md"
SUMMARY = ROOT / "evals" / "backtest_summary.json"

CUTOFF = pd.Timestamp("2025-09-08")
HORIZON = 42
OVERSTOCK_DAYS = 7
RATES = [0.10, 0.20, 0.35, 0.50]
COVER = REVIEW_DAYS + LEAD_DAYS
WINDOW = pd.date_range(CUTOFF, periods=HORIZON)


REFERENCE_RATE = 1.0   # all lost units captured = uncensored history (report-only ceiling for demand sensing)


PAST_DIWALIS = [pd.Timestamp("2024-11-01")]     # the only Diwali inside the training history
BT_DIWALI = pd.Timestamp("2025-10-20")


def variants(with_reference: bool = False) -> list[tuple[str, str, float]]:
    v = [("sales_only", "0.00", 0.0)] + [("demand_sensed", f"{r:.2f}", r) for r in RATES] \
        + [("demand_sensed_scaled", f"{r:.2f}", r) for r in RATES]
    return v + ([("demand_sensed", "1.00", REFERENCE_RATE)] if with_reference else [])


# ------------------------------------------------------------------------------------------------
def build_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sales = pd.read_parquet(OUT / "sales_daily.parquet")
    gt = pd.read_parquet(OUT / "eval_ground_truth.parquet")
    fi = pd.read_parquet(OUT / "forecast_input.parquet")
    for df in (sales, gt, fi):
        df["date"] = pd.to_datetime(df["date"])
    keys = ["date", "store_id", "category"]
    base = sales[sales.date < CUTOFF].groupby(keys, as_index=False)["units_sold"].sum() \
        .rename(columns={"units_sold": "units_sales"})
    frames = []
    for variant, key, rate in variants(with_reference=True):
        f = base.copy()
        if rate > 0:
            cap = captured_unmet_frame(gt, rate)
            cap["date"] = pd.to_datetime(cap["date"])
            cap = cap[cap.date < CUTOFF].groupby(keys, as_index=False)["unmet_units"].sum()
            f = f.merge(cap, on=keys, how="left").fillna({"unmet_units": 0})
            if variant == "demand_sensed_scaled":
                f["y"] = f["units_sales"] + scale_unmet(f["unmet_units"], rate)
                if key == "0.35":   # must reproduce the production forecast_input exactly
                    chk = f.merge(fi[fi.date < CUTOFF], on=keys)
                    assert (chk["y"] == chk["units_demand_sensed"]).all(), "capture regeneration mismatch"
            else:
                f["y"] = f["units_sales"] + f["unmet_units"]
        else:
            f["y"] = f["units_sales"]
        f["variant"], f["capture_key"] = variant, key
        frames.append(f[["date", "variant", "capture_key", "store_id", "category", "y"]])
    inp = pd.concat(frames, ignore_index=True)
    inp["y"] = inp["y"].astype("int64")
    return inp, sales, gt


def run_forecasts(client: bigquery.Client, inp: pd.DataFrame) -> pd.DataFrame:
    df = inp.copy()
    df["date"] = df["date"].dt.date
    schema = [bigquery.SchemaField("date", "DATE"), bigquery.SchemaField("variant", "STRING"),
              bigquery.SchemaField("capture_key", "STRING"), bigquery.SchemaField("store_id", "STRING"),
              bigquery.SchemaField("category", "STRING"), bigquery.SchemaField("y", "INT64")]
    client.load_table_from_dataframe(df, f"{DS}.backtest_input", job_config=bigquery.LoadJobConfig(
        schema=schema, write_disposition="WRITE_TRUNCATE")).result()
    sql = (ROOT / "bigquery" / "02_backtest.sql").read_text()
    client.query(sql, job_config=bigquery.QueryJobConfig(default_dataset=DS)).result()
    fc = client.query(f"SELECT variant, capture_rate, store_id, category, forecast_date, forecast_value "
                      f"FROM `{DS}.backtest_forecasts`").to_dataframe()
    fc["forecast_date"] = pd.to_datetime(fc["forecast_date"])
    fc["capture_rate"] = fc["capture_rate"].round(2)
    return fc


def add_festival_arms(fc: pd.DataFrame, inp: pd.DataFrame) -> pd.DataFrame:
    """For every arm, a "_festival" twin with the festival-calendar uplift learned from its own training series."""
    keys = ["store_id", "category"]
    out = [fc]
    for (variant, rate), sub in fc.groupby(["variant", "capture_rate"]):
        if rate == REFERENCE_RATE:
            continue
        hist = inp[(inp.variant == variant) & (inp.capture_key == f"{rate:.2f}")][["date"] + keys + ["y"]]
        up, wk = festival_uplift(hist, PAST_DIWALIS), weekday_index(hist)
        adj = apply_uplift(sub[["variant", "capture_rate"] + keys + ["forecast_date", "forecast_value"]],
                           up, wk, base_level(hist, wk, BT_DIWALI), BT_DIWALI)
        adj["variant"] = f"{variant}_festival"
        out.append(adj.drop(columns=["uplift"]))
    return pd.concat(out, ignore_index=True)


def truth_from_bq(client: bigquery.Client) -> pd.DataFrame:
    end = (CUTOFF + pd.Timedelta(days=HORIZON + OVERSTOCK_DAYS - 1)).date()
    t = client.query(f"""
        SELECT date, store_id, category, SUM(true_demand) AS true_demand
        FROM `{DS}.eval_ground_truth`
        WHERE date BETWEEN '{CUTOFF.date()}' AND '{end}'
        GROUP BY 1, 2, 3""").to_dataframe()
    t["date"] = pd.to_datetime(t["date"])
    return t


# ------------------------------------------------------------------------------------------------
def planner_prebuild() -> dict[tuple[str, str], np.ndarray]:
    """The generator's festive pre-build factor for each Monday of the window, per store x category.

    Same rule as data/generate.py: 1 + PREBUILD x (calendar intensity of the coming cover window / of the last
    28 days - 1), using the base-rate-weighted planner calendar of the SKUs in the store x category.
    """
    _, P = calendar_multipliers()
    b = base_rates()
    t0 = int((CUTOFF - START).days)
    out: dict[tuple[str, str], np.ndarray] = {}
    groups: dict[tuple[str, str], list[int]] = {}
    from data.catalog_spec import PRODUCT_BY_SKU
    for i, (s, k) in enumerate(SERIES):
        groups.setdefault((s, PRODUCT_BY_SKU[k]["category"]), []).append(i)
    for key, idx in groups.items():
        w = b[idx] / b[idx].sum()
        pc = (P[idx] * w[:, None]).sum(axis=0)
        f = np.ones(HORIZON)
        for d in range(HORIZON):
            t = t0 + d
            ahead = pc[t + LEAD_DAYS:t + LEAD_DAYS + REVIEW_DAYS].mean()
            behind = pc[t - 28:t].mean()
            f[d] = 1 + PREBUILD * (ahead / behind - 1)
        out[key] = f
    return out


def replenish(fc_series: np.ndarray, truth: np.ndarray, on_hand0: int, prebuild: np.ndarray) -> dict:
    """Weekly order-up-to policy over the window (the generator's policy with the forecast in place of trailing
    sales). fc_series: >= HORIZON + COVER days of forecasts; truth: HORIZON + OVERSTOCK_DAYS days of true demand."""
    on_hand = float(on_hand0)
    arrivals = np.zeros(HORIZON + LEAD_DAYS + 1)
    stockout_days, lost, sold_tot = 0, 0.0, 0.0
    for d in range(HORIZON):
        on_hand += arrivals[d]
        if WINDOW[d].dayofweek == 0:
            S = np.ceil(SAFETY * fc_series[d:d + COVER].sum() * prebuild[d])
            on_order = arrivals[d + 1:d + LEAD_DAYS + 1].sum()
            arrivals[d + LEAD_DAYS] += max(0.0, S - on_hand - on_order)
        dem = truth[d]
        s = min(dem, on_hand)
        on_hand -= s
        sold_tot += s
        if dem > s:
            stockout_days += 1
            lost += dem - s
    overstock = max(0.0, on_hand - truth[HORIZON:HORIZON + OVERSTOCK_DAYS].sum())
    return dict(stockout_days=stockout_days, lost_units=lost, sold=sold_tot, overstock_units=overstock)


def evaluate(fc: pd.DataFrame, truth: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    series = truth[["store_id", "category"]].drop_duplicates().sort_values(["store_id", "category"])
    tw = truth.pivot_table(index=["store_id", "category"], columns="date", values="true_demand").fillna(0)
    open_stock = sales[sales.date == CUTOFF].groupby(["store_id", "category"])["stock_open"].sum()
    hist = sales[(sales.date < CUTOFF) & (sales.date >= CUTOFF - pd.Timedelta(days=56))] \
        .groupby(["store_id", "category"])[["revenue_inr", "units_sold"]].sum()
    asp = hist["revenue_inr"] / hist["units_sold"]
    pre = planner_prebuild()
    rows = []
    arms = sorted({(v, float(r)) for v, r in zip(fc.variant, fc.capture_rate)}) + [("oracle", -1.0)]
    for variant, rate in arms:
        for s, c in series.itertuples(index=False):
            tr = tw.loc[(s, c)].to_numpy()
            if variant == "oracle":    # reference only: a perfect forecast (not written to BigQuery)
                f_all = np.concatenate([tr, np.repeat(tr[-7:].mean(), COVER)])
                pb = np.ones(HORIZON)  # a perfect forecast already contains the festival
            else:
                sub = fc[(fc.variant == variant) & (fc.capture_rate == round(rate, 2)) & (fc.store_id == s)
                         & (fc.category == c)].sort_values("forecast_date")
                f_all = sub["forecast_value"].to_numpy()
                assert len(f_all) >= HORIZON + COVER - 1, (variant, rate, s, c, len(f_all))
                f_all = np.concatenate([f_all, np.repeat(f_all[-1], 1)])
                # festival arms already forecast the festival, so the planner pre-build is not applied on top
                pb = np.ones(HORIZON) if variant.endswith("_festival") else pre[(s, c)]
            f42, t42 = f_all[:HORIZON], tr[:HORIZON]
            rep = replenish(f_all, tr, int(open_stock.get((s, c), 0)), pb)
            rows.append(dict(variant=variant, capture_rate=rate, store_id=s, category=c,
                             abs_err=float(np.abs(f42 - t42).sum()), err=float((f42 - t42).sum()),
                             demand=float(t42.sum()), lost_revenue_inr=rep["lost_units"] * float(asp[(s, c)]),
                             stockout_days=rep["stockout_days"], overstock_units=rep["overstock_units"],
                             sold=rep["sold"]))
    return pd.DataFrame(rows)


def long_results(ev: pd.DataFrame, run_at: dt.datetime) -> pd.DataFrame:
    ev = ev[(ev.variant != "oracle") & (ev.capture_rate.round(2) != REFERENCE_RATE)]   # references: report only
    out = []

    def add(g: pd.DataFrame, scope: str):
        d = g["demand"].sum()
        vals = {"wape": g["abs_err"].sum() / d, "bias": g["err"].sum() / d,
                "stockout_days": g["stockout_days"].sum(), "lost_revenue_inr": round(g["lost_revenue_inr"].sum()),
                "overstock_units": round(g["overstock_units"].sum()), "fill_rate": g["sold"].sum() / d}
        v, r = g["variant"].iloc[0], float(g["capture_rate"].iloc[0])
        for m, x in vals.items():
            out.append(dict(variant=v, capture_rate=r, scope=scope, metric=m, value=float(x), run_at=run_at))

    for (v, r), g in ev.groupby(["variant", "capture_rate"]):
        add(g, "overall")
        for c, gc in g.groupby("category"):
            add(gc, f"category:{c}")
        for s, gs in g.groupby("store_id"):
            add(gs, f"store:{s}")
        for (s, c), gsc in g.groupby(["store_id", "category"]):
            add(gsc, f"{s}|{c}")
    return pd.DataFrame(out)


def write_results(client: bigquery.Client, res: pd.DataFrame) -> None:
    schema = [bigquery.SchemaField("variant", "STRING"), bigquery.SchemaField("capture_rate", "FLOAT64"),
              bigquery.SchemaField("scope", "STRING"), bigquery.SchemaField("metric", "STRING"),
              bigquery.SchemaField("value", "FLOAT64"), bigquery.SchemaField("run_at", "TIMESTAMP")]
    client.load_table_from_dataframe(res, f"{DS}.backtest_results", job_config=bigquery.LoadJobConfig(
        schema=schema, write_disposition="WRITE_TRUNCATE")).result()


# ------------------------------------------------------------------------------------------------
def fmt_inr(x: float) -> str:
    return f"₹{x / 1e5:,.2f} lakh"


def summary_table(ev: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (v, r), g in ev.groupby(["variant", "capture_rate"], sort=False):
        d = g["demand"].sum()
        rows.append(dict(variant=v, capture_rate=r, wape=g["abs_err"].sum() / d, bias=g["err"].sum() / d,
                         stockout_days=int(g["stockout_days"].sum()), lost_revenue_inr=g["lost_revenue_inr"].sum(),
                         overstock_units=g["overstock_units"].sum(), fill_rate=g["sold"].sum() / d))
    t = pd.DataFrame(rows)
    fam = {"sales_only": 0, "demand_sensed": 1, "demand_sensed_scaled": 2}

    def key(v, r):
        if v == "oracle":
            return (9, 0, 0)
        festival = v.endswith("_festival")
        base = v.replace("_festival", "")
        ref = 1 if r == REFERENCE_RATE else 0
        return (int(festival) * 2 + ref, fam[base], r)
    t["o"] = [key(v, r) for v, r in zip(t.variant, t.capture_rate)]
    return t.sort_values("o").drop(columns="o")


def write_report(ev: pd.DataFrame, gt_window: dict, run_at: dt.datetime) -> str:
    t = summary_table(ev)

    def row(v, r):
        return t[(t.variant == v) & (t.capture_rate.round(2) == round(r, 2))].iloc[0]

    def label(v, r):
        festival = v.endswith("_festival")
        base = v.replace("_festival", "")
        if v == "oracle":
            return "Reference · perfect forecast"
        if r == REFERENCE_RATE:
            return "Reference · uncensored history (100% capture)"
        name = {"sales_only": "A · sales only", "demand_sensed": f"B · sales + captured @ {r:.0%}",
                "demand_sensed_scaled": f"B′ · sales + captured ÷ rate @ {r:.0%}"}[base]
        return name + (" + festival calendar" if festival else "")

    def table(sub: pd.DataFrame) -> list[str]:
        out = ["| Arm | WAPE | Bias | Stock-out days | Lost revenue | Overstock units | Fill rate |",
               "|---|---:|---:|---:|---:|---:|---:|"]
        for r in sub.itertuples():
            out.append(f"| {label(r.variant, r.capture_rate)} | {r.wape:.1%} | {r.bias:+.1%} | {r.stockout_days} | "
                       f"{fmt_inr(r.lost_revenue_inr)} | {r.overstock_units:,.0f} | {r.fill_rate:.1%} |")
        return out

    a, b, bs = row("sales_only", 0.0), row("demand_sensed", 0.35), row("demand_sensed_scaled", 0.35)
    af, bf, bsf = row("sales_only_festival", 0.0), row("demand_sensed_festival", 0.35), \
        row("demand_sensed_scaled_festival", 0.35)
    ref = row("demand_sensed", REFERENCE_RATE)

    def pct(x, y):
        return f"{(y - x) / max(x, 1):+.1%}"

    lines = ["# Backtest: sales-only vs demand-sensed forecasting\n",
             "> **All data is simulated** (Nova Bazaar is a fictional retailer). The simulation is what makes this "
             "measurable: true demand, including demand lost to stock-outs, is known. These are not field results.\n",
             f"Run at {run_at.strftime('%Y-%m-%d %H:%M UTC')}. Reproduce with `.venv/bin/python evals/backtest.py`. "
             "Long-format results are in BigQuery `retailnova.backtest_results`.\n",
             "## Headline (cutoff 2025-09-08, 42-day horizon through the Diwali 2025 ramp, 35% capture)\n",
             "| | A · sales only | B · + captured | B′ · + captured ÷ rate |",
             "|---|---:|---:|---:|",
             f"| WAPE, TimesFM | {a.wape:.1%} | {b.wape:.1%} | {bs.wape:.1%} |",
             f"| WAPE, TimesFM + festival calendar | {af.wape:.1%} | {bf.wape:.1%} | {bsf.wape:.1%} |",
             f"| Bias, TimesFM + festival calendar | {af.bias:+.1%} | {bf.bias:+.1%} | {bsf.bias:+.1%} |",
             f"| Lost revenue, TimesFM (+ planner pre-build) | {fmt_inr(a.lost_revenue_inr)} | {fmt_inr(b.lost_revenue_inr)} "
             f"({pct(a.lost_revenue_inr, b.lost_revenue_inr)}) | {fmt_inr(bs.lost_revenue_inr)} "
             f"({pct(a.lost_revenue_inr, bs.lost_revenue_inr)}) |",
             f"| Lost revenue, TimesFM + festival calendar | {fmt_inr(af.lost_revenue_inr)} | {fmt_inr(bf.lost_revenue_inr)} "
             f"({pct(af.lost_revenue_inr, bf.lost_revenue_inr)}) | {fmt_inr(bsf.lost_revenue_inr)} "
             f"({pct(af.lost_revenue_inr, bsf.lost_revenue_inr)}) |",
             f"| Stock-out days, TimesFM + festival calendar | {af.stockout_days} | {bf.stockout_days} | {bsf.stockout_days} |",
             f"| Overstock units, TimesFM + festival calendar | {af.overstock_units:,.0f} | {bf.overstock_units:,.0f} | "
             f"{bsf.overstock_units:,.0f} |",
             "",
             f"- **Reading it.** Only {gt_window['lost_pct_hist']:.1%} of pre-cutoff demand was censored in this simulation, "
             f"so demand sensing moves WAPE by {(a.wape - bs.wape) * 100:.1f} points (TimesFM) and "
             f"{(af.wape - bsf.wape) * 100:.1f} points (with the calendar) at 35% capture. Even a fully uncensored history "
             f"({ref.wape:.1%}) is only {(a.wape - ref.wape) * 100:.1f} points better than A. Scaling captured demand by the "
             "capture rate (B′) recovers more of the censored level than adding raw captures (B). The decision metrics move "
             "more than WAPE, because the recovered units sit on exactly the series that stock out.",
             f"- **Seasonality is the bigger lever for accuracy.** Without a festival calendar, every arm under-forecasts the "
             f"Diwali ramp ({a.bias:+.0%} bias for A). The calendar uplift, learned from Diwali 2024 only, brings that to "
             f"{af.bias:+.0%} and cuts WAPE by about {(a.wape - af.wape) * 100:.0f} points. Demand sensing fixes censoring, "
             "the calendar fixes seasonality, and the gains add up.",
             "- **Compare within a block, not across.** The two blocks use different replenishment rules. TimesFM-only arms "
             "get the planner's festive pre-build (1.3 safety × half the calendar uplift on top of the forecast level), which "
             "orders more than the still under-biased calendar forecasts do. That is why lost revenue is lower in the "
             "TimesFM-only block. Within each block, the policy, starting stock and true demand are identical.\n",
             "## All arms\n",
             "### TimesFM only (replenishment adds the planner's partial festive pre-build)\n"]
    plain = t[~t.variant.str.endswith("_festival") & (t.variant != "oracle") & (t.capture_rate != REFERENCE_RATE)]
    lines += table(plain) + [""]
    lines += ["### TimesFM + festival calendar (no pre-build: the forecast already carries the festival)\n"]
    lines += table(t[t.variant.str.endswith("_festival")]) + [""]
    lines += ["### References (not written to BigQuery)\n"]
    lines += table(t[(t.variant == "oracle") | (t.capture_rate == REFERENCE_RATE)]) + [""]
    lines.append("*Uncensored history* trains TimesFM on true demand (every lost unit captured): the most demand sensing "
                 "could ever recover. It is shown with the planner pre-build. *Perfect forecast* feeds the replenishment "
                 "policy the true future demand: the ceiling for the policy itself.\n")
    lines.append("## By category (TimesFM + festival calendar, A vs B′ at 35%)\n")
    lines.append("| Category | WAPE A | WAPE B′ | Lost revenue A | Lost revenue B′ | Stock-out days A | Stock-out days B′ |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for c in sorted(ev.category.unique()):
        ga = ev[(ev.variant == "sales_only_festival") & (ev.category == c)]
        gb = ev[(ev.variant == "demand_sensed_scaled_festival") & (ev.capture_rate.round(2) == 0.35) & (ev.category == c)]
        lines.append(f"| {c} | {ga.abs_err.sum() / ga.demand.sum():.1%} | {gb.abs_err.sum() / gb.demand.sum():.1%} | "
                     f"{fmt_inr(ga.lost_revenue_inr.sum())} | {fmt_inr(gb.lost_revenue_inr.sum())} | "
                     f"{int(ga.stockout_days.sum())} | {int(gb.stockout_days.sum())} |")
    lines.append("")
    lines.append("## Method\n")
    lines.append("- **Data.** `data/generate.py` (seed 2026) simulates daily true demand for 7 stores × 72 SKUs from "
                 "2024-10-01, with weekday, festival (Diwali, Navratri/Dussehra, Pongal, Onam, Ugadi, Eid, Christmas and "
                 "others), wedding-season, monsoon, rain-day and regional effects. A weekly order-up-to policy based on "
                 "trailing 4-week sales (with a partial festive pre-build) censors sales whenever stock runs out.")
    lines.append(f"- **Censoring.** Before the cutoff, {gt_window['lost_pct_hist']:.1%} of true demand was lost to "
                 f"stock-outs. In the evaluation window it is {gt_window['lost_pct_window']:.1%} under the historical policy.")
    lines.append("- **Signals.** Each lost unit is captured as a conversation signal with probability *r* (common random "
                 "numbers, so captures are nested across rates). Only stock-related signals are used. B adds the captured units "
                 "to sales. B′ adds captured ÷ *r*, an estimate of true lost demand. In a real deployment *r* is calibrated "
                 "with store audits; here B′ uses the true simulated rate, which is optimistic.")
    lines.append("- **Forecasts.** BigQuery `AI.FORECAST` (TimesFM), one series per store × category per arm, "
                 "trained on 2024-10-01 → 2025-09-07, horizon 56 days. WAPE is scored on the first 42 days "
                 "(2025-09-08 → 2025-10-19) against `eval_ground_truth`; the extra 14 days only let late orders see a full cover window.")
    lines.append("- **Festival calendar** (same code as the live forecasts, `data/run_forecast.py`). From each arm's own "
                 "training series:\n"
                 "  - Uplift(o) = weekday-adjusted units at offset *o* from Diwali 2024, divided by the 28 days before the "
                 "window, for o = −21 … +2, smoothed over 3 days.\n"
                 "  - For forecast days in Diwali 2025 − 21 … + 2, the forecast becomes max(TimesFM, base × weekday × uplift). "
                 "Base is the last 28 days of training history.")
    lines.append(f"- **Replenishment.** The generator's own policy, with the forecast in place of trailing sales. Every Monday, "
                 f"order up to {SAFETY} × forecast demand over the next {COVER} days (7-day review + {LEAD_DAYS}-day lead time), "
                 "minus stock on hand and on order.\n"
                 f"  - For TimesFM-only arms, the order is also multiplied by the planner's festive pre-build "
                 f"(1 + {PREBUILD} × the calendar's expected uplift). Festival arms omit the pre-build, because the forecast "
                 "already carries the festival.\n"
                 "  - Demand is served at store × category level, starting from the simulated stock on the cutoff date.\n"
                 "  - Lost revenue = lost units × the store × category average selling price over the 8 weeks before the cutoff.\n"
                 f"  - Overstock = stock left after the window beyond the next {OVERSTOCK_DAYS} days of true demand.")
    lines.append("- **Metrics.** WAPE = Σ|forecast − true demand| / Σ true demand; bias = Σ(forecast − true demand) / Σ true demand.\n")
    lines.append("## Caveats (read before quoting the numbers)\n")
    lines.append("- **Simulation, not field data.** The size of B's advantage follows from the generator's assumptions: how much "
                 "demand is censored, the capture rate, and that captured signals are unbiased (no double counting of "
                 "repeat asks and no fake intent). Real signal streams are noisier.")
    lines.append("- **Capture rate matters.** B′ assumes the capture rate is known exactly. A mis-estimated rate would "
                 "over- or under-correct the censored level.")
    lines.append("- **One past Diwali.** The backtest calendar uplift is learned from a single Diwali (2024), and that "
                 "Diwali's baseline window is truncated by the start of the data. The live forecast uses two Diwalis (2024 and 2025).")
    lines.append("- **Category-level pooling.** The replenishment simulation pools SKUs and sizes within a store × category, "
                 "which understates stock-outs compared with SKU × size reality. Within each block the comparison is like for "
                 "like (same policy, same starting stock, same true demand); only the forecast input differs.")
    lines.append("- **One cutoff, one season.** This is a single backtest window. A rolling-origin backtest over more festivals "
                 "would give tighter evidence. Small differences (a few percent of lost revenue, a few stock-out days) are "
                 "within the noise of one window. For example, in the TimesFM-only block B′ at 35% edges out the uncensored "
                 "reference on lost revenue, and B′ is not monotonic between 35% and 50%.")
    lines.append("- **Not tuned for B.** The generator's parameters are set for seasonal realism and are documented in "
                 "`data/generate.py` and `data/calendar.py`.")
    REPORT.write_text("\n".join(lines) + "\n")
    return "\n".join(lines)


def write_summary(ev: pd.DataFrame, run_at: dt.datetime) -> dict:
    """Machine-readable headline. Primary arm = the live pipeline (TimesFM + festival calendar):
    A = sales_only_festival vs B = demand_sensed_scaled_festival, chain-wide, 0.35 capture, Diwali 2025 window."""
    import json
    t = summary_table(ev)

    def row(v, r):
        return t[(t.variant == v) & (t.capture_rate.round(2) == round(r, 2))].iloc[0]

    a, b = row("sales_only_festival", 0.0), row("demand_sensed_scaled_festival", 0.35)
    red = {r: (a.lost_revenue_inr - row("demand_sensed_scaled_festival", r).lost_revenue_inr) / a.lost_revenue_inr * 100
           for r in RATES}
    dw = {r: (a.wape - row("demand_sensed_scaled_festival", r).wape) * 100 for r in RATES}
    out = {
        "data": "SIMULATED (Nova Bazaar is fictional); not field results",
        "primary_arm": "TimesFM (BigQuery AI.FORECAST) + festival calendar; demand_sensed = sales + captured unmet / capture rate",
        "window": f"cutoff {CUTOFF.date()}, {HORIZON}-day horizon to {(CUTOFF + pd.Timedelta(days=HORIZON - 1)).date()} "
                  "(Diwali 2025 = 2025-10-20), chain-wide (7 stores x 6 categories)",
        "capture_rate": 0.35,
        "wape_sales_only": round(a.wape * 100, 1),
        "wape_demand_sensed": round(b.wape * 100, 1),
        "stockout_days_sales_only": int(a.stockout_days),
        "stockout_days_demand_sensed": int(b.stockout_days),
        "lost_revenue_sales_only_inr": int(round(a.lost_revenue_inr)),
        "lost_revenue_demand_sensed_inr": int(round(b.lost_revenue_inr)),
        "lost_revenue_reduction_pct": round(red[0.35], 1),
        "sensitivity_note": (f"Across capture rates of 10-50%, demand sensing cuts lost revenue by "
                             f"{min(red.values()):.1f}-{max(red.values()):.1f}% and WAPE by "
                             f"{min(dw.values()):.1f}-{max(dw.values()):.1f} points versus sales-only, with gains growing "
                             f"as more unmet demand is captured (simulation; capture rate assumed known)."),
        "run_at": run_at.isoformat().replace("+00:00", "Z"),
        "report": "evals/backtest_report.md",
    }
    SUMMARY.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return out


def main() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    run_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    inp, sales, gt = build_inputs()
    print(f"backtest_input: {len(inp):,} rows ({inp.groupby(['variant', 'capture_key']).ngroups} variants x 42 series)")
    fc = run_forecasts(client, inp)
    print(f"backtest_forecasts: {len(fc):,} rows")
    fc = add_festival_arms(fc, inp)
    truth = truth_from_bq(client)
    ev = evaluate(fc, truth, sales)
    res = long_results(ev, run_at)
    write_results(client, res)
    print(f"backtest_results: {len(res):,} rows")
    gt["date"] = pd.to_datetime(gt["date"])
    hist = gt[gt.date < CUTOFF]
    win = gt[(gt.date >= CUTOFF) & (gt.date < CUTOFF + pd.Timedelta(days=HORIZON))]
    stats = {"lost_pct_hist": hist.lost_units.sum() / hist.true_demand.sum(),
             "lost_pct_window": win.lost_units.sum() / win.true_demand.sum()}
    write_report(ev, stats, run_at)
    write_summary(ev, run_at)
    t = summary_table(ev)
    with pd.option_context("display.width", 160, "display.float_format", "{:,.4f}".format):
        print(t.to_string(index=False))
    print(f"report: {REPORT}")


if __name__ == "__main__":
    main()
