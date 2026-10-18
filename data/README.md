# RetailNova data pipeline

Everything in this folder is **synthetic**. Nova Bazaar is a fictional retailer, and every generated record carries `source: "simulated"`. The simulation exists so that **true demand is known**: we can measure how much demand stock-outs hide from sales data, and how much of it captured conversation signals recover.

## Files

| File | What it does |
|---|---|
| `catalog_spec.py` | 7 stores and 72 SKUs (6 categories × 12), with the hero records of `docs/contracts.md` §1.3. Validates itself on import. |
| `calendar.py` | Festival calendar for 2024-10 → 2026-12: Diwali, Navratri/Dussehra, Pongal, Onam, Ugadi, Puthandu, Eid, Christmas, Raksha Bandhan, Ganesh Chaturthi, Varalakshmi Vratham and Karthigai Deepam. Also covers pre-festival ramps, category multipliers, regional weights, wedding seasons, monsoon and rain days. |
| `generate.py` | Deterministic generator (`SEED = 2026`). Writes parquet and JSON to `data/out/` (gitignored) and prints a reproducibility hash. |
| `gen_embeddings.py` | Embeds the 72 products with `gemini-embedding-2` (768-dim, `RETRIEVAL_DOCUMENT`) and caches them to `data/out/embeddings.json`. |
| `load_firestore.py` | Idempotent batched seed of Firestore. Writes `meta/demo.seeded_at` last. |
| `verify_search.py` | Runs 5 natural-language queries against the Firestore vector index (COSINE). |
| `gen_images.py` | Generates the 72 catalog photos and 2 sample query photos with `gemini-3.1-flash-image`, as WebP (≤ 768 px, ≤ 80 KB). Skips files that already exist. |
| `load_bigquery.py` | Loads `stores`, `products`, `sales_daily`, `eval_ground_truth`, `signals_daily` and `forecast_input` into `retailnova-ai.retailnova` (WRITE_TRUNCATE). |
| `run_forecast.py` | Live forecasts. Runs `bigquery/01_forecast.sql` (`AI.FORECAST` / TimesFM, 42 days from 2026-10-18, both variants) and keeps the raw rows in `forecasts_timesfm`. Then applies the festival-calendar uplift and writes `forecasts`. |
| `../evals/backtest.py` | Backtest at capture rates of 10–50%: A (sales only) vs B (sales + captured) vs B′ (sales + captured ÷ rate), each with and without the festival calendar. Writes `backtest_results`, `evals/backtest_report.md` and `evals/backtest_summary.json`. |

## Reproduce everything (from the repo root)

```bash
source scripts/env.sh                      # personal account + project retailnova-ai (check the printed account)
gcloud config get account                  # must print manojtofficial@gmail.com

.venv/bin/python data/catalog_spec.py      # optional: list and validate the catalog
.venv/bin/python data/generate.py          # ~5 s; prints REPRODUCIBILITY HASH (same on every run)
.venv/bin/python data/gen_embeddings.py    # 72 embedding calls (cached afterwards)
.venv/bin/python data/load_firestore.py    # ~3,900 doc writes; meta/demo.seeded_at written last
# targeted fix without a full reseed (rewrites the docs in inventory AND inventory_snapshot):
# .venv/bin/python data/load_firestore.py --patch-inventory CBE-RSP__SAR-001__FREE HYD-BNJ__SAR-005__FREE
.venv/bin/python data/verify_search.py     # vector search smoke test
.venv/bin/python data/load_bigquery.py     # 6 tables, WRITE_TRUNCATE
.venv/bin/python data/run_forecast.py      # forecasts (+ forecasts_timesfm): 2 variants x 42 series x 42 days
.venv/bin/python evals/backtest.py         # backtest tables + evals/backtest_report.md + backtest_summary.json
.venv/bin/python data/gen_images.py --parallel 3   # 74 images; idempotent (skips existing files)
```

To regenerate particular images: `.venv/bin/python data/gen_images.py --only SAR-001 MEN-004 --force`.

Scripts in `data/` import each other as the `data` package. `data/calendar.py` would otherwise shadow Python's standard `calendar` module, so each script removes `data/` from `sys.path` at start-up.

## How the simulation works

1. **True demand** for each store × SKU × day (2024-10-01 → 2026-10-17) is a Poisson draw. Its rate is:
   - base rate (store scale × category base × SKU popularity × price factor × regional taste)
   - × weekday × wedding season / monsoon / post-Diwali lull
   - × festival lift × 10% annual growth
   - × rain days × store footfall noise

   A flagship store sells a few units of a typical SKU a day. Online is the largest channel, and Coimbatore and Hyderabad are the smallest stores.
2. **Inventory** is simulated at SKU level:
   - Review every Monday with a 7-day supplier lead time.
   - Order-up-to level = trailing 4-week **sales** × 14 days × 1.3 safety × a partial festive pre-build. Planners anticipate only half of the calendar's uplift.
   - `units_sold = min(demand, stock)` and `lost_units = demand − sold`.

   Because orders follow censored sales, stock-outs shrink sales, which then shrink the next order. Stock-outs cluster on festive ramps (about 10% of demand lost in Nov 2024, 5.5% in Oct 2025, 2.2% overall).
3. **Captured unmet demand.** Each lost unit becomes a conversation signal with probability 0.35. Captures use common random numbers, so `generate.captured_unmet_frame(eval_ground_truth, rate)` regenerates nested captures at any rate for the backtest. A small stream of `not_carried` / `price_too_high` asks (with `sku` NULL) is added for realism. These asks are excluded from `forecast_input`, where `units_demand_sensed = units_sales + round(captured / 0.35)`: estimated true demand, with the capture rate assumed known (calibrated with store audits in a real deployment).
4. **Demo-day state (2026-10-18).**
   - The size-level inventory snapshot is split from the simulated end-of-day stock, keeping a full size run where stock allows. In-transit orders become `incoming` with an ETA.
   - The planted hero states are forced *inside* the simulation, so the last 14 days of history agree with them:
     - SAR-001 at T. Nagar sells out on Oct 10 while demand climbs.
     - RS Puram holds 14 units and Anna Nagar 2.
     - Two reorder points are lowered so they work as demo transfer sources: RS Puram SAR-001 (→ 2) and Banjara Hills SAR-005 (→ 4, wine maroon soft silk).
     - MEN-004 size L is out at T. Nagar.
     - DEC-002 is low at Jayanagar.
     - FTW-003 size 7 is out at Banjara Hills.
5. **Firestore `demand_signals`.** There are 735 docs for the last 30 days (unmet, substituted and fulfilled), with a channel mix, language mix (en/hi/ta), reasons, price bands and short, non-personal summaries. The unmet docs aggregate exactly to `signals_daily`. T. Nagar has 2 → 7 maroon-saree unmet signals a day over the last 7 days (31 in total).

## Live forecasts (`data/run_forecast.py`)
TimesFM cannot line up a lunar festival across years (Diwali was on 2025-10-20 and falls on 2026-11-08), so a calendar uplift is applied after `AI.FORECAST`, separately for each store × category × variant:
- **Uplift.** For each Diwali offset from −21 to +2 days, take the weekday-adjusted units in 2024 and 2025, divide by the mean of the 28 days before the window, and smooth over 3 days.
- **Forecast inside the window** (2026-10-18 … 11-10): `max(TimesFM, base × weekday × uplift)`, where base is the weekday-adjusted mean of 2026-09-20 … 10-17.
- **Result.** For CHN-TNG sarees over the next 21 days, sales-only forecasts 961 units and demand-sensed 1,072 (+11.6%). Both peak on Sat 2026-11-07.

## Outputs (`data/out/`)
`stores`, `products`, `sales_daily` (376,488 rows), `eval_ground_truth` (376,488), `signals_daily` (5,228), `forecast_input` (31,374), `inventory` (1,428 size-level rows) and `customers` (200) as parquet. Also `demand_signals.json` (735), `embeddings.json` and `manifest.json` (row counts and the hash).
