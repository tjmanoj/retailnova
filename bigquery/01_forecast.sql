-- RetailNova: raw TimesFM forecasts per store x category, 42 days from DEMO_TODAY = 2026-10-18 (SIMULATED data).
--   sales_only     : observed sales (censored by stock-outs)
--   demand_sensed  : estimated true demand = sales + captured unmet / capture rate (units_demand_sensed)
-- data/run_forecast.py runs this query, keeps the raw rows in `forecasts_timesfm`, applies the festival-calendar
-- uplift (TimesFM cannot align a lunar festival across years) and writes `forecasts`.
-- Forecasts are counts, so point and lower values are floored at 0.

WITH sales_only AS (
  SELECT store_id, category, forecast_timestamp, forecast_value,
         prediction_interval_lower_bound AS lower, prediction_interval_upper_bound AS upper,
         'sales_only' AS variant
  FROM AI.FORECAST(
    (SELECT date, store_id, category, units_sales AS y FROM `retailnova.forecast_input`),
    data_col => 'y', timestamp_col => 'date', id_cols => ['store_id', 'category'],
    horizon => 42, confidence_level => 0.9)
),
demand_sensed AS (
  SELECT store_id, category, forecast_timestamp, forecast_value,
         prediction_interval_lower_bound AS lower, prediction_interval_upper_bound AS upper,
         'demand_sensed' AS variant
  FROM AI.FORECAST(
    (SELECT date, store_id, category, units_demand_sensed AS y FROM `retailnova.forecast_input`),
    data_col => 'y', timestamp_col => 'date', id_cols => ['store_id', 'category'],
    horizon => 42, confidence_level => 0.9)
)
SELECT
  store_id,
  category,
  DATE(forecast_timestamp) AS forecast_date,
  variant,
  GREATEST(0.0, forecast_value) AS forecast_value,
  GREATEST(0.0, lower) AS lower,
  GREATEST(0.0, upper) AS upper
FROM (SELECT * FROM sales_only UNION ALL SELECT * FROM demand_sensed);
