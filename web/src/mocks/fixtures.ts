// Realistic fixtures for mock mode. Shapes follow docs/contracts.md §4 exactly.
import type {
  ActionProposal,
  Bootstrap,
  Category,
  DemandSignal,
  PlanStep,
  ProductBadge,
  ProductCard,
  Radar,
  RadarPoint,
  StoreStock,
} from '../types'
import { CATEGORIES, SAMPLE_MANAGER_PROMPTS, SAMPLE_SHOPPER_PROMPTS, STORES, storeName } from '../lib/constants'

export const bootstrap: Bootstrap = {
  demo_today: '2026-10-18',
  diwali_date: '2026-11-08',
  days_to_diwali: 21,
  stores: STORES,
  categories: CATEGORIES,
  sample_prompts: { shopper: SAMPLE_SHOPPER_PROMPTS, manager: SAMPLE_MANAGER_PROMPTS },
  reset_at: null,
}

interface ProductSeed {
  sku: string
  name: string
  category: Category
  color: string
  material: string
  price_inr: number
  mrp_inr: number
  image_alt: string
  sizes: string[]
  stock: Record<string, Record<string, number>> // store -> size -> on_hand
}

const S = (o: Record<string, number>, size = 'FREE') =>
  Object.fromEntries(Object.entries(o).map(([k, v]) => [k, { [size]: v }]))

export const productSeeds: ProductSeed[] = [
  {
    sku: 'SAR-001',
    name: 'Maroon Kanchipuram Silk Saree, gold zari border',
    category: 'sarees',
    color: 'maroon',
    material: 'silk',
    price_inr: 4799,
    mrp_inr: 5999,
    image_alt: 'Studio photo of the Maroon Kanchipuram Silk Saree, gold zari border, a folded saree on a plain off-white background',
    sizes: ['FREE'],
    stock: S({ 'CHN-TNG': 0, 'CHN-ANN': 3, 'BLR-JAY': 2, 'BLR-IND': 1, 'CBE-RSP': 14, 'HYD-BNJ': 4, ONLINE: 6 }),
  },
  {
    sku: 'SAR-005',
    name: 'Wine Maroon Soft Silk Saree with copper zari',
    category: 'sarees',
    color: 'maroon',
    material: 'soft silk',
    price_inr: 3299,
    mrp_inr: 3999,
    image_alt: 'Studio photo of the Wine Maroon Soft Silk Saree with copper zari, a folded saree on a plain off-white background',
    sizes: ['FREE'],
    stock: S({ 'CHN-TNG': 3, 'CHN-ANN': 5, 'BLR-JAY': 4, 'BLR-IND': 6, 'CBE-RSP': 7, 'HYD-BNJ': 2, ONLINE: 12 }),
  },
  {
    sku: 'SAR-003',
    name: 'Mustard Yellow Cotton-Silk Saree with temple border',
    category: 'sarees',
    color: 'mustard',
    material: 'cotton silk',
    price_inr: 2299,
    mrp_inr: 2799,
    image_alt: 'Studio photo of the Mustard Yellow Cotton-Silk Saree with temple border, a folded saree on a plain off-white background',
    sizes: ['FREE'],
    stock: S({ 'CHN-TNG': 9, 'CHN-ANN': 4, 'BLR-JAY': 6, 'BLR-IND': 3, 'CBE-RSP': 5, 'HYD-BNJ': 8, ONLINE: 15 }),
  },
  {
    sku: 'MEN-004',
    name: 'Royal Blue Silk-Blend Kurta',
    category: 'mens_ethnic',
    color: 'blue',
    material: 'silk blend',
    price_inr: 1899,
    mrp_inr: 2399,
    image_alt: "Studio photo of the Royal Blue Silk-Blend Kurta, a men's ethnic wear on a plain off-white background",
    sizes: ['S', 'M', 'L', 'XL', 'XXL'],
    stock: {
      'CHN-TNG': { S: 2, M: 4, L: 0, XL: 3, XXL: 1 },
      'CHN-ANN': { S: 1, M: 2, L: 3, XL: 1, XXL: 0 },
      'BLR-JAY': { S: 0, M: 3, L: 2, XL: 2, XXL: 1 },
      'BLR-IND': { S: 1, M: 1, L: 1, XL: 0, XXL: 0 },
      'CBE-RSP': { S: 2, M: 2, L: 4, XL: 2, XXL: 1 },
      'HYD-BNJ': { S: 1, M: 3, L: 2, XL: 1, XXL: 1 },
      ONLINE: { S: 4, M: 6, L: 5, XL: 3, XXL: 2 },
    },
  },
  {
    sku: 'MEN-007',
    name: 'Cream Silk Kurta and Veshti Set',
    category: 'mens_ethnic',
    color: 'cream',
    material: 'silk',
    price_inr: 3499,
    mrp_inr: 4299,
    image_alt: "Studio photo of the Cream Silk Kurta and Veshti Set, a men's ethnic wear on a plain off-white background",
    sizes: ['S', 'M', 'L', 'XL', 'XXL'],
    stock: {
      'CHN-TNG': { S: 1, M: 2, L: 3, XL: 2, XXL: 0 },
      'CHN-ANN': { S: 0, M: 1, L: 2, XL: 1, XXL: 1 },
      'BLR-JAY': { S: 1, M: 1, L: 1, XL: 1, XXL: 0 },
      'BLR-IND': { S: 2, M: 2, L: 2, XL: 1, XXL: 1 },
      'CBE-RSP': { S: 1, M: 2, L: 1, XL: 1, XXL: 0 },
      'HYD-BNJ': { S: 0, M: 1, L: 2, XL: 2, XXL: 1 },
      ONLINE: { S: 3, M: 4, L: 4, XL: 3, XXL: 2 },
    },
  },
  {
    sku: 'DEC-002',
    name: 'Brass Diya Set of 5, engraved',
    category: 'home_decor',
    color: 'gold',
    material: 'brass',
    price_inr: 1299,
    mrp_inr: 1599,
    image_alt: 'Studio photo of the Brass Diya Set of 5, engraved, a festive decor item on a plain off-white background',
    sizes: ['FREE'],
    stock: S({ 'CHN-TNG': 18, 'CHN-ANN': 11, 'BLR-JAY': 2, 'BLR-IND': 9, 'CBE-RSP': 7, 'HYD-BNJ': 10, ONLINE: 40 }),
  },
  {
    sku: 'FTW-003',
    name: "Women's Embroidered Juttis, maroon and gold",
    category: 'footwear',
    color: 'maroon',
    material: 'velvet',
    price_inr: 1299,
    mrp_inr: 1599,
    image_alt: "Studio photo of the Women's Embroidered Juttis, maroon and gold, a pair of footwear on a plain off-white background",
    sizes: ['6', '7', '8', '9', '10'],
    stock: {
      'CHN-TNG': { '6': 2, '7': 3, '8': 2, '9': 1, '10': 0 },
      'CHN-ANN': { '6': 1, '7': 2, '8': 1, '9': 1, '10': 1 },
      'BLR-JAY': { '6': 1, '7': 1, '8': 2, '9': 0, '10': 0 },
      'BLR-IND': { '6': 2, '7': 1, '8': 1, '9': 1, '10': 0 },
      'CBE-RSP': { '6': 1, '7': 2, '8': 2, '9': 1, '10': 1 },
      'HYD-BNJ': { '6': 2, '7': 0, '8': 1, '9': 1, '10': 1 },
      ONLINE: { '6': 3, '7': 4, '8': 3, '9': 2, '10': 2 },
    },
  },
]

export function seedBySku(sku: string) {
  return productSeeds.find((p) => p.sku === sku)
}

export function toCard(seed: ProductSeed, storeId: string, reason?: string): ProductCard {
  const availability: StoreStock[] = STORES.map((st) => {
    const bySize = seed.stock[st.store_id] ?? {}
    const sizes_in_stock = seed.sizes.filter((s) => (bySize[s] ?? 0) > 0)
    return {
      store_id: st.store_id,
      store_name: st.name,
      on_hand: Object.values(bySize).reduce((a, b) => a + b, 0),
      sizes_in_stock,
    }
  })
  const here = availability.find((a) => a.store_id === storeId)
  const onHand = here?.on_hand ?? 0
  const elsewhere = availability.some((a) => a.store_id !== storeId && a.on_hand > 0)
  const badge: ProductBadge = onHand === 0 ? (elsewhere ? 'other_store' : 'out_of_stock') : onHand <= 3 ? 'low' : 'in_stock'
  return {
    sku: seed.sku,
    name: seed.name,
    category: seed.category,
    color: seed.color,
    material: seed.material,
    price_inr: seed.price_inr,
    mrp_inr: seed.mrp_inr,
    image_url: `/products/${seed.sku}.webp`,
    image_alt: seed.image_alt,
    sizes: seed.sizes,
    availability,
    requested_store_id: storeId,
    requested_store_on_hand: onHand,
    badge,
    reason: reason ?? null,
  }
}

// ---------- Signals ----------

const SUMMARIES: { category: Category; sku: string | null; color?: string; summary: string; value: number; channel: DemandSignal['channel']; outcome: DemandSignal['outcome']; reason: DemandSignal['reason'] }[] = [
  { category: 'sarees', sku: 'SAR-001', color: 'maroon', summary: 'Asked for maroon Kanchipuram silk saree for Diwali; sold out here', value: 4799, channel: 'chat', outcome: 'unmet', reason: 'out_of_stock' },
  { category: 'sarees', sku: 'SAR-001', color: 'maroon', summary: 'Photo match: maroon silk saree with zari border; none in store', value: 4799, channel: 'image_search', outcome: 'unmet', reason: 'out_of_stock' },
  { category: 'sarees', sku: 'SAR-005', color: 'maroon', summary: 'Wanted maroon silk under ₹5,000; took wine soft silk instead', value: 3299, channel: 'chat', outcome: 'substituted', reason: 'out_of_stock' },
  { category: 'sarees', sku: 'SAR-001', color: 'maroon', summary: 'Walk-in asked for Kanchipuram silk in maroon; staff logged no stock', value: 4799, channel: 'store_assist', outcome: 'unmet', reason: 'out_of_stock' },
  { category: 'mens_ethnic', sku: 'MEN-004', color: 'blue', summary: 'Royal blue kurta in size L; size unavailable here', value: 1899, channel: 'chat', outcome: 'unmet', reason: 'size_unavailable' },
  { category: 'home_decor', sku: 'DEC-002', color: 'gold', summary: 'Brass diya set for puja; found in stock', value: 1299, channel: 'chat', outcome: 'fulfilled', reason: null },
  { category: 'sarees', sku: 'SAR-003', color: 'mustard', summary: 'Mustard cotton-silk saree with temple border; reserved for pickup', value: 2299, channel: 'chat', outcome: 'fulfilled', reason: null },
]

export function seedSignals(): DemandSignal[] {
  const out: DemandSignal[] = []
  const now = Date.now()
  let n = 0
  const stores = ['CHN-TNG', 'CHN-TNG', 'CHN-TNG', 'CBE-RSP', 'BLR-JAY', 'CHN-ANN', 'HYD-BNJ']
  for (let i = 0; i < 34; i++) {
    const tpl = SUMMARIES[i % SUMMARIES.length]
    const store = i < 22 ? 'CHN-TNG' : stores[i % stores.length]
    const ts = new Date(now - (i * 47 + 6) * 60_000 - (i % 3) * 13 * 60_000)
    out.push({
      signal_id: `sim-${++n}`,
      ts: ts.toISOString(),
      date: ts.toISOString().slice(0, 10),
      source: 'simulated',
      session_id: null,
      store_id: store,
      channel: tpl.channel,
      category: tpl.category,
      sku: tpl.sku,
      attributes: tpl.color ? { color: tpl.color } : {},
      price_band: { min_inr: 3000, max_inr: 5000 },
      outcome: tpl.outcome,
      reason: tpl.reason,
      quantity: 1,
      est_value_inr: tpl.value,
      intent_strength: 0.7 + (i % 3) * 0.1,
      summary: tpl.summary,
      language: i % 5 === 0 ? 'ta' : 'en',
    })
  }
  return out
}

// ---------- Radar ----------

function addDays(ymd: string, d: number): string {
  const t = new Date(`${ymd}T00:00:00Z`)
  t.setUTCDate(t.getUTCDate() + d)
  return t.toISOString().slice(0, 10)
}

function rand(seed: number) {
  const x = Math.sin(seed * 9301 + 49297) * 233280
  return x - Math.floor(x)
}

const CAT_SCALE: Record<Category, number> = { sarees: 1, kurta_sets: 0.8, mens_ethnic: 0.7, home_decor: 1.3, gifting: 1.1, footwear: 0.6 }
const STORE_SCALE: Record<string, number> = { 'CHN-TNG': 1, 'CHN-ANN': 0.75, 'BLR-JAY': 0.8, 'BLR-IND': 0.85, 'CBE-RSP': 0.6, 'HYD-BNJ': 0.7, ONLINE: 1.4 }

export function makeRadar(storeId: string, category: Category, liveUnmet = 0): Radar {
  const today = '2026-10-18'
  const diwaliOffset = 21
  const k = (CAT_SCALE[category] ?? 1) * (STORE_SCALE[storeId] ?? 1)
  const hero = storeId === 'CHN-TNG' && category === 'sarees'
  const series: RadarPoint[] = []

  // Festive lift curve peaking at Diwali.
  const lift = (dayFromToday: number) => {
    const dist = Math.abs(dayFromToday - diwaliOffset)
    return 1 + 1.25 * Math.exp(-(dist * dist) / 120)
  }

  for (let i = -56; i < 0; i++) {
    const date = addDays(today, i)
    const base = 9 * k * lift(i) * (1 + 0.18 * Math.sin(i / 3.5)) + rand(i + 3) * 3
    const censor = hero && i >= -9 ? 0.55 + (i + 9) * -0.02 : 1
    const unmet = i >= -30 ? Math.max(0, Math.round((hero ? 1.2 : 0.4) * k * (1 + (i + 30) / 6) * (0.6 + rand(i) * 0.8))) : 0
    series.push({
      date,
      actual_units: Math.max(0, Math.round(base * censor)),
      forecast_sales_only: null,
      forecast_demand_sensed: null,
      lower: null,
      upper: null,
      unmet_units: i >= -30 ? unmet : null,
    })
  }
  for (let i = 0; i < 42; i++) {
    const date = addDays(today, i)
    const salesOnly = 9.5 * k * (1 + 0.85 * (lift(i) - 1)) * (hero ? 0.88 : 1)
    const gap = hero ? 0.42 : 0.16
    const sensed = salesOnly * (1 + gap * (0.6 + 0.4 * (lift(i) - 1)))
    series.push({
      date,
      actual_units: null,
      forecast_sales_only: +salesOnly.toFixed(1),
      forecast_demand_sensed: +sensed.toFixed(1),
      lower: +(sensed * 0.82).toFixed(1),
      upper: +(sensed * 1.2).toFixed(1),
      unmet_units: i === 0 && liveUnmet ? liveUnmet : null,
    })
  }

  const gap21 = series
    .filter((p) => p.forecast_sales_only != null)
    .slice(0, 21)
    .reduce((a, p) => a + ((p.forecast_demand_sensed ?? 0) - (p.forecast_sales_only ?? 0)), 0)

  const unmet7 = series.slice(49, 56).reduce((a, p) => a + (p.unmet_units ?? 0), 0) + liveUnmet

  const allSignals = seedSignals().filter((s) => s.store_id === storeId)

  return {
    store_id: storeId,
    as_of: today,
    days_to_diwali: 21,
    kpis: {
      unmet_value_7d_inr: Math.round(unmet7 * (hero ? 4520 : 2100)),
      unmet_units_7d: unmet7,
      stockouts_now: hero ? 7 : Math.round(3 * k),
      signals_today: (hero ? 14 : Math.round(5 * k)) + liveUnmet,
      forecast_gap_units_21d: Math.round(gap21),
    },
    top_gaps: hero
      ? [
          { category: 'sarees', sku: 'SAR-001', label: 'Maroon Kanchipuram Silk Saree, gold zari border', attributes: { color: 'maroon', material: 'silk' }, unmet_units_7d: 27 + liveUnmet, unmet_value_7d_inr: (27 + liveUnmet) * 4799, on_hand: 0, trend: 'rising' },
          { category: 'sarees', sku: 'SAR-004', label: 'Bottle Green Kanchipuram Silk Saree, contrast pink border', attributes: { color: 'green', material: 'silk' }, unmet_units_7d: 6, unmet_value_7d_inr: 6 * 7999, on_hand: 1, trend: 'rising' },
          { category: 'sarees', sku: null, label: 'Silk sarees in maroon, ₹3,000–5,000', attributes: { color: 'maroon' }, unmet_units_7d: 5, unmet_value_7d_inr: 5 * 3900, on_hand: 3, trend: 'flat' },
          { category: 'sarees', sku: 'SAR-008', label: 'Deep Maroon Bridal Kanchipuram Silk Saree', attributes: { color: 'maroon', material: 'silk' }, unmet_units_7d: 2, unmet_value_7d_inr: 2 * 12999, on_hand: 0, trend: 'falling' },
        ]
      : [
          { category, sku: null, label: `${CATEGORIES.find((c) => c.category === category)?.label ?? category}: popular sizes`, attributes: { size: 'M' }, unmet_units_7d: Math.round(6 * k), unmet_value_7d_inr: Math.round(6 * k * 2100), on_hand: 2, trend: 'rising' },
          { category, sku: null, label: 'Festive colours, mid price', attributes: { color: 'gold' }, unmet_units_7d: Math.round(3 * k), unmet_value_7d_inr: Math.round(3 * k * 1800), on_hand: 5, trend: 'flat' },
        ],
    series,
    recent_signals: allSignals.slice(0, 20),
  }
}

// ---------- Plan ----------

export function planSteps(storeId: string): { step: PlanStep; delayStart: number; delayDone: number }[] {
  const store = storeName(storeId)
  return [
    { step: { id: 'forecast', label: 'Compare both forecasts', status: 'done', summary: 'Demand-sensed forecast is 38% above sales-only for the next 21 days (+214 units).' }, delayStart: 0, delayDone: 1300 },
    { step: { id: 'unmet_demand', label: 'Count unmet demand', status: 'done', summary: `31 unmet asks for maroon silk sarees at ${store} in 7 days, worth ₹1,48,769.` }, delayStart: 80, delayDone: 1700 },
    { step: { id: 'inventory', label: 'Check inventory position', status: 'done', summary: `SAR-001 is out at ${store}. RS Puram holds 14, Anna Nagar 3.` }, delayStart: 160, delayDone: 1100 },
    { step: { id: 'transfers', label: 'Find transfer options', status: 'done', summary: 'RS Puram can spare 12 units and keep 2. Road transfer takes 2 days.' }, delayStart: 240, delayDone: 2100 },
    { step: { id: 'trends', label: 'Check festive trends', status: 'done', summary: 'Searches for maroon Kanchipuram silk are up ahead of Diwali in Tamil Nadu.' }, delayStart: 320, delayDone: 2500 },
    { step: { id: 'planner', label: 'Draft the action plan', status: 'done', summary: '2 actions proposed, protecting ₹2,63,945 before Diwali.' }, delayStart: 2600, delayDone: 4100 },
  ]
}

export const planSummary =
  'Customers at T. Nagar keep asking for the maroon Kanchipuram silk saree, but it has been out of stock for 9 days, so sales-only data hides the demand. Move spare units from RS Puram now and reorder from the supplier so stock lands well before Diwali.'

export function planProposals(planId: string, storeId: string): ActionProposal[] {
  const now = new Date().toISOString()
  return [
    {
      action_id: `${planId}-a1`,
      plan_id: planId,
      type: 'transfer',
      store_id: storeId,
      category: 'sarees',
      sku: 'SAR-001',
      size: 'FREE',
      quantity: 12,
      from_store_id: 'CBE-RSP',
      supplier_lead_days: null,
      eta_date: '2026-10-20',
      rationale:
        'T. Nagar has 0 on hand and 27 unmet asks in 7 days. RS Puram has 14 with slow sell-through, so moving 12 covers the next 10 days of demand-sensed sales.',
      evidence: [
        { kind: 'signals', text: '27 shoppers asked for this saree at T. Nagar in the last 7 days', value: 27 },
        { kind: 'forecast', text: 'Demand-sensed forecast: 19 units/day at the Diwali peak vs 13 from sales only', value: 19 },
        { kind: 'inventory', text: 'RS Puram: 14 on hand, sold 3 in the last 14 days', value: 14 },
        { kind: 'trend', text: 'Maroon and gold Kanchipuram searches rising in Chennai', value: null },
      ],
      confidence: 0.86,
      expected_revenue_protected_inr: 57588,
      status: 'proposed',
      created_at: now,
      decided_at: null,
    },
    {
      action_id: `${planId}-a2`,
      plan_id: planId,
      type: 'reorder',
      store_id: storeId,
      category: 'sarees',
      sku: 'SAR-001',
      size: 'FREE',
      quantity: 40,
      from_store_id: null,
      supplier_lead_days: 9,
      eta_date: '2026-10-27',
      rationale:
        'The transfer only covers the first 10 days. A 40-unit reorder lands 12 days before Diwali and covers the peak week the sales-only forecast misses.',
      evidence: [
        { kind: 'forecast', text: '+214 units gap between the two forecasts over 21 days', value: 214 },
        { kind: 'signals', text: 'Unmet asks rising for 7 days in a row', value: 7 },
        { kind: 'inventory', text: 'Chain-wide stock of SAR-001 is 30 units', value: 30 },
      ],
      confidence: 0.74,
      expected_revenue_protected_inr: 191960,
      status: 'proposed',
      created_at: now,
      decided_at: null,
    },
  ]
}
