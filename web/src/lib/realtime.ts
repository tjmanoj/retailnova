import { useEffect, useMemo, useRef, useState } from 'react'
import type { ActionProposal, DemandSignal, Notification } from '../types'
import { isMock } from './mockMode'
import { emit, on } from './bus'
import { getSessionId } from './session'
import { api } from './api'

export type FeedStatus = 'loading' | 'live' | 'error'

/** Firestore Timestamp | ISO string | Date → ISO string */
export function toIso(v: unknown): string {
  if (!v) return ''
  if (typeof v === 'string') return v
  if (v instanceof Date) return v.toISOString()
  const t = v as { toDate?: () => Date; seconds?: number; _seconds?: number }
  if (typeof t.toDate === 'function') return t.toDate().toISOString()
  const secs = t.seconds ?? t._seconds
  if (typeof secs === 'number') return new Date(secs * 1000).toISOString()
  return String(v)
}

function normalizeSignal(id: string, d: Record<string, unknown>): DemandSignal {
  return {
    ...(d as unknown as DemandSignal),
    signal_id: (d.signal_id as string) || id,
    ts: toIso(d.ts),
    attributes: (d.attributes as Record<string, string>) ?? {},
    quantity: (d.quantity as number) ?? 1,
    est_value_inr: (d.est_value_inr as number) ?? 0,
  }
}

function normalizeNotification(id: string, d: Record<string, unknown>): Notification {
  return {
    ...(d as unknown as Notification),
    notification_id: (d.notification_id as string) || id,
    created_at: toIso(d.created_at),
    read: Boolean(d.read),
  }
}

type Unsub = () => void

async function subscribeSignalsSource(cb: (items: DemandSignal[]) => void, onError: (e: unknown) => void): Promise<Unsub> {
  if (isMock()) {
    const m = await import('../mocks')
    return m.mockSubscribeSignals(cb)
  }
  const fb = await import('./firebase')
  const q = fb.query(fb.collection((await fb.getDb()), 'demand_signals'), fb.orderBy('ts', 'desc'), fb.limit(50))
  return fb.onSnapshot(
    q,
    (snap) => cb(snap.docs.map((doc) => normalizeSignal(doc.id, doc.data()))),
    (err) => onError(err),
  )
}

async function subscribeNotificationsSource(
  sessionId: string,
  cb: (items: Notification[]) => void,
  onError: (e: unknown) => void,
): Promise<Unsub> {
  if (isMock()) {
    const m = await import('../mocks')
    return m.mockSubscribeNotifications(sessionId, cb)
  }
  const fb = await import('./firebase')
  const q = fb.query(fb.collection((await fb.getDb()), 'notifications'), fb.where('session_id', '==', sessionId))
  return fb.onSnapshot(
    q,
    (snap) => cb(snap.docs.map((doc) => normalizeNotification(doc.id, doc.data()))),
    (err) => onError(err),
  )
}

const announced = new Set<string>()
const mountedAt = Date.now()

/**
 * Announce a signal from this browser session to the in-tab bus exactly once. Called for the chat
 * stream's `signal` event and for this session's live signals that arrive through Firestore (the
 * backend may store a signal after the chat stream has closed).
 */
export function announceSignal(s: DemandSignal) {
  if (announced.has(s.signal_id)) return
  announced.add(s.signal_id)
  emit('signal', s)
  emit('step', 'signal')
}

const byTsDesc = (a: DemandSignal, b: DemandSignal) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0)

/**
 * Live demand-signal feed for one store: Firestore `demand_signals` ordered by ts desc (limit 50),
 * filtered on the client, merged with signals pushed in this tab (so the Live Loop reacts instantly)
 * and with an optional seed (radar.recent_signals) used until the listener answers.
 */
export function useSignals(storeId: string, seed?: DemandSignal[]) {
  const [remote, setRemote] = useState<DemandSignal[] | null>(null)
  const [local, setLocal] = useState<DemandSignal[]>([])
  const [status, setStatus] = useState<FeedStatus>('loading')
  const initialIds = useRef<Set<string> | null>(null)
  const readyAt = useRef(0)
  const lastStore = useRef(storeId)

  useEffect(() => {
    let unsub: Unsub | null = null
    let cancelled = false
    subscribeSignalsSource(
      (items) => {
        if (cancelled) return
        setRemote(items)
        setStatus('live')
        const me = getSessionId()
        for (const it of items) {
          if (it.source === 'live' && it.session_id === me && new Date(it.ts).getTime() > mountedAt - 30_000) announceSignal(it)
        }
      },
      () => !cancelled && setStatus('error'),
    )
      .then((u) => (cancelled ? u() : (unsub = u)))
      .catch(() => !cancelled && setStatus('error'))
    const off = on('signal', (s) => setLocal((prev) => (prev.some((p) => p.signal_id === s.signal_id) ? prev : [s, ...prev].slice(0, 20))))
    const offReset = on('reset', () => setLocal([]))
    return () => {
      cancelled = true
      unsub?.()
      off()
      offReset()
    }
  }, [])

  const signals = useMemo(() => {
    const map = new Map<string, DemandSignal>()
    for (const s of seed ?? []) map.set(s.signal_id, s)
    for (const s of remote ?? []) map.set(s.signal_id, s)
    for (const s of local) if (!map.has(s.signal_id)) map.set(s.signal_id, s)
    return [...map.values()].filter((s) => s.store_id === storeId).sort(byTsDesc).slice(0, 50)
  }, [remote, local, seed, storeId])

  // Everything present at first paint is "old". Later arrivals are highlighted only if they are
  // actually recent, so older items that load late (from the radar seed) don't flash.
  if (lastStore.current !== storeId) {
    lastStore.current = storeId
    initialIds.current = null
  }
  if (initialIds.current === null && (remote !== null || (seed && seed.length))) {
    initialIds.current = new Set(signals.map((s) => s.signal_id))
    readyAt.current = Date.now()
  }
  const isNew = (s: DemandSignal) =>
    initialIds.current !== null && !initialIds.current.has(s.signal_id) && new Date(s.ts).getTime() > readyAt.current - 60_000

  return { signals, status, isNew, ready: remote !== null || Boolean(seed?.length) }
}

/** Notifications for this browser session: Firestore `notifications` where session_id == mine, sorted on the client. */
export function useNotifications(sessionId: string, onNew?: (n: Notification) => void) {
  const [items, setItems] = useState<Notification[]>([])
  const [status, setStatus] = useState<FeedStatus>('loading')
  const seen = useRef<Set<string> | null>(null)
  const onNewRef = useRef(onNew)
  onNewRef.current = onNew

  useEffect(() => {
    let unsub: Unsub | null = null
    let cancelled = false
    let poll: number | undefined
    const apply = (list: Notification[]) => {
      if (cancelled) return
      const sorted = [...list].sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
      if (seen.current === null) {
        seen.current = new Set(sorted.map((n) => n.notification_id))
      } else {
        for (const n of sorted) {
          if (!seen.current.has(n.notification_id)) {
            seen.current.add(n.notification_id)
            onNewRef.current?.(n)
          }
        }
      }
      setItems(sorted)
    }
    // If the live listener fails, fall back to polling the API so alerts still arrive.
    const fallback = () => {
      if (cancelled || poll) return
      setStatus('error')
      const tick = () =>
        api
          .notifications(sessionId)
          .then((r) => apply(r.items.map((n) => ({ ...n, created_at: toIso(n.created_at) }))))
          .catch(() => {})
      void tick()
      poll = window.setInterval(tick, 4000)
    }
    subscribeNotificationsSource(
      sessionId,
      (list) => {
        apply(list)
        if (!cancelled) setStatus('live')
      },
      fallback,
    )
      .then((u) => (cancelled ? u() : (unsub = u)))
      .catch(fallback)
    const offReset = on('reset', () => {
      seen.current = new Set()
      setItems([])
    })
    return () => {
      cancelled = true
      unsub?.()
      offReset()
      window.clearInterval(poll)
    }
  }, [sessionId])

  return { items, status }
}

const productCache = new Map<string, Promise<{ name: string; image_url: string; image_alt: string } | null>>()

/** Look up a product's display name (for proposal cards). Cached per SKU. */
export function getProductInfo(sku: string) {
  let p = productCache.get(sku)
  if (!p) {
    p = (async () => {
      try {
        if (isMock()) {
          const m = await import('../mocks')
          return m.mockProductInfo(sku)
        }
        const fb = await import('./firebase')
        const snap = await fb.getDoc(fb.doc((await fb.getDb()), 'products', sku))
        if (!snap.exists()) return null
        const d = snap.data() as { name?: string; image_url?: string; image_alt?: string }
        return { name: d.name ?? sku, image_url: d.image_url ?? `/products/${sku}.webp`, image_alt: d.image_alt ?? d.name ?? sku }
      } catch {
        return null
      }
    })()
    productCache.set(sku, p)
  }
  return p
}

export function useProductInfo(sku: string | null | undefined) {
  const [info, setInfo] = useState<{ name: string; image_url: string; image_alt: string } | null>(null)
  useEffect(() => {
    let alive = true
    if (!sku) return
    getProductInfo(sku).then((i) => alive && setInfo(i))
    return () => {
      alive = false
    }
  }, [sku])
  return info
}

/**
 * Live status of a plan's proposals: Firestore `actions` where plan_id == <plan>, sorted on the client.
 * Keeps cards in sync when someone approves or rejects from another screen.
 */
export function useActionUpdates(planId: string | null, onUpdate: (a: Partial<ActionProposal> & { action_id: string }) => void) {
  const cb = useRef(onUpdate)
  cb.current = onUpdate
  useEffect(() => {
    if (!planId || isMock()) return
    let unsub: Unsub | null = null
    let cancelled = false
    import('./firebase')
      .then(async (fb) => {
        const db = await fb.getDb()
        if (cancelled) return
        const q = fb.query(fb.collection(db, 'actions'), fb.where('plan_id', '==', planId))
        unsub = fb.onSnapshot(
          q,
          (snap) =>
            snap.docs.forEach((d) => {
              const v = d.data() as Partial<ActionProposal>
              cb.current({ action_id: v.action_id ?? d.id, status: v.status, decided_at: v.decided_at ? toIso(v.decided_at) : null })
            }),
          () => {},
        )
      })
      .catch(() => {})
    return () => {
      cancelled = true
      unsub?.()
    }
  }, [planId])
}
