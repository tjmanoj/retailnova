"""Load the generated tables into BigQuery `retailnova-ai.retailnova` (asia-south1) with WRITE_TRUNCATE.

Tables (docs/contracts.md §3): stores, products, sales_daily, eval_ground_truth, signals_daily, forecast_input.
Run data/generate.py first, then (with `source scripts/env.sh`):  .venv/bin/python data/load_bigquery.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# data/calendar.py would shadow the stdlib `calendar` module if data/ were on sys.path.
_HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]

import os  # noqa: E402

import pandas as pd  # noqa: E402
from google.cloud import bigquery  # noqa: E402
import warnings  # noqa: E402

warnings.filterwarnings("ignore", message=".*pandas-gbq.*")

OUT = Path(__file__).resolve().parent / "out"
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "retailnova-ai")
DATASET = os.environ.get("BQ_DATASET", "retailnova")
LOCATION = os.environ.get("REGION", "asia-south1")

S, I, D, F, TS = "STRING", "INT64", "DATE", "FLOAT64", "TIMESTAMP"
SCHEMAS = {
    "stores": [("store_id", S), ("name", S), ("city", S), ("type", S)],
    "products": [("sku", S), ("name", S), ("category", S), ("color", S), ("material", S), ("price_inr", I)],
    "sales_daily": [("date", D), ("store_id", S), ("sku", S), ("category", S), ("units_sold", I),
                    ("revenue_inr", I), ("stock_open", I)],
    "eval_ground_truth": [("date", D), ("store_id", S), ("sku", S), ("category", S), ("true_demand", I),
                          ("lost_units", I)],
    "signals_daily": [("date", D), ("store_id", S), ("category", S), ("sku", S), ("unmet_units", I),
                      ("signals", I), ("source", S)],
    "forecast_input": [("date", D), ("store_id", S), ("category", S), ("units_sales", I),
                       ("units_demand_sensed", I)],
}
DESCRIPTIONS = {
    "sales_daily": "SIMULATED observed sales (censored by stock), 2024-10-01..2026-10-17. Nova Bazaar is fictional.",
    "eval_ground_truth": "SIMULATED hidden true demand and lost units. Evals/backtest only; never used by the app.",
    "signals_daily": "SIMULATED unmet demand captured from conversations (35% capture rate). sku NULL = asks "
                     "not tied to stock (not carried / price too high).",
    "forecast_input": "Store x category daily: units_sales and units_demand_sensed = units_sales + captured "
                      "stock-related unmet units (signals with a catalog sku).",
    "stores": "Nova Bazaar stores (fictional retailer).",
    "products": "Nova Bazaar catalog (72 synthetic SKUs).",
}


def load(client: bigquery.Client, name: str, df: pd.DataFrame) -> int:
    schema = [bigquery.SchemaField(c, t, mode="NULLABLE") for c, t in SCHEMAS[name]]
    df = df[[c for c, _ in SCHEMAS[name]]].copy()
    for c, t in SCHEMAS[name]:
        if t == D:
            df[c] = pd.to_datetime(df[c]).dt.date
        elif t == I:
            df[c] = df[c].astype("Int64")
    table_id = f"{PROJECT}.{DATASET}.{name}"
    cfg = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")
    client.load_table_from_dataframe(df, table_id, job_config=cfg, location=LOCATION).result()
    t = client.get_table(table_id)
    if DESCRIPTIONS.get(name) and t.description != DESCRIPTIONS[name]:
        t.description = DESCRIPTIONS[name]
        client.update_table(t, ["description"])
    print(f"  {name:<18} {t.num_rows:>8,} rows")
    return t.num_rows


def main() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    client.create_dataset(bigquery.Dataset(f"{PROJECT}.{DATASET}"), exists_ok=True)
    print(f"loading into {PROJECT}.{DATASET} ({LOCATION})")
    for name in SCHEMAS:
        df = pd.read_parquet(OUT / f"{name}.parquet")
        n = load(client, name, df)
        assert n == len(df), (name, n, len(df))


if __name__ == "__main__":
    main()
