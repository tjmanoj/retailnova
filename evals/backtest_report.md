# Backtest: sales-only vs demand-sensed forecasting

> **All data is simulated** (Nova Bazaar is a fictional retailer). The simulation is what makes this measurable: true demand, including demand lost to stock-outs, is known. These are not field results.

Run at 2026-10-18 05:05 UTC. Reproduce with `.venv/bin/python evals/backtest.py`. Long-format results are in BigQuery `retailnova.backtest_results`.

## Headline (cutoff 2025-09-08, 42-day horizon through the Diwali 2025 ramp, 35% capture)

| | A · sales only | B · + captured | B′ · + captured ÷ rate |
|---|---:|---:|---:|
| WAPE, TimesFM | 45.5% | 45.1% | 44.5% |
| WAPE, TimesFM + festival calendar | 34.3% | 33.8% | 33.0% |
| Bias, TimesFM + festival calendar | -29.6% | -28.9% | -27.7% |
| Lost revenue, TimesFM (+ planner pre-build) | ₹30.41 lakh | ₹26.37 lakh (-13.3%) | ₹20.95 lakh (-31.1%) |
| Lost revenue, TimesFM + festival calendar | ₹125.87 lakh | ₹119.75 lakh (-4.9%) | ₹111.93 lakh (-11.1%) |
| Stock-out days, TimesFM + festival calendar | 159 | 150 | 141 |
| Overstock units, TimesFM + festival calendar | 0 | 0 | 0 |

- **Reading it.** Only 2.5% of pre-cutoff demand was censored in this simulation, so demand sensing moves WAPE by 1.0 points (TimesFM) and 1.4 points (with the calendar) at 35% capture. Even a fully uncensored history (44.5%) is only 1.0 points better than A. Scaling captured demand by the capture rate (B′) recovers more of the censored level than adding raw captures (B). The decision metrics move more than WAPE, because the recovered units sit on exactly the series that stock out.
- **Seasonality is the bigger lever for accuracy.** Without a festival calendar, every arm under-forecasts the Diwali ramp (-41% bias for A). The calendar uplift, learned from Diwali 2024 only, brings that to -30% and cuts WAPE by about 11 points. Demand sensing fixes censoring, the calendar fixes seasonality, and the gains add up.
- **Compare within a block, not across.** The two blocks use different replenishment rules. TimesFM-only arms get the planner's festive pre-build (1.3 safety × half the calendar uplift on top of the forecast level), which orders more than the still under-biased calendar forecasts do. That is why lost revenue is lower in the TimesFM-only block. Within each block, the policy, starting stock and true demand are identical.

## All arms

### TimesFM only (replenishment adds the planner's partial festive pre-build)

| Arm | WAPE | Bias | Stock-out days | Lost revenue | Overstock units | Fill rate |
|---|---:|---:|---:|---:|---:|---:|
| A · sales only | 45.5% | -40.9% | 41 | ₹30.41 lakh | 0 | 97.0% |
| B · sales + captured @ 10% | 45.4% | -40.7% | 42 | ₹29.13 lakh | 0 | 97.1% |
| B · sales + captured @ 20% | 45.3% | -40.6% | 39 | ₹28.81 lakh | 0 | 97.1% |
| B · sales + captured @ 35% | 45.1% | -40.4% | 35 | ₹26.37 lakh | 0 | 97.4% |
| B · sales + captured @ 50% | 45.0% | -40.2% | 35 | ₹25.74 lakh | 0 | 97.5% |
| B′ · sales + captured ÷ rate @ 10% | 45.0% | -40.2% | 40 | ₹22.30 lakh | 1 | 97.5% |
| B′ · sales + captured ÷ rate @ 20% | 44.7% | -39.8% | 36 | ₹21.31 lakh | 30 | 98.0% |
| B′ · sales + captured ÷ rate @ 35% | 44.5% | -39.5% | 34 | ₹20.95 lakh | 0 | 98.0% |
| B′ · sales + captured ÷ rate @ 50% | 44.5% | -39.6% | 29 | ₹21.92 lakh | 1 | 97.9% |

### TimesFM + festival calendar (no pre-build: the forecast already carries the festival)

| Arm | WAPE | Bias | Stock-out days | Lost revenue | Overstock units | Fill rate |
|---|---:|---:|---:|---:|---:|---:|
| A · sales only + festival calendar | 34.3% | -29.6% | 159 | ₹125.87 lakh | 0 | 87.8% |
| B · sales + captured @ 10% + festival calendar | 34.2% | -29.4% | 154 | ₹123.08 lakh | 0 | 88.0% |
| B · sales + captured @ 20% + festival calendar | 34.1% | -29.2% | 157 | ₹121.51 lakh | 0 | 88.2% |
| B · sales + captured @ 35% + festival calendar | 33.8% | -28.9% | 150 | ₹119.75 lakh | 0 | 88.5% |
| B · sales + captured @ 50% + festival calendar | 33.6% | -28.6% | 145 | ₹118.46 lakh | 0 | 88.7% |
| B′ · sales + captured ÷ rate @ 10% + festival calendar | 33.2% | -28.2% | 148 | ₹113.78 lakh | 0 | 89.1% |
| B′ · sales + captured ÷ rate @ 20% + festival calendar | 33.1% | -28.0% | 140 | ₹113.24 lakh | 0 | 89.3% |
| B′ · sales + captured ÷ rate @ 35% + festival calendar | 33.0% | -27.7% | 141 | ₹111.93 lakh | 0 | 89.5% |
| B′ · sales + captured ÷ rate @ 50% + festival calendar | 32.9% | -27.7% | 140 | ₹111.70 lakh | 0 | 89.6% |

### References (not written to BigQuery)

| Arm | WAPE | Bias | Stock-out days | Lost revenue | Overstock units | Fill rate |
|---|---:|---:|---:|---:|---:|---:|
| Reference · uncensored history (100% capture) | 44.5% | -39.5% | 34 | ₹22.15 lakh | 81 | 97.9% |
| Reference · perfect forecast | 0.0% | +0.0% | 0 | ₹0.00 lakh | 2,019 | 100.0% |

*Uncensored history* trains TimesFM on true demand (every lost unit captured): the most demand sensing could ever recover. It is shown with the planner pre-build. *Perfect forecast* feeds the replenishment policy the true future demand: the ceiling for the policy itself.

## By category (TimesFM + festival calendar, A vs B′ at 35%)

| Category | WAPE A | WAPE B′ | Lost revenue A | Lost revenue B′ | Stock-out days A | Stock-out days B′ |
|---|---:|---:|---:|---:|---:|---:|
| footwear | 31.7% | 31.0% | ₹5.77 lakh | ₹5.12 lakh | 21 | 20 |
| gifting | 37.4% | 35.4% | ₹22.15 lakh | ₹18.49 lakh | 30 | 27 |
| home_decor | 32.4% | 30.3% | ₹10.85 lakh | ₹8.71 lakh | 22 | 16 |
| kurta_sets | 36.7% | 36.0% | ₹34.78 lakh | ₹31.73 lakh | 39 | 37 |
| mens_ethnic | 31.6% | 30.5% | ₹10.18 lakh | ₹8.65 lakh | 18 | 12 |
| sarees | 33.8% | 32.9% | ₹42.15 lakh | ₹39.23 lakh | 29 | 29 |

## Method

- **Data.** `data/generate.py` (seed 2026) simulates daily true demand for 7 stores × 72 SKUs from 2024-10-01, with weekday, festival (Diwali, Navratri/Dussehra, Pongal, Onam, Ugadi, Eid, Christmas and others), wedding-season, monsoon, rain-day and regional effects. A weekly order-up-to policy based on trailing 4-week sales (with a partial festive pre-build) censors sales whenever stock runs out.
- **Censoring.** Before the cutoff, 2.5% of true demand was lost to stock-outs. In the evaluation window it is 2.6% under the historical policy.
- **Signals.** Each lost unit is captured as a conversation signal with probability *r* (common random numbers, so captures are nested across rates). Only stock-related signals are used. B adds the captured units to sales. B′ adds captured ÷ *r*, an estimate of true lost demand. In a real deployment *r* is calibrated with store audits; here B′ uses the true simulated rate, which is optimistic.
- **Forecasts.** BigQuery `AI.FORECAST` (TimesFM), one series per store × category per arm, trained on 2024-10-01 → 2025-09-07, horizon 56 days. WAPE is scored on the first 42 days (2025-09-08 → 2025-10-19) against `eval_ground_truth`; the extra 14 days only let late orders see a full cover window.
- **Festival calendar** (same code as the live forecasts, `data/run_forecast.py`). From each arm's own training series:
  - Uplift(o) = weekday-adjusted units at offset *o* from Diwali 2024, divided by the 28 days before the window, for o = −21 … +2, smoothed over 3 days.
  - For forecast days in Diwali 2025 − 21 … + 2, the forecast becomes max(TimesFM, base × weekday × uplift). Base is the last 28 days of training history.
- **Replenishment.** The generator's own policy, with the forecast in place of trailing sales. Every Monday, order up to 1.3 × forecast demand over the next 14 days (7-day review + 7-day lead time), minus stock on hand and on order.
  - For TimesFM-only arms, the order is also multiplied by the planner's festive pre-build (1 + 0.5 × the calendar's expected uplift). Festival arms omit the pre-build, because the forecast already carries the festival.
  - Demand is served at store × category level, starting from the simulated stock on the cutoff date.
  - Lost revenue = lost units × the store × category average selling price over the 8 weeks before the cutoff.
  - Overstock = stock left after the window beyond the next 7 days of true demand.
- **Metrics.** WAPE = Σ|forecast − true demand| / Σ true demand; bias = Σ(forecast − true demand) / Σ true demand.

## Caveats (read before quoting the numbers)

- **Simulation, not field data.** The size of B's advantage follows from the generator's assumptions: how much demand is censored, the capture rate, and that captured signals are unbiased (no double counting of repeat asks and no fake intent). Real signal streams are noisier.
- **Capture rate matters.** B′ assumes the capture rate is known exactly. A mis-estimated rate would over- or under-correct the censored level.
- **One past Diwali.** The backtest calendar uplift is learned from a single Diwali (2024), and that Diwali's baseline window is truncated by the start of the data. The live forecast uses two Diwalis (2024 and 2025).
- **Category-level pooling.** The replenishment simulation pools SKUs and sizes within a store × category, which understates stock-outs compared with SKU × size reality. Within each block the comparison is like for like (same policy, same starting stock, same true demand); only the forecast input differs.
- **One cutoff, one season.** This is a single backtest window. A rolling-origin backtest over more festivals would give tighter evidence. Small differences (a few percent of lost revenue, a few stock-out days) are within the noise of one window. For example, in the TimesFM-only block B′ at 35% edges out the uncensored reference on lost revenue, and B′ is not monotonic between 35% and 50%.
- **Not tuned for B.** The generator's parameters are set for seasonal realism and are documented in `data/generate.py` and `data/calendar.py`.
