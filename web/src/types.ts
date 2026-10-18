// Mirrors docs/contracts.md §4 (shared schemas) and §5 (API payloads) field for field.

export type Category = 'sarees' | 'kurta_sets' | 'mens_ethnic' | 'home_decor' | 'gifting' | 'footwear'

export interface StoreStock {
  store_id: string
  store_name: string
  on_hand: number // total across sizes
  sizes_in_stock: string[]
}

export type ProductBadge = 'in_stock' | 'low' | 'out_of_stock' | 'other_store'

export interface ProductCard {
  sku: string
  name: string
  category: Category
  color: string
  material: string
  price_inr: number
  mrp_inr: number
  image_url: string
  image_alt: string
  sizes: string[]
  availability: StoreStock[] // all physical stores + ONLINE
  requested_store_id: string
  requested_store_on_hand: number
  badge: ProductBadge
  reason?: string | null // one line: why it was recommended
}

export type SignalChannel = 'chat' | 'image_search' | 'store_assist' | 'voice'
export type SignalOutcome = 'fulfilled' | 'substituted' | 'unmet'
export type SignalReason = 'out_of_stock' | 'size_unavailable' | 'not_carried' | 'price_too_high' | 'other'

export interface DemandSignal {
  signal_id: string
  ts: string // ISO-8601 UTC
  date: string // YYYY-MM-DD
  source: 'live' | 'simulated'
  session_id?: string | null
  store_id: string
  channel: SignalChannel
  category: Category
  sku?: string | null
  attributes: Record<string, string>
  price_band?: Record<string, number> | null // {min_inr, max_inr}
  outcome: SignalOutcome
  reason?: SignalReason | null
  quantity: number
  est_value_inr: number
  intent_strength: number // 0..1
  summary: string // ≤ 120 chars
  language: string
}

export type PlanStepId = 'forecast' | 'unmet_demand' | 'inventory' | 'transfers' | 'trends' | 'planner'
export type PlanStepStatus = 'running' | 'done' | 'skipped' | 'error'

export interface PlanStep {
  id: PlanStepId
  label: string
  status: PlanStepStatus
  started_at?: string | null
  finished_at?: string | null
  summary: string
  data?: Record<string, unknown> | null
}

export type EvidenceKind = 'forecast' | 'signals' | 'inventory' | 'trend'

export interface Evidence {
  kind: EvidenceKind
  text: string
  value?: number | null
  url?: string | null // §9.4: trend evidence carries a source URL when available
}

export type ActionType = 'transfer' | 'reorder' | 'markdown' | 'assortment'
export type ActionStatus = 'proposed' | 'approved' | 'rejected' | 'executed'

export interface ActionProposal {
  action_id: string
  plan_id: string
  type: ActionType
  store_id: string // destination store
  category: Category
  sku?: string | null
  size?: string | null
  quantity: number
  from_store_id?: string | null // transfers only
  supplier_lead_days?: number | null // reorders only
  eta_date: string
  rationale: string // ≤ 300 chars
  evidence: Evidence[]
  confidence: number // 0..1
  expected_revenue_protected_inr: number
  status: ActionStatus
  created_at: string
  decided_at?: string | null
}

export type NotificationKind = 'back_in_stock' | 'reserved' | 'transfer_eta'

export interface Notification {
  notification_id: string
  session_id: string
  kind: NotificationKind
  sku: string
  store_id: string
  message: string
  created_at: string
  read: boolean
}

// ---------- Firestore reference docs (contracts §2) ----------

export interface Store {
  store_id: string
  name: string
  city: string
  type: 'store' | 'online'
  languages: string[]
  lat?: number | null
  lng?: number | null
}

// ---------- SSE events (contracts §5) ----------

export interface ActivityEvent {
  id: string
  tool: string
  label: string
  status: 'start' | 'end'
}

export interface Guardrail {
  provider: 'model_armor'
  verdict: 'blocked' | 'allowed'
  categories?: string[]
}

export interface DoneEvent {
  latency_ms: number
  model: string
  session_id?: string
  plan_id?: string
  guardrail?: Guardrail | null // §9.5
}

export interface Preference {
  key: string
  value: string
}

export interface MemoryEvent {
  summary: string
  preferences: Preference[]
}

export interface ErrorEvent {
  message: string
  retryable: boolean
}

export type SSEEvent =
  | { event: 'activity'; data: ActivityEvent }
  | { event: 'text'; data: { delta: string } }
  | { event: 'products'; data: { items: ProductCard[] } }
  | { event: 'signal'; data: { signal: DemandSignal } }
  | { event: 'step'; data: { step: PlanStep } }
  | { event: 'proposal'; data: { proposal: ActionProposal } }
  | { event: 'transcript'; data: { text: string; language: string } }
  | { event: 'memory'; data: MemoryEvent }
  | { event: 'error'; data: ErrorEvent }
  | { event: 'done'; data: DoneEvent }

export type SSEEventName = SSEEvent['event']

// ---------- REST payloads (contracts §5) ----------

export interface Features {
  voice: boolean
  store_assist: boolean
  trends: boolean
  model_armor: boolean
  memory: 'memory_bank' | 'firestore' | null
  guided_demo: boolean
}

export interface HealthResponse {
  status: 'ok'
  version: string
  time: string
  features?: Features
}

export interface Bootstrap {
  demo_today: string
  diwali_date: string
  days_to_diwali: number
  stores: Store[]
  categories: { category: Category; label: string }[]
  sample_prompts: { shopper: string[]; manager: string[] }
  reset_at: string | null
  features?: Features // §9.1
}

export interface ChatRequest {
  session_id: string
  message: string
  store_id?: string
  image_base64?: string
  image_mime?: 'image/jpeg' | 'image/png' | 'image/webp'
  audio_base64?: string // §9.2
  audio_mime?: AudioMime
  language_hint?: 'auto' | 'en' | 'hi' | 'ta'
}

export type AudioMime = 'audio/webm' | 'audio/ogg' | 'audio/mp4' | 'audio/mpeg' | 'audio/wav'

export interface AssistRequest {
  store_id: string
  text?: string
  audio_base64?: string
  audio_mime?: AudioMime
}

export interface AssistResponse {
  signal: DemandSignal | null
  transcript: string | null
  message: string
}

export interface Profile {
  session_id: string
  summary: string
  preferences: Preference[]
  source: 'memory_bank' | 'firestore' | null
  updated_at: string | null
}

export interface ItemRequest {
  session_id: string
  sku: string
  size: string
  store_id: string
}

export interface NotifyResponse {
  waitlist_id: string
  message: string
}

export interface ReserveResponse {
  reservation_id: string
  hold_until: string
  message: string
}

export interface PlanRequest {
  store_id: string
  category?: Category
  horizon_days?: number
  question?: string
  session_id?: string // optional; the backend uses it only for rate limiting
}

export interface AskRequest {
  store_id: string
  question: string
  session_id?: string
}

export interface InventoryChange {
  store_id: string
  sku: string
  size: string
  delta: number
  on_hand_after: number
  // Reorders only (contracts §8): on hand is unchanged, stock is incoming.
  incoming_delta?: number | null
  incoming_after?: number | null
  incoming_eta?: string | null
}

export interface ApproveResponse {
  action: ActionProposal
  inventory_changes: InventoryChange[]
  notifications_created: number
}

export interface RejectResponse {
  action: ActionProposal
}

export interface ResetResponse {
  reset_at: string
}

export type GapTrend = 'rising' | 'flat' | 'falling'

export interface RadarGap {
  category: Category
  sku: string | null
  label: string
  attributes: Record<string, string>
  unmet_units_7d: number
  unmet_value_7d_inr: number
  on_hand: number
  trend: GapTrend
}

export interface RadarPoint {
  date: string
  actual_units: number | null
  forecast_sales_only: number | null
  forecast_demand_sensed: number | null
  lower: number | null
  upper: number | null
  unmet_units: number | null
}

export interface Radar {
  store_id: string
  as_of: string
  days_to_diwali: number
  kpis: {
    unmet_value_7d_inr: number
    unmet_units_7d: number
    stockouts_now: number
    signals_today: number
    forecast_gap_units_21d: number
    revenue_protected_inr?: number // §9.7
  }
  top_gaps: RadarGap[]
  series: RadarPoint[]
  recent_signals: DemandSignal[]
  assortment_gaps?: AssortmentGap[] // §9.7
}

export interface AssortmentGap {
  label: string
  category: Category
  asks_7d: number
  est_value_7d_inr: number
  examples: string[]
}

export interface ApiErrorBody {
  error: { code: string; message: string }
}
