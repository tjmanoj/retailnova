-- RetailNova backtest forecasts (SIMULATED data). Orchestrated by evals/backtest.py, which first loads
-- `retailnova.backtest_input` (one series per variant x capture rate x store x category, history up to the
-- cutoff only) and afterwards scores these forecasts against `retailnova.eval_ground_truth`.
--
--   cutoff  = 2025-09-08 (6 weeks before Diwali 2025-10-20); first forecast day = cutoff
--   A       = sales_only    : observed (censored) sales
--   B(rate) = demand_sensed : sales + unmet demand captured at rate 0.10 / 0.20 / 0.35 / 0.50
--   horizon = 56 days: accuracy (WAPE) is scored on the first 42 days; the extra 14 days only let the
--             replenishment simulation see a full 14-day cover window for orders placed late in the window.

CREATE OR REPLACE TABLE `retailnova.backtest_forecasts`
OPTIONS (description = "TimesFM backtest forecasts from cutoff 2025-09-08 (SIMULATED data); see evals/backtest_report.md")
AS
SELECT
  variant,
  SAFE_CAST(capture_key AS FLOAT64) AS capture_rate,
  store_id,
  category,
  DATE(forecast_timestamp) AS forecast_date,
  GREATEST(0.0, forecast_value) AS forecast_value,
  GREATEST(0.0, prediction_interval_lower_bound) AS lower,
  GREATEST(0.0, prediction_interval_upper_bound) AS upper,
  'TimesFM' AS model,
  CURRENT_TIMESTAMP() AS run_at
FROM AI.FORECAST(
  (SELECT date, variant, capture_key, store_id, category, y
   FROM `retailnova.backtest_input`
   WHERE date < '2025-09-08'),
  data_col => 'y', timestamp_col => 'date',
  id_cols => ['variant', 'capture_key', 'store_id', 'category'],
  horizon => 56, confidence_level => 0.9);
