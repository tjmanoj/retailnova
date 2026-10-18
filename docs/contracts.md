# RetailNova contracts (single source of truth)

This file is the contract between the data pipeline (`data/`, `bigquery/`), the agent API (`backend/`) and the UI (`web/`).
Change it first, then change code. Names are exact: collection names, field names, enum values, route paths and SSE event names.

- **Demo clock.** "Today" is **2026-10-18** (`DEMO_TODAY`). Diwali is **2026-11-08**, so `days_to_diwali = 21`.
- **Money and time formats.**
  - Money is **integer INR** (`*_inr`).
  - Dates are `YYYY-MM-DD` strings.
  - Timestamps are Firestore `Timestamp`, serialised in the API as ISO-8601 UTC strings.
- **Synthetic data.** All data is synthetic, and every record created by the generator carries `source: "simulated"`.

---

## 1. Reference data

### 1.1 Stores (`store_id`)
| store_id | name | city | type | languages |
|---|---|---|---|---|
| `CHN-TNG` | T. Nagar | Chennai | store | ta, en |
| `CHN-ANN` | Anna Nagar | Chennai | store | ta, en |
| `BLR-JAY` | Jayanagar | Bengaluru | store | kn, en, hi |
| `BLR-IND` | Indiranagar | Bengaluru | store | kn, en, hi |
| `CBE-RSP` | RS Puram | Coimbatore | store | ta, en |
| `HYD-BNJ` | Banjara Hills | Hyderabad | store | te, hi, en |
| `ONLINE` | Online store | — | online | en, hi, ta |

The default store for shoppers and managers is `CHN-TNG`.

### 1.2 Categories (`category`)
| category | label | SKU prefix | sizes |
|---|---|---|---|
| `sarees` | Sarees | `SAR` | `FREE` |
| `kurta_sets` | Women's Kurta Sets | `KUR` | `S M L XL` |
| `mens_ethnic` | Men's Ethnic | `MEN` | `S M L XL XXL` |
| `home_decor` | Festive Home Decor | `DEC` | `FREE` |
| `gifting` | Festive Gifting | `GFT` | `FREE` |
| `footwear` | Ethnic Footwear | `FTW` | `6 7 8 9 10` |

There are 12 SKUs per category, 72 in total. SKU ids look like `SAR-001` … `FTW-012`.

### 1.3 Hero records (must exist exactly like this)
| What | Value |
|---|---|
| Hero SKU | `SAR-001`: "Maroon Kanchipuram Silk Saree, gold zari border", sarees, color `maroon`, material `silk`, ₹4,799 (MRP ₹5,999) |
| Hero gap | `inventory/CHN-TNG__SAR-001__FREE.on_hand = 0`, `inventory/CBE-RSP__SAR-001__FREE.on_hand = 14` |
| Hero trend | Over the last 7 days, `CHN-TNG` has ≥ 25 simulated `unmet` signals for sarees with `attributes.color = "maroon"` or `sku = "SAR-001"`, rising day by day |
| Image-search SKU | `MEN-004`: "Royal Blue Silk-Blend Kurta", mens_ethnic, color `blue`. Some sizes are in stock at CHN-TNG and L is out of stock |
| Secondary gaps | `DEC-002` (brass diya set) is low at BLR-JAY; `FTW-003` (women's juttis, size 7) is out at HYD-BNJ |

---

## 2. Firestore (database `(default)`, native mode, asia-south1)

Rules: clients may **read** `stores`, `products`, `inventory`, `demand_signals`, `plans`, `actions`, `notifications`, `meta`. Clients may **never write**. Every write goes through the backend's service account.

### `stores/{store_id}`
`store_id, name, city, type ("store"|"online"), languages: string[], lat: float|null, lng: float|null`

### `products/{sku}`
```
sku, name, category, subcategory, color, color_family, material, occasion: string[], sizes: string[],
price_inr: int, mrp_inr: int, description: string (2–3 sentences), image_url: "/products/{sku}.webp",
image_alt: string, tags: string[], embedding: Vector(768)   # gemini-embedding-2, RETRIEVAL_DOCUMENT
```
The vector index on `products.embedding` (768, flat) already exists. Query with COSINE distance.

### `inventory/{store_id}__{sku}__{size}`
`store_id, sku, size, category, on_hand: int, incoming: int, incoming_eta: "YYYY-MM-DD"|null, reorder_point: int, updated_at: Timestamp`

### `inventory_snapshot/{same id}`
This is a frozen copy of `inventory` at seed time, with the same fields. `/api/demo/reset` copies it back into `inventory`.

### `customers/{customer_id}` (synthetic)
`customer_id ("C0001"…), first_name, city, home_store_id, language ("en"|"hi"|"ta"|"te"|"kn"), preferences: {categories: string[], colors: string[], budget_max_inr: int}`

### `conversations/{session_id}`
`session_id, store_id, started_at, updated_at, turns: int, language: string, last_user_message: string (≤ 200 chars)`

### `demand_signals/{signal_id}`: see `DemandSignal` (§4)
The backend writes live ones with `source: "live"`; the generator writes `source: "simulated"` (last 30 days).

### `waitlist/{waitlist_id}`
`waitlist_id, session_id, sku, size, store_id, created_at, status ("waiting"|"notified")`

### `reservations/{reservation_id}`
`reservation_id, session_id, sku, size, store_id, created_at, hold_until: Timestamp, status ("held"|"collected"|"expired")`

### `plans/{plan_id}`
`plan_id, store_id, category: string|null, question: string|null, created_at, steps: PlanStep[], proposal_ids: string[], summary: string, model: string`

### `actions/{action_id}`: see `ActionProposal` (§4)

### `notifications/{notification_id}`: see `Notification` (§4)

### `meta/demo`
`demo_today: "2026-10-18", diwali_date: "2026-11-08", snapshot_version: string, reset_at: Timestamp, seeded_at: Timestamp`

---

## 3. BigQuery (dataset `retailnova-ai.retailnova`, asia-south1)

| table | columns | notes |
|---|---|---|
| `stores` | store_id STRING, name STRING, city STRING, type STRING | |
| `products` | sku STRING, name STRING, category STRING, color STRING, material STRING, price_inr INT64 | |
| `sales_daily` | date DATE, store_id STRING, sku STRING, category STRING, units_sold INT64, revenue_inr INT64, stock_open INT64 | **Observed** sales only (censored by stock). 2024-10-01 → 2026-10-17 |
| `eval_ground_truth` | date DATE, store_id STRING, sku STRING, category STRING, true_demand INT64, lost_units INT64 | Hidden truth. Used **only** by evals and backtest, never by the app |
| `signals_daily` | date DATE, store_id STRING, category STRING, sku STRING, unmet_units INT64, signals INT64, source STRING | Unmet demand captured from conversations (simulated history at a 35% capture rate) |
| `forecast_input` (view or table) | date DATE, store_id STRING, category STRING, units_sales INT64, units_demand_sensed INT64 | `units_demand_sensed = units_sold + unmet_units` |
| `forecasts` | store_id STRING, category STRING, forecast_date DATE, variant STRING, forecast_value FLOAT64, lower FLOAT64, upper FLOAT64, model STRING, run_at TIMESTAMP | `variant` ∈ {`sales_only`, `demand_sensed`}. Horizon is 42 days from 2026-10-18 |
| `backtest_results` | variant STRING, capture_rate FLOAT64, scope STRING, metric STRING, value FLOAT64, run_at TIMESTAMP | Long format. Metrics: `wape`, `stockout_days`, `lost_revenue_inr`, `overstock_units` |

Forecast SQL pattern (verified in asia-south1):
```sql
SELECT * FROM AI.FORECAST(
  (SELECT date, store_id, category, units_sales AS y FROM retailnova.forecast_input),
  data_col => 'y', timestamp_col => 'date', id_cols => ['store_id','category'], horizon => 42, confidence_level => 0.9)
```

---

## 4. Shared schemas

Python (Pydantic v2) is canonical. The TypeScript types in `web/src/types.ts` must match field for field.

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

Category = Literal["sarees","kurta_sets","mens_ethnic","home_decor","gifting","footwear"]

class StoreStock(BaseModel):
    store_id: str
    store_name: str
    on_hand: int                      # total across sizes
    sizes_in_stock: list[str]

class ProductCard(BaseModel):
    sku: str
    name: str
    category: Category
    color: str
    material: str
    price_inr: int
    mrp_inr: int
    image_url: str
    image_alt: str
    sizes: list[str]
    availability: list[StoreStock]    # all physical stores + ONLINE
    requested_store_id: str
    requested_store_on_hand: int
    badge: Literal["in_stock","low","out_of_stock","other_store"]
    reason: Optional[str] = None      # one line: why it was recommended

class DemandSignal(BaseModel):
    signal_id: str
    ts: str                           # ISO-8601 UTC
    date: str                         # YYYY-MM-DD
    source: Literal["live","simulated"]
    session_id: Optional[str] = None
    store_id: str
    channel: Literal["chat","image_search","store_assist"]
    category: Category
    sku: Optional[str] = None         # requested or closest SKU
    attributes: dict[str, str] = {}   # color, size, material, occasion
    price_band: Optional[dict[str, int]] = None   # {"min_inr":..,"max_inr":..}
    outcome: Literal["fulfilled","substituted","unmet"]
    reason: Optional[Literal["out_of_stock","size_unavailable","not_carried","price_too_high","other"]] = None
    quantity: int = 1
    est_value_inr: int
    intent_strength: float = Field(ge=0, le=1)
    summary: str                      # ≤ 120 chars, no personal data
    language: str = "en"

class PlanStep(BaseModel):
    id: Literal["forecast","unmet_demand","inventory","transfers","trends","planner"]
    label: str
    status: Literal["running","done","skipped","error"]
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: str = ""
    data: Optional[dict] = None

class Evidence(BaseModel):
    kind: Literal["forecast","signals","inventory","trend"]
    text: str
    value: Optional[float] = None

class ActionProposal(BaseModel):
    action_id: str
    plan_id: str
    type: Literal["transfer","reorder","markdown","assortment"]
    store_id: str                     # destination store
    category: Category
    sku: Optional[str] = None
    size: Optional[str] = None
    quantity: int
    from_store_id: Optional[str] = None      # transfers only
    supplier_lead_days: Optional[int] = None # reorders only
    eta_date: str
    rationale: str                    # ≤ 300 chars
    evidence: list[Evidence]
    confidence: float = Field(ge=0, le=1)
    expected_revenue_protected_inr: int
    status: Literal["proposed","approved","rejected","executed"] = "proposed"
    created_at: str
    decided_at: Optional[str] = None

class Notification(BaseModel):
    notification_id: str
    session_id: str
    kind: Literal["back_in_stock","reserved","transfer_eta"]
    sku: str
    store_id: str
    message: str
    created_at: str
    read: bool = False
```

---

## 5. HTTP API (Cloud Run `retailnova-api`; same origin via the Firebase Hosting rewrite `/api/**`)

- **Format.** JSON in and out. Errors are `{"error": {"code": str, "message": str}}` with a 4xx/5xx status.
- **Sessions.** `session_id` is a UUID that the browser creates and keeps in `localStorage` (`rn_session`). The Live Loop view uses the same id for both panes.

### SSE convention (POST streaming)
- The response is `Content-Type: text/event-stream`. Each event is `event: <name>\ndata: <json>\n\n`.
- The UI reads it with `fetch()` plus a stream reader (not `EventSource`, because these are POST requests).
- Every stream ends with exactly one `done` event, or with an `error` event followed by `done`.

| event | payload |
|---|---|
| `activity` | `{id: str, tool: str, label: str, status: "start"|"end"}`. The label is human-friendly, e.g. "Checking stock at T. Nagar" |
| `text` | `{delta: str}`. Append it to the current assistant message |
| `products` | `{items: ProductCard[]}` |
| `signal` | `{signal: DemandSignal}` |
| `step` | `{step: PlanStep}`. It is sent again on each status change |
| `proposal` | `{proposal: ActionProposal}` |
| `error` | `{message: str, retryable: bool}` |
| `done` | `{latency_ms: int, model: str, session_id?: str, plan_id?: str}` |

### Routes
| Method and path | Request | Response |
|---|---|---|
| `GET /api/health` | — | `{status:"ok", version:str, time:str}` |
| `GET /api/bootstrap` | — | `{demo_today, diwali_date, days_to_diwali, stores: Store[], categories: [{category,label}], sample_prompts: {shopper: str[], manager: str[]}, reset_at: str|null}` |
| `POST /api/chat` (SSE) | `{session_id, message, store_id?="CHN-TNG", image_base64?: str, image_mime?: "image/jpeg"|"image/png"|"image/webp", language_hint?: "auto"|"en"|"hi"|"ta"}` | events `activity`, `text`, `products`, `signal`, `error`, `done` |
| `POST /api/notify` | `{session_id, sku, size, store_id}` | `{waitlist_id, message}` |
| `POST /api/reserve` | `{session_id, sku, size, store_id}` | `{reservation_id, hold_until, message}` |
| `GET /api/notifications?session_id=` | — | `{items: Notification[]}`, newest first |
| `GET /api/radar?store_id=CHN-TNG&category=` | `category` optional | `Radar` (below) |
| `POST /api/plan` (SSE) | `{store_id, category?: Category, horizon_days?: 21, question?: str}` | events `step` (×n), `proposal` (×n), `text` (summary), `error`, `done{plan_id}` |
| `POST /api/ask` (SSE) | `{store_id, question, session_id?}` | events `activity`, `text`, `error`, `done` |
| `POST /api/actions/{action_id}/approve` | — | `{action: ActionProposal, inventory_changes: [{store_id, sku, size, delta, on_hand_after}], notifications_created: int}` |
| `POST /api/actions/{action_id}/reject` | — | `{action: ActionProposal}` |
| `POST /api/demo/reset` | — | `{reset_at}`. Restores `inventory` from `inventory_snapshot` and deletes live `demand_signals`, `waitlist`, `reservations`, `plans`, `actions`, `notifications` |

```
Radar = {
  store_id, as_of: "2026-10-18", days_to_diwali: 21,
  kpis: { unmet_value_7d_inr: int, unmet_units_7d: int, stockouts_now: int, signals_today: int, forecast_gap_units_21d: int },
  top_gaps: [{ category, sku: str|null, label, attributes: {..}, unmet_units_7d: int, unmet_value_7d_inr: int,
               on_hand: int, trend: "rising"|"flat"|"falling" }],          # max 6, sorted by value
  series: [{ date, actual_units: int|null, forecast_sales_only: float|null, forecast_demand_sensed: float|null,
             lower: float|null, upper: float|null, unmet_units: int|null }], # last 56 days + next 42, for the selected category (default sarees)
  recent_signals: DemandSignal[]                                        # 20 newest for this store
}
```

**Limits:**
- `message` ≤ 1,000 characters and images ≤ 1.5 MB (otherwise 413).
- 20 chat requests per 10 minutes per session, and 6 plan requests per 10 minutes per session (otherwise 429 with a friendly message).

---

## 6. Agents and models

| Agent | Model | Tools / output |
|---|---|---|
| `concierge` (ADK `LlmAgent`) | `gemini-3.8-flash`, low thinking | `search_products`, `search_by_image`, `check_availability`, `get_alternatives`, `reserve_item`, `notify_me` |
| `signal_extractor` | `gemini-3.5-flash-lite`, JSON schema = `DemandSignal` minus server fields | runs after every chat turn as a background task |
| `ops_planner` | `gemini-3.8-flash`, structured `ActionProposal[]` | inputs from the fan-out: `get_baseline_forecast`, `get_unmet_demand`, `get_inventory_position`, `get_transfer_options`, and (P1) `trend_check` with Google Search grounding |
| `manager_qa` (ADK `LlmAgent`) | `gemini-3.8-flash` | the same read-only ops tools |
| Fallback on 429/503 | `gemini-3.5-flash-lite` | — |
| Embeddings | `gemini-embedding-2`, 768-dim | `RETRIEVAL_DOCUMENT` for products, `RETRIEVAL_QUERY` for queries |
| Catalog images (offline, once) | `gemini-3.1-flash-image` | WebP ≤ 80 KB at `web/public/products/{sku}.webp` |

All Gemini calls go through Agent Platform (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`, location `global`) using the service account's identity. There are **no API keys**.

**Grounding rule.** Any SKU the concierge mentions, and any SKU in a `products` event, must come from a tool result in the same turn. The server enforces this.

---

## 7. Front end

| Route | Purpose |
|---|---|
| `/` | Judge Mode landing: pitch, 2-minute test guide, entry cards (Shopper, Store Manager, Live Loop), sample prompt chips, "SYNTHETIC DATA" badge, warm-up `GET /api/health` |
| `/shop` | Shopper chat (mobile-first) |
| `/manager` | Demand Radar plus Ops Copilot |
| `/live` | Split-screen: `/shop` on the left, `/manager` on the right, same session |

**Firestore listeners** (all single-field queries, so no composite indexes are needed):
- `demand_signals` ordered by `ts` desc, limit 50. Filter by `store_id` on the client.
- `notifications` where `session_id == <session>`. Sort on the client.
- `actions` where `plan_id == <plan>`. Sort on the client.

**Firebase web config** (public by design): project `retailnova-ai`, appId `1:569310655517:web:759a40bebfe91ceaa8c2f4`. Read the full config with `firebase apps:sdkconfig WEB <appId>`.
