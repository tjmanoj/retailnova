# RetailNova architecture

## System
```
        Shoppers / store managers / judges (browser, phone)
                         │  https://retailnova-ai.web.app
                ┌────────▼─────────┐
                │ Firebase Hosting │  React + Vite + Tailwind (static, global CDN)
                │  /api/** rewrite │  Firestore JS SDK: live listeners (read-only rules)
                └────────┬─────────┘
                         │ same origin
          ┌──────────────▼───────────────────────────┐
          │ Cloud Run: retailnova-api (Python 3.12)  │  runs as service account retailnova-run (no API keys)
          │  FastAPI + Agent Development Kit (ADK)    │
          │   ├─ concierge      Gemini 3.6 Flash      │──▶ Gemini on Agent Platform (global endpoint)
          │   ├─ signal_extractor Gemini Flash-Lite   │
          │   ├─ ops_planner    fan-out ▶ Gemini plan │──▶ (P1) Google Search grounding
          │   └─ manager_qa     Gemini 3.6 Flash      │
          └───────┬───────────────────────┬───────────┘
                  ▼                       ▼
     Firestore (asia-south1)        BigQuery (asia-south1, dataset retailnova)
     products + vector index         sales_daily (2 yrs) · signals_daily
     inventory · demand_signals      forecasts ◀── AI.FORECAST (TimesFM)
     plans · actions · notifications backtest_results · eval_ground_truth
```

## Google services and their roles
| Service | Role in RetailNova |
|---|---|
| **Gemini 3.6 Flash** (Agent Platform) | Concierge reasoning and tool use, image understanding, multilingual chat, ops planning, manager Q&A |
| **Gemini 3.5 Flash-Lite** | Fast, cheap structured extraction of demand signals; fallback model |
| **Gemini Embedding 2** | 768-dim product vectors for semantic search and image-to-catalog matching |
| **Gemini 3.1 Flash Image** | One-off generation of a consistent catalog photo set |
| **Agent Development Kit (ADK)** | Agents, tools, sessions, streaming events |
| **Cloud Run** | Serverless agent API that autoscales and scales to zero |
| **Firebase Hosting** | Global CDN for the UI, and a same-origin rewrite to Cloud Run |
| **Firestore** | Operational store, vector search, real-time UI updates |
| **BigQuery + `AI.FORECAST` (TimesFM)** | Forecasts per store and category with no model training; backtest analytics |
| **Cloud Build + Artifact Registry** | Container builds |
| **Cloud Logging / Monitoring** | Structured logs, uptime check, budget alerts |

## Request flows
**Chat turn**
1. `POST /api/chat` starts the concierge (ADK runner).
2. Tool calls (Firestore vector search, inventory reads) are streamed to the UI as `activity` events.
3. The answer text is streamed.
4. Products pass the grounding validator and are sent as `products`.
5. In the background, Flash-Lite extracts a `DemandSignal`. It is written to Firestore and sent as a `signal` event.
6. The manager's Radar receives the signal through its Firestore listener.

**Plan**
1. `POST /api/plan` fans out in parallel: forecast (BigQuery), unmet demand (Firestore aggregate), inventory, and transfer options.
2. Each step is streamed as a `step` event.
3. Gemini produces a structured `ActionProposal[]`, which is persisted to `plans` and `actions` and streamed as `proposal` events.

**Approve**
1. `POST /api/actions/{id}/approve` writes the inventory change in a transaction.
2. Matching `waitlist` entries become `notifications`.
3. The shopper's UI receives them live.

## Security
- **Keyless auth.** Cloud Run runs as `retailnova-run` with least-privilege roles: aiplatform.user, datastore.user, bigquery.dataEditor and jobUser, logWriter, metricWriter, cloudtrace.agent.
- **Firestore rules.** Clients can only read demo collections and can never write.
- **Abuse limits.** Input size limits, a rate limit per session, and `max-instances` to bound cost. A budget alert is set on gross usage.
- **No secrets in the repo.** gitleaks runs before every push.

## Scale path (beyond the prototype)
- **Compute and storage:** Cloud Run autoscaling, and Firestore serverless scale for live operations.
- **Forecasting:** BigQuery for chain-wide history, with scheduled `AI.FORECAST` runs across thousands of store × SKU series.
- **Signals:** Pub/Sub for high-volume ingestion, with Firestore aggregates per store.
- **Agents:** Agent Runtime and Memory Bank for long-running agents and shopper memory.
- **Cost:** measured per 1,000 conversations from real token usage (see `evals/RESULTS.md`).

## v1.1 additions
| Capability | How it works |
|---|---|
| **Voice notes** | The browser records audio; Gemini 3.6 Flash transcribes it inline (any Indian language) and emits a `transcript` event; the concierge then runs on the transcript. Signal channel `voice`. |
| **Store assist** | Staff log a walk-in request by text or voice through `POST /api/assist`. Model Armor screens it, then catalog search and the extractor produce a `store_assist` signal, checked against that store's stock. Items the store doesn't carry become assortment gaps. |
| **Market trends** | The ops plan's `trends` step asks Gemini with the `google_search` tool (10 s timeout, 60-minute cache per city and category). Insights and source links feed into proposal evidence. |
| **Model Armor** | The `retailnova-shield` template (asia-south1) screens chat, ask and assist text before any tool runs. A block returns a polite refusal; on any error it fails open. |
| **Memory Bank** | Agent Platform Memory Bank (`retailnova-memory` engine) stores shopping preferences per shopper (browser id). They are recalled at the start of each turn (1.6 s cap) and written after the reply. `/api/profile` shows them and `/api/profile/forget` deletes them. |
| **Observability** | OpenTelemetry → Cloud Trace spans for requests, Model Armor, transcription and trends (alongside ADK's agent, model and tool spans). Logs carry the trace id. Uptime checks and budget alerts are in place. Cloud Scheduler resets the demo nightly. |
