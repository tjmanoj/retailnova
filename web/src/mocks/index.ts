// Mock backend used only when mock mode is on (VITE_MOCK=1 or ?mock=1). Loaded with a dynamic import.
import type {
  ActionProposal,
  ApproveResponse,
  Category,
  AssistRequest,
  ChatRequest,
  DemandSignal,
  Profile,
  ItemRequest,
  Notification,
  PlanRequest,
  AskRequest,
  SSEEvent,
} from '../types'
import { storeName } from '../lib/constants'
import { ApiError } from '../lib/api'
import { bootstrap, makeRadar, planProposals, planSteps, planSummary, productSeeds, seedBySku, seedSignals, toCard } from './fixtures'

// ---------- in-memory state ----------
const state = {
  signals: seedSignals(),
  notifications: [] as Notification[],
  waitlist: [] as ItemRequest[],
  actions: new Map<string, ActionProposal>(),
  liveUnmet: 0,
  profiles: new Map<string, Profile>(),
  revenueProtected: 0,
}

const signalSubs = new Set<(s: DemandSignal[]) => void>()
const notifSubs = new Map<(n: Notification[]) => void, string>()

function publishSignals() {
  const sorted = [...state.signals].sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 50)
  signalSubs.forEach((cb) => cb(sorted))
}
function publishNotifications() {
  notifSubs.forEach((sid, cb) => cb(state.notifications.filter((n) => n.session_id === sid)))
}

export function mockSubscribeSignals(cb: (s: DemandSignal[]) => void) {
  signalSubs.add(cb)
  setTimeout(publishSignals, 250)
  return () => {
    signalSubs.delete(cb)
  }
}

export function mockSubscribeNotifications(sessionId: string, cb: (n: Notification[]) => void) {
  notifSubs.set(cb, sessionId)
  setTimeout(() => cb(state.notifications.filter((n) => n.session_id === sessionId)), 200)
  return () => {
    notifSubs.delete(cb)
  }
}

export async function mockProductInfo(sku: string) {
  const p = seedBySku(sku)
  return p ? { name: p.name, image_url: `/products/${sku}.webp`, image_alt: p.image_alt } : null
}

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('aborted', 'AbortError'))
    })
  })

const uid = () => Math.random().toString(36).slice(2, 10)

// ---------- REST ----------
export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  await wait(220 + Math.random() * 200)
  const url = new URL(path, 'http://mock')
  const p = url.pathname
  const b = (body ?? {}) as Record<string, unknown>

  if (p === '/api/health') return { status: 'ok', version: 'mock', time: new Date().toISOString() } as T
  if (p === '/api/bootstrap') return bootstrap as T
  if (p === '/api/radar') {
    const store = url.searchParams.get('store_id') || 'CHN-TNG'
    const cat = (url.searchParams.get('category') || 'sarees') as Category
    const r = makeRadar(store, cat, store === 'CHN-TNG' && cat === 'sarees' ? state.liveUnmet : 0)
    r.kpis.revenue_protected_inr = store === 'CHN-TNG' ? state.revenueProtected : 0
    r.recent_signals = [...state.signals].filter((s) => s.store_id === store).sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 20)
    return r as T
  }
  if (p === '/api/notify') {
    const req = b as unknown as ItemRequest
    state.waitlist.push(req)
    const name = seedBySku(req.sku)?.name ?? req.sku
    return { waitlist_id: `wl-${uid()}`, message: `We'll tell you as soon as ${name} is back at ${storeName(req.store_id)}.` } as T
  }
  if (p === '/api/reserve') {
    const req = b as unknown as ItemRequest
    const hold = new Date(Date.now() + 48 * 3600_000).toISOString()
    return {
      reservation_id: `rs-${uid()}`,
      hold_until: hold,
      message: `Reserved at ${storeName(req.store_id)}. We'll hold it for 48 hours.`,
    } as T
  }
  if (p === '/api/notifications') {
    const sid = url.searchParams.get('session_id')
    return { items: state.notifications.filter((n) => n.session_id === sid) } as T
  }
  const m = p.match(/^\/api\/actions\/([^/]+)\/(approve|reject)$/)
  if (m) {
    const a = state.actions.get(decodeURIComponent(m[1]))
    if (!a) throw new ApiError(404, 'not_found', 'That proposal no longer exists. Generate a new plan.')
    const decided = { ...a, status: m[2] === 'approve' ? 'executed' : 'rejected', decided_at: new Date().toISOString() } as ActionProposal
    if (m[2] === 'approve') state.revenueProtected += a.expected_revenue_protected_inr
    state.actions.set(a.action_id, decided)
    if (m[2] === 'reject') return { action: decided } as T
    const changes =
      a.type === 'transfer' && a.from_store_id
        ? [
            { store_id: a.store_id, sku: a.sku ?? '', size: a.size ?? 'FREE', delta: a.quantity, on_hand_after: a.quantity },
            { store_id: a.from_store_id, sku: a.sku ?? '', size: a.size ?? 'FREE', delta: -a.quantity, on_hand_after: 14 - a.quantity },
          ]
        : [
            {
              store_id: a.store_id,
              sku: a.sku ?? '',
              size: a.size ?? 'FREE',
              delta: 0,
              on_hand_after: 0,
              incoming_delta: a.quantity,
              incoming_after: a.quantity,
              incoming_eta: a.eta_date,
            },
          ]
    let created = 0
    if (a.type === 'reorder') {
      const waiting = state.waitlist.filter((w) => w.sku === a.sku)
      const sessions = new Set(waiting.map((w) => w.session_id))
      created = sessions.size
      setTimeout(() => {
        for (const sid of sessions) {
          state.notifications.unshift({
            notification_id: `nt-${uid()}`,
            session_id: sid,
            kind: 'transfer_eta',
            sku: a.sku ?? '',
            store_id: a.store_id,
            message: `More ${seedBySku(a.sku ?? '')?.name ?? a.sku} is on order for ${storeName(a.store_id)} and should arrive by ${a.eta_date.slice(8, 10)} Oct.`,
            created_at: new Date().toISOString(),
            read: false,
          })
        }
        publishNotifications()
      }, 900)
    }
    if (a.type === 'transfer') {
      const waiting = state.waitlist.filter((w) => w.sku === a.sku && w.store_id === a.store_id)
      const sessions = new Set(waiting.map((w) => w.session_id))
      created = sessions.size + 2 // plus simulated shoppers on the waitlist
      state.waitlist = state.waitlist.filter((w) => !(w.sku === a.sku && w.store_id === a.store_id))
      setTimeout(() => {
        for (const sid of sessions) {
          state.notifications.unshift({
            notification_id: `nt-${uid()}`,
            session_id: sid,
            kind: 'reserved',
            sku: a.sku ?? '',
            store_id: a.store_id,
            message: `Reserved for you at ${storeName(a.store_id)}: ${seedBySku(a.sku ?? '')?.name ?? a.sku}. It arrives on 20 Oct and we'll hold it for 48 hours.`,
            created_at: new Date().toISOString(),
            read: false,
          })
        }
        publishNotifications()
      }, 900)
    }
    const res: ApproveResponse = { action: decided, inventory_changes: changes, notifications_created: created }
    return res as T
  }
  if (p === '/api/demo/reset') {
    state.signals = seedSignals()
    state.notifications = []
    state.waitlist = []
    state.actions.clear()
    state.liveUnmet = 0
    state.revenueProtected = 0
    publishSignals()
    publishNotifications()
    return { reset_at: new Date().toISOString() } as T
  }
  if (p === '/api/profile') {
    const sid = url.searchParams.get('session_id') ?? ''
    return (state.profiles.get(sid) ?? { session_id: sid, summary: '', preferences: [], source: 'firestore', updated_at: null }) as T
  }
  if (p === '/api/profile/forget') {
    state.profiles.delete(String(b.session_id ?? ''))
    return { forgotten: true } as T
  }
  if (p === '/api/assist') {
    const req = b as unknown as AssistRequest
    await wait(900)
    const transcript = req.audio_base64 ? 'Customer wanted a red Banarasi saree, free size, about ₹8,000. We had none.' : null
    const text = (req.text || transcript || '').toLowerCase()
    const banarasi = text.includes('banarasi')
    const now = new Date()
    const sig: DemandSignal = {
      signal_id: `live-${uid()}`,
      ts: now.toISOString(),
      date: now.toISOString().slice(0, 10),
      source: 'live',
      session_id: null,
      store_id: req.store_id,
      channel: 'store_assist',
      category: 'sarees',
      sku: null,
      attributes: banarasi ? { color: 'red', material: 'banarasi silk' } : {},
      price_band: { max_inr: 8000 },
      outcome: 'unmet',
      reason: banarasi ? 'not_carried' : 'out_of_stock',
      quantity: 1,
      est_value_inr: 8000,
      intent_strength: 0.8,
      summary: banarasi ? 'Walk-in wanted a red Banarasi silk saree around ₹8,000; not carried here' : `Walk-in request: ${(req.text || transcript || '').slice(0, 90)}`,
      language: 'en',
    }
    state.signals.unshift(sig)
    publishSignals()
    return { signal: sig, transcript, message: `Logged as unmet demand at ${storeName(req.store_id)}.` } as T
  }
  void method
  throw new ApiError(404, 'not_found', `No mock for ${path}`)
}

// ---------- SSE ----------
type Emit = (e: SSEEvent) => void

async function streamText(emit: Emit, text: string, signal?: AbortSignal) {
  const parts = text.match(/\S+\s*/g) ?? [text]
  for (const part of parts) {
    await wait(22 + Math.random() * 30, signal)
    emit({ event: 'text', data: { delta: part } })
  }
}

async function activity(emit: Emit, tool: string, label: string, ms: number, signal?: AbortSignal) {
  const id = `${tool}-${uid()}`
  emit({ event: 'activity', data: { id, tool, label, status: 'start' } })
  await wait(ms, signal)
  emit({ event: 'activity', data: { id, tool, label, status: 'end' } })
}

function makeSignal(req: ChatRequest, partial: Partial<DemandSignal>): DemandSignal {
  const now = new Date()
  return {
    signal_id: `live-${uid()}`,
    ts: now.toISOString(),
    date: now.toISOString().slice(0, 10),
    source: 'live',
    session_id: req.session_id,
    store_id: req.store_id ?? 'CHN-TNG',
    channel: req.image_base64 ? 'image_search' : 'chat',
    category: 'sarees',
    sku: null,
    attributes: {},
    price_band: null,
    outcome: 'fulfilled',
    reason: null,
    quantity: 1,
    est_value_inr: 0,
    intent_strength: 0.8,
    summary: '',
    language: 'en',
    ...partial,
  }
}

async function chatStream(req: ChatRequest, emit: Emit, signal?: AbortSignal) {
  const t0 = performance.now()
  const store = req.store_id ?? 'CHN-TNG'
  const here = storeName(store)
  const msg = req.message.toLowerCase()

  if (/ignore (all|previous|your) (previous )?instructions|system prompt|jailbreak/i.test(req.message)) {
    await streamText(emit, "I can only help with shopping at Nova Bazaar. Tell me what you're looking for and I'll check stock for you.", signal)
    emit({ event: 'done', data: { latency_ms: Math.round(performance.now() - t0), model: 'mock', guardrail: { provider: 'model_armor', verdict: 'blocked', categories: ['prompt_injection'] } } })
    return
  }

  let heard = ''
  if (req.audio_base64) {
    await activity(emit, 'transcribe', 'Listening to your voice note', 1600, signal)
    heard = 'தீபாவளிக்கு மெரூன் பட்டுப் புடவை வேண்டும், ஐந்தாயிரம் ரூபாய்க்குள்'
    emit({ event: 'transcript', data: { text: heard, language: 'ta' } })
  }

  if (msg.includes('fail') || msg.includes('error')) {
    await activity(emit, 'search_products', 'Searching the catalog', 600, signal)
    emit({ event: 'error', data: { message: 'The concierge took too long to answer. Try again.', retryable: true } })
    emit({ event: 'done', data: { latency_ms: Math.round(performance.now() - t0), model: 'mock' } })
    return
  }

  let products: string[] = []
  let text = ''
  let sig: Partial<DemandSignal> | null = null
  const reasons: Record<string, string> = {}

  if (req.image_base64) {
    await activity(emit, 'search_products', 'Looking at your photo', 2600, signal)
    await activity(emit, 'check_availability', `Checking stock at ${here}`, 700, signal)
    products = ['MEN-004', 'MEN-007']
    reasons['MEN-004'] = 'Closest match to your photo: royal blue, silk blend, mandarin collar'
    reasons['MEN-007'] = 'Festive silk set if you want a different look'
    text = `That looks like our Royal Blue Silk-Blend Kurta. ${here} has it in S, M, XL and XXL, but size L is sold out here. Anna Nagar and RS Puram have L in stock, or I can notify you when it's back.`
    sig = { category: 'mens_ethnic', sku: 'MEN-004', attributes: { color: 'blue', size: 'L' }, outcome: 'substituted', reason: 'size_unavailable', est_value_inr: 1899, summary: 'Photo match: royal blue kurta; size L unavailable here' }
  } else if (heard || /saree|sari|maroon|silk|kanchi|புடவை|पट्टु|पट्टू/.test(msg)) {
    const known = state.profiles.get(req.session_id)
    if (known && known.preferences.length) emit({ event: 'memory', data: { summary: known.summary, preferences: known.preferences } })
    await activity(emit, 'search_products', 'Searching the catalog for maroon silk sarees', 900, signal)
    await activity(emit, 'check_availability', `Checking stock at ${here}`, 650, signal)
    await activity(emit, 'get_alternatives', 'Looking at nearby stores and alternatives', 700, signal)
    products = ['SAR-001', 'SAR-005', 'SAR-003']
    reasons['SAR-001'] = 'Exact match: maroon Kanchipuram silk with gold zari, under ₹5,000'
    reasons['SAR-005'] = 'Same maroon family in soft silk, in stock here'
    reasons['SAR-003'] = 'Festive mustard with a temple border, in stock here'
    text = `The Maroon Kanchipuram Silk Saree with the gold zari border is ₹4,799, but it's sold out at ${here} right now. RS Puram in Coimbatore has 14. Tap Notify me and I'll tell you the moment it's back at ${here}. If you'd like something today, the Wine Maroon Soft Silk Saree (₹3,299) is in the same colour family and in stock here.`
    sig = { category: 'sarees', sku: 'SAR-001', attributes: { color: 'maroon', material: 'silk', occasion: 'diwali' }, price_band: { min_inr: 3000, max_inr: 5000 }, outcome: 'unmet', reason: 'out_of_stock', est_value_inr: 4799, intent_strength: 0.92, summary: `Asked for maroon Kanchipuram silk saree under ₹5,000 for Diwali; out of stock at ${here}` }
  } else if (/kurta|blue/.test(msg)) {
    await activity(emit, 'search_products', 'Searching the catalog for blue kurtas', 800, signal)
    await activity(emit, 'check_availability', `Checking stock at ${here}`, 600, signal)
    products = ['MEN-004', 'MEN-007']
    text = `The Royal Blue Silk-Blend Kurta is ₹1,899. ${here} is out of size L, but Anna Nagar has 3 and RS Puram has 4.`
    sig = { category: 'mens_ethnic', sku: 'MEN-004', attributes: { color: 'blue', size: 'L' }, outcome: 'unmet', reason: 'size_unavailable', est_value_inr: 1899, summary: `Royal blue kurta in L; size out at ${here}` }
  } else if (/diya|lamp|decor|puja/.test(msg)) {
    await activity(emit, 'search_products', 'Searching festive home decor', 700, signal)
    await activity(emit, 'check_availability', `Checking stock at ${here}`, 500, signal)
    products = ['DEC-002']
    text = `The Brass Diya Set of 5 is ₹1,299 and ${here} has plenty in stock. Want me to hold one for pickup?`
    sig = { category: 'home_decor', sku: 'DEC-002', attributes: { material: 'brass' }, outcome: 'fulfilled', est_value_inr: 1299, summary: 'Brass diya set for puja; in stock' }
  } else if (/jutti|footwear|chappal|size 7/.test(msg)) {
    await activity(emit, 'search_products', 'Searching ethnic footwear', 700, signal)
    await activity(emit, 'check_availability', `Checking stock at ${here}`, 500, signal)
    products = ['FTW-003']
    text = `Our Women's Embroidered Juttis in maroon and gold are ₹1,299. ${here} has size 7 in stock, 3 pairs left.`
    sig = { category: 'footwear', sku: 'FTW-003', attributes: { size: '7' }, outcome: 'fulfilled', est_value_inr: 1299, summary: 'Embroidered juttis, size 7; in stock' }
  } else {
    await activity(emit, 'search_products', 'Searching the catalog', 700, signal)
    text = `I can help you find festive sarees, kurtas, home decor, gifts and footwear across Nova Bazaar stores. What are you shopping for, and is there a colour or budget in mind?`
  }

  if (sig && sig.category === 'sarees') {
    state.profiles.set(req.session_id, {
      session_id: req.session_id,
      summary: 'Likes maroon silk sarees for Diwali, budget up to ₹5,000, picks up at T. Nagar.',
      preferences: [
        { key: 'colour', value: 'maroon' },
        { key: 'fabric', value: 'silk' },
        { key: 'budget_max_inr', value: '5000' },
        { key: 'occasion', value: 'Diwali' },
      ],
      source: 'firestore',
      updated_at: new Date().toISOString(),
    })
  }
  if (heard && sig) sig.channel = 'voice'
  await streamText(emit, text, signal)
  if (products.length) {
    const items = products.map((sku) => toCard(seedBySku(sku) ?? productSeeds[0], store, reasons[sku]))
    // Like the real service, cards can arrive in more than one products event.
    emit({ event: 'products', data: { items: items.slice(0, 1) } })
    if (items.length > 1) {
      await wait(250, signal)
      emit({ event: 'products', data: { items } })
    }
  }
  if (sig) {
    await wait(500, signal)
    const s = makeSignal(req, sig)
    state.signals.unshift(s)
    if (s.outcome === 'unmet' && s.store_id === 'CHN-TNG' && s.category === 'sarees') state.liveUnmet += 1
    publishSignals()
    emit({ event: 'signal', data: { signal: s } })
  }
  emit({ event: 'done', data: { latency_ms: Math.round(performance.now() - t0), model: 'mock', session_id: req.session_id } })
}

async function planStream(req: PlanRequest, emit: Emit, signal?: AbortSignal) {
  const t0 = performance.now()
  const planId = `plan-${uid()}`
  const steps = planSteps(req.store_id)
  const start = performance.now()
  const timeline: { at: number; e: SSEEvent }[] = []
  for (const s of steps) {
    timeline.push({ at: s.delayStart, e: { event: 'step', data: { step: { ...s.step, status: 'running', summary: '', started_at: new Date().toISOString() } } } })
    timeline.push({ at: s.delayDone, e: { event: 'step', data: { step: { ...s.step, started_at: new Date().toISOString(), finished_at: new Date().toISOString() } } } })
  }
  timeline.sort((a, b) => a.at - b.at)
  for (const t of timeline) {
    const delay = t.at - (performance.now() - start)
    if (delay > 0) await wait(delay, signal)
    emit(t.e)
  }
  await streamText(emit, planSummary, signal)
  for (const p of planProposals(planId, req.store_id)) {
    await wait(350, signal)
    state.actions.set(p.action_id, p)
    emit({ event: 'proposal', data: { proposal: p } })
  }
  emit({ event: 'done', data: { latency_ms: Math.round(performance.now() - t0), model: 'mock', plan_id: planId } })
}

async function askStream(req: AskRequest, emit: Emit, signal?: AbortSignal) {
  const t0 = performance.now()
  await activity(emit, 'get_unmet_demand', 'Reading unmet demand', 700, signal)
  await activity(emit, 'get_baseline_forecast', 'Reading the forecasts', 600, signal)
  if (/morning brief/i.test(req.question)) {
    await activity(emit, 'get_inventory_position', 'Checking stock positions', 600, signal)
    const store = storeName(req.store_id)
    const brief = `**What changed since yesterday**
- 14 new demand signals at ${store}, 9 of them unmet. Maroon Kanchipuram silk is the top ask.
- SAR-001 has been out of stock for 9 days. RS Puram still holds 14.
- Walk-ins asked for red Banarasi silk 3 times. We don't carry it.

**Top 3 risks before Diwali (21 days)**
- SAR-001 stays out of stock through the peak week: about ₹1.9 lakh at risk.
- Size L in the Royal Blue Silk-Blend Kurta is out; 6 asks this week.
- Brass diya sets are low at Jayanagar, which shares suppliers with us.

**3 actions for today**
- Approve the 12-unit SAR-001 transfer from RS Puram (arrives 20 Oct).
- Reorder 40 units of SAR-001 so stock lands 12 days before Diwali.
- Review the assortment gap for red Banarasi silk with the buying team.`
    await streamText(emit, brief, signal)
    emit({ event: 'done', data: { latency_ms: Math.round(performance.now() - t0), model: 'mock' } })
    return
  }
  const text = `At ${storeName(req.store_id)}, the biggest gap is the Maroon Kanchipuram Silk Saree (SAR-001): 27 shoppers asked for it in the last 7 days while it was out of stock, about ₹1.3 lakh of demand that never reached the sales data. That's why the demand-sensed forecast runs well above the sales-only one into Diwali.`
  await streamText(emit, text, signal)
  emit({ event: 'done', data: { latency_ms: Math.round(performance.now() - t0), model: 'mock' } })
}

export async function mockStream(path: string, body: unknown, onEvent: (e: SSEEvent) => void, signal?: AbortSignal) {
  try {
    if (path === '/api/chat') return await chatStream(body as ChatRequest, onEvent, signal)
    if (path === '/api/plan') return await planStream(body as PlanRequest, onEvent, signal)
    if (path === '/api/ask') return await askStream(body as AskRequest, onEvent, signal)
    onEvent({ event: 'error', data: { message: `No mock stream for ${path}`, retryable: false } })
    onEvent({ event: 'done', data: { latency_ms: 0, model: 'mock' } })
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') return
    throw err
  }
}
