"""Live forecasts: TimesFM (BigQuery AI.FORECAST) + a festival-calendar uplift, both variants.

1. bigquery/01_forecast.sql runs AI.FORECAST per store x category, horizon 42 from 2026-10-18, on
     sales_only    : units_sales (observed, censored by stock-outs)
     demand_sensed : units_demand_sensed = estimated true demand = sales + captured unmet / capture rate
                     (in a real deployment the capture rate is calibrated with store audits)
   Raw TimesFM rows are kept in `retailnova.forecasts_timesfm`.
2. Festival alignment. TimesFM cannot line up a lunar festival (Diwali 2025-10-20 vs 2026-11-08), so a
   calendar-aligned uplift is applied AFTER AI.FORECAST, per store x category x variant:
     uplift(o) = mean over past Diwalis (2024, 2025) of  y(Diwali + o) / mean y(28 days before the window),
     o = -21 .. +2 days, computed on weekday-adjusted daily units and smoothed (3-day centred mean).
   For forecast days 2026-10-18 .. 2026-11-10 (offset from 2026-11-08):
     calendar(d) = base x weekday(d) x uplift(offset)
     forecast(d) = max(TimesFM(d), calendar(d))
   base = the weekday-adjusted mean of the series over the 28 days before the window (2026-09-20 .. 10-17), the same
   reference the uplift ratios are measured against. Taking the max keeps what TimesFM already sees at the origin
   (the Navratri tail) without double counting it. Bounds are scaled by the same ratio.
3. Result -> `retailnova.forecasts` (WRITE_TRUNCATE), model = 'TimesFM + festival calendar'.

Run with `source scripts/env.sh` first:  .venv/bin/python data/run_forecast.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]
warnings.filterwarnings("ignore", message=".*BigQuery Storage module not found.*")
warnings.filterwarnings("ignore", message=".*pandas-gbq.*")

import datetime as dt  # noqa: E402
import os  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from google.cloud import bigquery  # noqa: E402

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "retailnova-ai")
LOCATION = os.environ.get("REGION", "asia-south1")
DS = f"{PROJECT}.retailnova"
SQL = _HERE.parent / "bigquery" / "01_forecast.sql"
OUT = _HERE / "out"

PAST_DIWALIS = [pd.Timestamp("2024-11-01"), pd.Timestamp("2025-10-20")]
TARGET_DIWALI = pd.Timestamp("2026-11-08")
OFFSETS = (-21, 2)
BASE_DAYS = 28
MODEL = "TimesFM + festival calendar"
KEYS = ["store_id", "category"]


# ------------------------------------------------------------------------------------------------
# Festival uplift (shared with evals/backtest.py)
# ------------------------------------------------------------------------------------------------
def weekday_index(hist: pd.DataFrame, group: list[str] = KEYS) -> pd.DataFrame:
    """*group, dow, wk: mean units by weekday / overall mean, from history."""
    h = hist.copy()
    h["dow"] = pd.to_datetime(h["date"]).dt.dayofweek
    wk = (h.groupby(group + ["dow"])["y"].mean() / h.groupby(group)["y"].mean()).rename("wk").reset_index()
    wk["wk"] = wk["wk"].fillna(1.0).replace(0, 1.0)
    return wk


def festival_uplift(hist: pd.DataFrame, diwalis: list[pd.Timestamp], group: list[str] = KEYS) -> pd.DataFrame:
    """hist: date, *group, y (daily). Returns *group, offset, uplift for offsets -21..+2.

    Daily units are weekday-adjusted first (Diwali falls on a different weekday each year), then for each past
    Diwali: ratio(o) = y(D + o) / mean y over the 28 days before the window. Ratios are averaged over the Diwalis
    available in `hist` and smoothed with a centred 3-day mean.
    """
    h = hist.copy()
    h["date"] = pd.to_datetime(h["date"])
    h["dow"] = h["date"].dt.dayofweek
    wk = h.groupby(group + ["dow"])["y"].mean() / h.groupby(group)["y"].mean()
    h = h.join(wk.rename("wk"), on=group + ["dow"])
    h["ya"] = h["y"] / h["wk"].replace(0, np.nan)
    lo, hi = OFFSETS
    start = h["date"].min()
    frames = []
    for D in diwalis:
        w0 = D + pd.Timedelta(days=lo)
        if w0 < start or D + pd.Timedelta(days=hi) > h["date"].max():
            continue
        b0 = max(start, w0 - pd.Timedelta(days=BASE_DAYS))
        base = h[(h.date >= b0) & (h.date < w0)].groupby(group)["ya"].mean().rename("base")
        win = h[(h.date >= w0) & (h.date <= D + pd.Timedelta(days=hi))].copy()
        win["offset"] = (win["date"] - D).dt.days
        win = win.join(base, on=group)
        win["ratio"] = win["ya"] / win["base"]
        frames.append(win[group + ["offset", "ratio"]])
    if not frames:
        raise ValueError("no complete past Diwali window in history")
    r = pd.concat(frames).groupby(group + ["offset"], as_index=False)["ratio"].mean()
    r = r.sort_values(group + ["offset"])
    r["uplift"] = r.groupby(group)["ratio"].transform(lambda s: s.rolling(3, center=True, min_periods=1).mean())
    r["uplift"] = r["uplift"].fillna(1.0).clip(lower=0.5)
    return r[group + ["offset", "uplift"]]


def base_level(hist: pd.DataFrame, wk: pd.DataFrame, diwali: pd.Timestamp, group: list[str] = KEYS) -> pd.DataFrame:
    """*group, base: weekday-adjusted mean daily units over the 28 days before the uplift window, or the last 28 days
    of history if the history ends earlier (backtest)."""
    h = hist.copy()
    h["date"] = pd.to_datetime(h["date"])
    end = min(diwali + pd.Timedelta(days=OFFSETS[0]), h["date"].max() + pd.Timedelta(days=1))
    h = h[(h.date >= end - pd.Timedelta(days=BASE_DAYS)) & (h.date < end)]
    h["dow"] = h["date"].dt.dayofweek
    h = h.merge(wk, on=group + ["dow"], how="left")
    h["ya"] = h["y"] / h["wk"].fillna(1.0)
    return h.groupby(group, as_index=False)["ya"].mean().rename(columns={"ya": "base"})


def apply_uplift(fc: pd.DataFrame, uplift: pd.DataFrame, wk: pd.DataFrame, base: pd.DataFrame,
                 diwali: pd.Timestamp, group: list[str] = KEYS) -> pd.DataFrame:
    """Rows dated diwali-21 .. diwali+2: forecast = max(TimesFM, baseline x weekday x uplift); bounds scaled by the
    same ratio. Other rows unchanged. `fc` holds one forecast series per `group` (forecast_date, forecast_value,
    lower, upper)."""
    out = fc.copy()
    out["offset"] = (pd.to_datetime(out["forecast_date"]) - diwali).dt.days
    out["dow"] = pd.to_datetime(out["forecast_date"]).dt.dayofweek
    out = out.merge(uplift, on=group + ["offset"], how="left").merge(wk, on=group + ["dow"], how="left") \
        .merge(base, on=group, how="left")
    out["wk"] = out["wk"].fillna(1.0)
    cal = out["base"] * out["wk"] * out["uplift"]
    new = np.where(out["uplift"].notna(), np.maximum(out["forecast_value"], cal), out["forecast_value"])
    ratio = np.where(out["forecast_value"] > 0, new / out["forecast_value"].where(out["forecast_value"] > 0, 1), 1.0)
    out["forecast_value"] = new
    for c in ("lower", "upper"):
        if c in out:
            out[c] = out[c] * ratio
    out["uplift"] = ratio
    return out.drop(columns=["offset", "dow", "wk", "base"])


# ------------------------------------------------------------------------------------------------
def main() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    run_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    raw = client.query(SQL.read_text(), job_config=bigquery.QueryJobConfig(default_dataset=DS)).to_dataframe()
    raw["forecast_date"] = pd.to_datetime(raw["forecast_date"])
    print(f"TimesFM: {len(raw):,} rows ({raw.groupby(['variant'] + KEYS).ngroups} series)")

    fi = pd.read_parquet(OUT / "forecast_input.parquet")
    parts = []
    for variant, col in (("sales_only", "units_sales"), ("demand_sensed", "units_demand_sensed")):
        hist = fi.rename(columns={col: "y"})[["date"] + KEYS + ["y"]]
        up, wk = festival_uplift(hist, PAST_DIWALIS), weekday_index(hist)
        parts.append(apply_uplift(raw[raw.variant == variant], up, wk, base_level(hist, wk, TARGET_DIWALI),
                                  TARGET_DIWALI))
    adj = pd.concat(parts, ignore_index=True)

    def write(df: pd.DataFrame, table: str, model: str) -> None:
        d = df[["store_id", "category", "forecast_date", "variant", "forecast_value", "lower", "upper"]].copy()
        d["forecast_date"] = d["forecast_date"].dt.date
        d["model"], d["run_at"] = model, run_at
        schema = [bigquery.SchemaField(n, t) for n, t in [
            ("store_id", "STRING"), ("category", "STRING"), ("forecast_date", "DATE"), ("variant", "STRING"),
            ("forecast_value", "FLOAT64"), ("lower", "FLOAT64"), ("upper", "FLOAT64"), ("model", "STRING"),
            ("run_at", "TIMESTAMP")]]
        client.load_table_from_dataframe(d, f"{DS}.{table}", job_config=bigquery.LoadJobConfig(
            schema=schema, write_disposition="WRITE_TRUNCATE")).result()
        print(f"  {table:<18} {len(d):,} rows  model={model!r}")

    write(raw, "forecasts_timesfm", "TimesFM")
    write(adj, "forecasts", MODEL)

    # ---------------- checks ----------------
    w = adj[(adj.forecast_date >= "2026-10-18") & (adj.forecast_date <= "2026-11-07")]
    tot = w.groupby(KEYS + ["variant"])["forecast_value"].sum().unstack("variant")
    tot["gap"] = tot["demand_sensed"] - tot["sales_only"]
    tot["gap_pct"] = tot["gap"] / tot["sales_only"]
    h = tot.loc[("CHN-TNG", "sarees")]
    print(f"\nCHN-TNG sarees, next 21 days (2026-10-18..11-07): sales_only {h.sales_only:,.0f}, "
          f"demand_sensed {h.demand_sensed:,.0f} ({h.gap_pct:+.1%})")
    raw21 = raw[(raw.forecast_date >= "2026-10-18") & (raw.forecast_date <= "2026-11-07")
                & (raw.store_id == "CHN-TNG") & (raw.category == "sarees")].groupby("variant")["forecast_value"].sum()
    print(f"  (raw TimesFM before the calendar uplift: {raw21.to_dict()})")
    cs = adj[(adj.store_id == "CHN-TNG") & (adj.category == "sarees")].pivot(
        index="forecast_date", columns="variant", values="forecast_value")
    for v in ("sales_only", "demand_sensed"):
        print(f"  {v:<14} peak {cs[v].idxmax().date()} ({cs[v].max():.0f}/day)")
    print("  daily (CHN-TNG sarees):")
    for d, r in cs[cs.index <= "2026-11-12"].iterrows():
        print(f"    {d.date()} {d.strftime('%a')}  sales_only {r.sales_only:6.1f}  demand_sensed {r.demand_sensed:6.1f}")
    other = tot.drop(index=("CHN-TNG", "sarees")).sort_values("gap", ascending=False).head(3)
    print("\nTop 3 other gaps (21 days, demand_sensed - sales_only):")
    for (s, c), r in other.iterrows():
        print(f"  {s:<8} {c:<12} sales_only {r.sales_only:7,.0f}  demand_sensed {r.demand_sensed:7,.0f}  "
              f"gap {r.gap:+6,.0f} ({r.gap_pct:+.1%})")
    allg = tot[["sales_only", "demand_sensed"]].sum()
    print(f"\nAll stores x categories, 21 days: sales_only {allg.sales_only:,.0f}, demand_sensed {allg.demand_sensed:,.0f} "
          f"({allg.demand_sensed / allg.sales_only - 1:+.1%})")


if __name__ == "__main__":
    main()
