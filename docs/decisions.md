# Decisions log (append only)

| # | Date (IST) | Decision | Why |
|---|---|---|---|
| D1 | 2026-10-17 | The product is **RetailNova**, for a fictional retailer **Nova Bazaar** (6 South-India stores plus online) | Close to the real context for Indian festive retail, with no real brands impersonated |
| D2 | 2026-10-17 | Core insight: **censored demand**, meaning unmet asks are captured as signals | Sales-only forecasts systematically under-predict demand for items that sell out |
| D3 | 2026-10-17 | All resources in **asia-south1**; Gemini uses the `global` endpoint | Low latency for India; `AI.FORECAST` verified in asia-south1 |
| D4 | 2026-10-17 | Models: `gemini-3.8-flash` for agents, `gemini-3.5-flash-lite` for extraction and fallback, `gemini-embedding-2` (768-dim), `gemini-3.1-flash-image` for catalog photos | Each verified on Agent Platform; balances quality, latency and cost |
| D5 | 2026-10-17 | Forecasting with BigQuery `AI.FORECAST` (TimesFM), per store × category, in two variants (`sales_only`, `demand_sensed`) | No training or model management; the two variants make the insight visible |
| D6 | 2026-10-17 | Keyless runtime auth through the Cloud Run service account | Nothing to leak; least privilege |
| D7 | 2026-10-18 | Catalog of **72 SKUs** (6 categories × 12) | Fits the time budget while keeping variety |
| D8 | 2026-10-18 | The ops plan fans out with ADK agents and `asyncio`, not a full graph runtime | Same parallel behaviour, lower delivery risk |
| D9 | 2026-10-18 | No login; sessions are browser UUIDs | Judges get to value in under 2 minutes |
| D10 | 2026-10-18 | Firebase Hosting serves the UI and rewrites `/api/**` to Cloud Run | One origin, so no CORS; both required services are used |
| D11 | 2026-10-18 | Demo clock fixed at 2026-10-18; Diwali 2026-11-08 | A stable, reproducible story (confirmed with Search grounding) |
| D12 | 2026-10-18 | The primary agent model is **`gemini-3.6-flash`** (GA), with `gemini-3.5-flash-lite` as a hedged fallback | Measured on 18 Oct with a tool-calling prompt: 3.6 Flash median 1.3 s vs 3.8 Flash 7.5 s (up to 20 s and timeouts). Judges need fast, reliable turns |
