# RetailNova: every conversation is a demand signal

**AI Builder Cup 2026 · Retail & Commerce: Intelligent Customer and Business Experiences · Team RetailNova (Manoj T, Suvetha)**

| | |
|---|---|
| **Live prototype (no login)** | https://retailnova-ai.web.app |
| **Demo video** | _link added at submission_ |
| **Pitch deck** | [`docs/submission/RetailNova-Prototype-Deck.pdf`](docs/submission/) |
| **API (Cloud Run)** | https://retailnova-api-569310655517.asia-south1.run.app/api/health |

RetailNova is a pair of Gemini agents for a multi-store retailer, built on Google Cloud:
- a **shopping concierge** for customers
- a **demand copilot** for store managers

They are joined by one loop: what shoppers *ask for but can't buy* becomes the signal that decides what stores stock next.

> All data is **synthetic**. Nova Bazaar is a fictional 6-store South Indian festive retailer plus an online store.

---

## Try it in 2 minutes

1. Open **https://retailnova-ai.web.app** and choose **Live Loop**. The shopper is on the left; the store manager is on the right.
2. Tap the sample prompt **"Diwali ke liye maroon silk saree chahiye, 5000 tak, T-Nagar se pickup"**. You'll see:
   - live tool-activity chips
   - product cards **grounded in the real catalog**, with stock in every store
   - an honest **"Sold out at T. Nagar"**, plus where the item *is* available
3. Tap **Notify me**. Within seconds the **demand signal** appears in the manager's live feed.
4. Click **Generate Diwali action plan**. Four data steps run in parallel (forecast, unmet demand, inventory, transfer options). Gemini then proposes transfers and reorders with evidence, confidence and the revenue protected.
5. **Approve** the transfer. Inventory moves (RS Puram −12, T. Nagar +12), and the shopper's phone shows **"Reserved for you at T. Nagar"**. The loop is closed.

| Try also (shopper) | Try also (manager) |
|---|---|
| "Kanchipuram pattu pudavai irukka? Budget 6000" (Tamil) | "Why are we losing saree sales at T. Nagar this week?" |
| "Do you have a royal blue kurta in size L?" | "Which stores have surplus I can transfer?" |
| 📷 **Try a sample photo** (image search) | Switch store or category on the Demand Radar |
| "Gift ideas under ₹1000 for Diwali" | ⋯ menu → **Reset demo** to start fresh |

---

## The problem: stockouts hide demand

Retailers forecast from what they **sold**. When an item is out of stock, its demand never reaches the sales data.

1. Out-of-stock items record **zero sales**.
2. The forecast concludes the item "doesn't sell".
3. The next order is smaller, so the gap repeats every season.

The shopper who asked for a maroon silk saree before Diwali and walked away is never counted.

- **$1.2 trillion** is lost to out-of-stocks globally every year (IHL Group, 2025).
- **37%** of shoppers go to another store when an item is unavailable (IGD).
- **₹5.40 lakh crore** of goods traded between Navratri and Diwali 2025, with about **85% through physical retail** (CAIT).

Sources: [`docs/sources.md`](docs/sources.md).

## What RetailNova does

```mermaid
flowchart LR
  A["🛍️ Shopper asks<br/>(English · Hinglish · Tamil · photo)"] --> B["Concierge agent<br/>Gemini + tools"]
  B -->|grounded cards, stock per store,<br/>reserve / notify-me| A
  B --> C["Signal extractor<br/>Gemini Flash-Lite → DemandSignal"]
  C --> D[("Firestore<br/>live signals")]
  D --> E["Demand Radar<br/>unmet demand vs forecasts"]
  F[("BigQuery<br/>AI.FORECAST · TimesFM")] --> G
  D --> G["Ops planner<br/>parallel data steps → Gemini plan"]
  G --> H["Manager approves<br/>(human in the loop)"]
  H -->|inventory moves| D
  H -->|"Reserved for you"| A
```

| For shoppers | For retailers |
|---|---|
| Answers in their own language, **only from the real catalog and live stock** | Sees **unmet demand** that sales data hides, live, by store, product and attribute |
| No dead ends: another store, an alternative, **reserve** or **notify me** | Two forecasts side by side: **sales-only** vs **demand-sensed** (TimesFM + festival calendar) |
| Photo search: "something like this in blue" | An agentic **action plan** (transfers and reorders) with evidence, confidence and ₹ impact |
| Hears back automatically when stock arrives | **One-click approval** updates inventory and notifies waiting shoppers |

## Architecture

```mermaid
flowchart TB
  U["Browser / phone"] -->|HTTPS| H["Firebase Hosting<br/>React UI on global CDN"]
  H -->|"/api/** rewrite (JSON)"| R
  U -->|"SSE streams (chat · plan · ask)"| R["Cloud Run: retailnova-api<br/>FastAPI + Agent Development Kit"]
  U -.->|"live listeners (read-only rules)"| FS
  R -->|"Gemini 3.6 Flash · Flash-Lite · Embedding 2"| G["Gemini on Agent Platform"]
  R --> FS[("Firestore<br/>catalog + vectors · inventory · signals · plans")]
  R --> BQ[("BigQuery<br/>2-yr sales · AI.FORECAST (TimesFM) · backtest")]
```

### How each Google service is used

| Google service | Role in RetailNova | Code |
|---|---|---|
| **Gemini 3.6 Flash** on Agent Platform | Concierge reasoning and tool calling, image understanding, multilingual replies, ops planning (structured output), manager Q&A | `backend/app/agents/` |
| **Gemini 3.5 Flash-Lite** | Structured `DemandSignal` extraction (JSON schema); hedged fallback when the primary model is slow | `backend/app/agents/extractor.py`, `backend/app/llm.py` |
| **Gemini Embedding 2** | 768-dim product vectors for semantic search, plus Firestore **vector search** (`find_nearest`) | `data/gen_embeddings.py`, `backend/app/tools/catalog.py` |
| **Gemini 3.1 Flash Image** | Generated the consistent 72-photo catalog (AI-generated, labelled synthetic) | `data/gen_images.py` |
| **Agent Development Kit (ADK)** | Agents, function tools, sessions, streamed events | `backend/app/agents/concierge.py` |
| **Cloud Run** | Serverless agent API; keyless service identity; 1 warm instance; autoscaling | `backend/Dockerfile`, `scripts/deploy.sh` |
| **Firebase Hosting** | UI on a global CDN; same-origin rewrite of `/api` to Cloud Run | `firebase.json` |
| **Firestore** | Catalog and vectors, inventory, demand signals, plans, actions, notifications; **real-time listeners** in the UI; read-only rules for browsers | `firestore.rules`, `web/src/lib/realtime.ts` |
| **BigQuery + `AI.FORECAST` (TimesFM)** | 2 years of daily sales; per-store, per-category forecasts with no model training; backtest analytics | `bigquery/`, `data/run_forecast.py`, `evals/backtest.py` |
| Cloud Build · Artifact Registry · Cloud Monitoring | Container builds, uptime checks with email alerts, budget alerts | `scripts/deploy.sh` |

Gemini runs through Agent Platform using the Cloud Run **service account**. There are **no API keys** anywhere in the backend.

## Results (measured, reported as is)

### Concierge evaluation: 30 cases against the deployed API
| Metric | Result |
|---|---|
| Grounding: recommended products exist, at the catalog price | **100%** (68/68) |
| Stock counts and badges match Firestore at check time | 92% (57/62; inventory was changing during the run) |
| Budget, size and colour constraints respected | **98%** (49/50) |
| Off-topic and prompt-injection attempts refused, with no leaks | **100%** (8/8) |
| Out-of-stock honesty | 80% (4/5) |
| Demand-signal category and outcome correct | **100%** (22/22) |
| Cases passing overall | **93.3%** (28/30) |
| Chat latency, p50 / p95 | **4.3 s / 7.3 s** (first streamed event in under 0.1 s) |

Method, per-case results and failures: [`evals/concierge_report.md`](evals/concierge_report.md).

### Backtest: does sensing unmet demand help? (synthetic; true demand known)
Cutoff 2025-09-08, a 42-day horizon through the Diwali 2025 ramp, all 7 stores, and a 35% signal capture rate. Both arms use **the same pipeline the live app runs** (TimesFM plus the festival calendar) and the same replenishment policy.

| | Sales-only forecast | Demand-sensed forecast |
|---|---:|---:|
| Lost revenue (6 weeks) | ₹125.9 lakh | **₹111.9 lakh (−11.1%)** |
| Stockout days | 159 | **141** |
| Forecast error (WAPE) | 34.3% | **33.0%** |

- **Robust to the capture assumption.** From 10% to 50% capture, lost revenue falls **9.6–11.3%**. Under a replenishment policy that pre-builds festive stock, the same signals cut lost revenue by **31%** (₹30.4 lakh → ₹21.0 lakh).
- **Honest reading.** Signals move forecast *error* only modestly, because just 2.5% of the simulated history was censored. The **decisions** improve more, because the recovered demand sits on exactly the items that stock out.
- **Seasonality matters more for accuracy.** The calendar-aligned festival layer on TimesFM cuts WAPE by about 11 points (45.5% → 34.3%).
- Every arm, policy and sensitivity result is in [`evals/backtest_report.md`](evals/backtest_report.md).

## Judging criteria → where to look

| Criterion | Evidence |
|---|---|
| **Technical merit and GenAI (40%)** | Multi-agent ADK backend (`backend/app/agents/`); tool-grounded concierge with a **server-side grounding validator**; structured extraction; parallel ops plan with structured proposals; Firestore vector search; BigQuery TimesFM; hedged model fallback; streaming; keyless auth; eval suite and backtest (`evals/`) |
| **Problem alignment and impact (25%)** | Covers discovery, personalization, conversational shopping, demand planning, inventory and customer insights, across physical and digital commerce; backtest: −11% lost revenue and 18 fewer stockout days |
| **Innovation (25%)** | Turns *conversations* into *planning inputs*: censored-demand capture, plus a closed loop from the shopper's ask to the manager's approval and back to the shopper |
| **UX and solution design (10%)** | No-login Judge Mode; Live Loop split-screen; streamed agent activity; mobile-first chat; no axe accessibility issues; light and dark themes |

## Responsible AI and guardrails
- **Grounding is enforced on the server.** Only SKUs returned by this turn's tools can reach the UI, and prices and stock come from Firestore, not from the model.
- **Refusals.** The concierge declines off-topic requests and prompt injection (100% in the eval). Input size and per-session rate limits apply.
- **Human in the loop.** No inventory action executes without a manager's approval.
- **Privacy.** Signals contain no personal data and analytics are aggregated. Consent for conversation analytics, aligned with India's DPDP Act 2023, is on the roadmap.
- **Security.** The browser has **read-only** Firestore access; every write goes through the service account. The Firebase web config is fetched at runtime and the browser key is restricted to our domains. The repo holds no secrets (gitleaks clean).

## Scalability, cost and the path to production
- **Serverless end to end.** Cloud Run autoscales; Firestore and BigQuery bill per use; TimesFM runs *inside* BigQuery, so there are no GPUs and no model training.
- **Scale path:**
  - Pub/Sub for signal ingestion
  - scheduled `AI.FORECAST` runs over thousands of store × SKU series
  - Agent Runtime and Memory Bank for long-running agents and consented shopper memory
- **Pilot design.** Run 5 stores for 6 weeks before a festival. Success means fewer stockout days and recovered lost sales compared with control stores.

## Limitations (we'd rather you hear it from us)
- **Synthetic data.** The results come from a simulation. The demand-sensed forecast scales captured signals by an assumed **35% capture rate**; a real deployment would calibrate it with store audits.
- **Small eval.** The concierge eval has 30 cases with deterministic checks. Photo turns take about 10–13 s.
- **Single-instance design.** Sessions live in memory (Cloud Run session affinity and one warm instance). A larger deployment would move them to Agent Platform Sessions.
- **Trends step off.** The Google Search–grounded trend step exists but is off in this demo.
- **Shared demo state.** One judge's approval changes inventory for the next; use **⋯ → Reset demo**.

## Run it yourself
```bash
# Prerequisites: a Google Cloud project with billing, Agent Platform, Firestore (native) and BigQuery enabled.
source scripts/env.sh                                   # project, region, Agent Platform env
.venv/bin/python data/generate.py                       # synthetic history + inventory snapshot (seeded)
.venv/bin/python data/gen_embeddings.py && .venv/bin/python data/load_firestore.py
.venv/bin/python data/load_bigquery.py && .venv/bin/python data/run_forecast.py
cd backend && ../.venv/bin/uvicorn app.main:app --port 8080        # API
cd web && npm install && npm run dev                                # UI on :5173 (proxies /api)
BASE=http://localhost:8080 bash scripts/golden.sh                   # 10 end-to-end checks
scripts/deploy.sh all                                               # Cloud Run + Firebase Hosting
```
Details: [`data/README.md`](data/README.md), [`docs/architecture.md`](docs/architecture.md), [`docs/contracts.md`](docs/contracts.md).

## Repository layout
```
backend/   FastAPI + ADK agents and tools (Cloud Run)
web/       React + Vite + Tailwind UI (Firebase Hosting)
data/      seeded synthetic data generator, image + embedding generation, loaders
bigquery/  AI.FORECAST and backtest SQL
evals/     concierge eval suite, backtest, reports
docs/      PRD, architecture, API/data contracts, decisions, sources, deck builder
scripts/   env, deploy, golden end-to-end checks
```

## License
Apache-2.0. See [LICENSE](LICENSE). The product images are AI-generated for this synthetic demo.
