import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ArrowUp, Bell, BellRing, Camera, ImagePlus, MapPin, PackageCheck, RefreshCw, Store as StoreIcon, Truck, X } from 'lucide-react'
import type { ChatRequest, DemandSignal, Notification, ProductCard as Product } from '../../types'
import { api } from '../../lib/api'
import { getSessionId } from '../../lib/session'
import { useBootstrap } from '../../lib/bootstrap'
import { DEFAULT_STORE, storeName } from '../../lib/constants'
import { emit, on } from '../../lib/bus'
import { announceSignal, useNotifications } from '../../lib/realtime'
import { relativeTime } from '../../lib/format'
import { ActivityChips, type ActivityState } from '../../components/ActivityChips'
import { RichText } from '../../components/RichText'
import { ToastCard } from '../../components/Toast'
import { Badge, cx } from '../../components/ui'
import { ProductCard } from './ProductCard'

interface Turn {
  id: string
  role: 'user' | 'assistant'
  text: string
  image?: string // data URL for display
  activities: ActivityState[]
  products: Product[]
  signal?: DemandSignal
  error?: { message: string; retryable: boolean }
  streaming?: boolean
  request?: ChatRequest
}

type Attachment = { dataUrl: string; base64: string; mime: 'image/jpeg' | 'image/png' | 'image/webp'; name: string }

const MAX_LEN = 1000
const MAX_IMAGE_BYTES = 1.5 * 1024 * 1024
let turnSeq = 0
const tid = () => `t${Date.now().toString(36)}${(turnSeq++).toString(36)}`

function readAsDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result))
    r.onerror = () => reject(r.error)
    r.readAsDataURL(blob)
  })
}

/** Downscale large photos so they stay under the 1.5 MB API limit. */
async function toAttachment(blob: Blob, name: string): Promise<Attachment> {
  let mime = (['image/jpeg', 'image/png', 'image/webp'].includes(blob.type) ? blob.type : 'image/jpeg') as Attachment['mime']
  let dataUrl = await readAsDataUrl(blob)
  if (blob.size > MAX_IMAGE_BYTES * 0.9 || !['image/jpeg', 'image/png', 'image/webp'].includes(blob.type)) {
    const img = new Image()
    img.src = dataUrl
    await img.decode()
    const scale = Math.min(1, 1280 / Math.max(img.width, img.height))
    const c = document.createElement('canvas')
    c.width = Math.round(img.width * scale)
    c.height = Math.round(img.height * scale)
    c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height)
    dataUrl = c.toDataURL('image/jpeg', 0.85)
    mime = 'image/jpeg'
  }
  return { dataUrl, base64: dataUrl.slice(dataUrl.indexOf(',') + 1), mime, name }
}

export function ShopView({ initialPrompt, embedded = false, onConsumedPrompt }: { initialPrompt?: string | null; embedded?: boolean; onConsumedPrompt?: () => void }) {
  const boot = useBootstrap()
  const sessionId = getSessionId()
  const [storeId, setStoreId] = useState<string>(() => {
    try {
      return localStorage.getItem('rn_store') || DEFAULT_STORE
    } catch {
      return DEFAULT_STORE
    }
  })
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [attachment, setAttachment] = useState<Attachment | null>(null)
  const [busy, setBusy] = useState(false)
  const [sampleBusy, setSampleBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [inboxOpen, setInboxOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [banner, setBanner] = useState<Notification | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const consumed = useRef(false)

  const physicalStores = boot.stores.filter((s) => s.type === 'store')
  const onlineStore = boot.stores.find((s) => s.type === 'online')

  const onNew = useCallback((n: Notification) => {
    setBanner(n)
    setUnread((u) => u + 1)
    emit('notification', n)
    emit('step', 'notify')
    window.setTimeout(() => setBanner((b) => (b?.notification_id === n.notification_id ? null : b)), 9000)
  }, [])
  const { items: notifications } = useNotifications(sessionId, onNew)

  useEffect(() => {
    try {
      localStorage.setItem('rn_store', storeId)
    } catch {
      /* ignore */
    }
  }, [storeId])

  useEffect(
    () =>
      on('reset', () => {
        abortRef.current?.abort()
        setTurns([])
        setBusy(false)
        setUnread(0)
        setBanner(null)
      }),
    [],
  )

  // A signal for this session can land after the chat stream closed (via the live feed).
  // Attach it to the latest assistant turn that doesn't have one yet.
  useEffect(
    () =>
      on('signal', (sig) => {
        if (sig.session_id !== sessionId) return
        setTurns((ts) => {
          if (ts.some((t) => t.signal?.signal_id === sig.signal_id)) return ts
          const idx = [...ts].reverse().findIndex((t) => t.role === 'assistant')
          if (idx === -1) return ts
          const i = ts.length - 1 - idx
          if (ts[i].signal) return ts
          return ts.map((t, j) => (j === i ? { ...t, signal: sig } : t))
        })
      }),
    [sessionId],
  )

  // Keep the newest content in view while streaming.
  useEffect(() => {
    const el = scroller.current
    if (!el || turns.length === 0) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [turns])

  const patch = (id: string, fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)))

  const run = useCallback(async (req: ChatRequest, assistantId: string) => {
    setBusy(true)
    emit('step', 'ask')
    const ctrl = new AbortController()
    abortRef.current = ctrl
    await api.chat(
      req,
      (e) => {
        switch (e.event) {
          case 'activity':
            patch(assistantId, (t) => {
              const exists = t.activities.find((a) => a.id === e.data.id)
              const activities = exists
                ? t.activities.map((a) => (a.id === e.data.id ? { ...a, ...e.data } : a))
                : [...t.activities, { ...e.data }]
              return { ...t, activities }
            })
            break
          case 'text':
            patch(assistantId, (t) => ({ ...t, text: t.text + e.data.delta }))
            break
          case 'products':
            // A turn can send more than one products event: append, de-duplicated by SKU (newest data wins).
            patch(assistantId, (t) => {
              const merged = [...t.products]
              for (const item of e.data.items) {
                const i = merged.findIndex((x) => x.sku === item.sku)
                if (i === -1) merged.push(item)
                else merged[i] = item
              }
              return { ...t, products: merged }
            })
            break
          case 'signal':
            patch(assistantId, (t) => ({ ...t, signal: e.data.signal }))
            announceSignal(e.data.signal)
            break
          case 'error':
            patch(assistantId, (t) => ({ ...t, error: e.data }))
            break
          case 'done':
            patch(assistantId, (t) => ({
              ...t,
              streaming: false,
              activities: t.activities.map((a) => ({ ...a, status: 'end' as const })),
            }))
            break
        }
      },
      ctrl.signal,
    )
    patch(assistantId, (t) => ({ ...t, streaming: false }))
    setBusy(false)
  }, [])

  const send = useCallback(
    (text: string, att: Attachment | null = null) => {
      const message = text.trim() || (att ? 'Find this in your catalog' : '')
      if (!message || busy) return
      const req: ChatRequest = {
        session_id: sessionId,
        message: message.slice(0, MAX_LEN),
        store_id: storeId,
        language_hint: 'auto',
        ...(att ? { image_base64: att.base64, image_mime: att.mime } : {}),
      }
      const userTurn: Turn = { id: tid(), role: 'user', text: message, image: att?.dataUrl, activities: [], products: [] }
      const asst: Turn = { id: tid(), role: 'assistant', text: '', activities: [], products: [], streaming: true, request: req }
      setTurns((ts) => [...ts, userTurn, asst])
      setInput('')
      setAttachment(null)
      void run(req, asst.id)
    },
    [busy, run, sessionId, storeId],
  )

  const retry = (t: Turn) => {
    if (!t.request || busy) return
    patch(t.id, (x) => ({ ...x, text: '', activities: [], products: [], error: undefined, streaming: true, signal: undefined }))
    void run(t.request, t.id)
  }

  // Deep link: /shop?q=...
  useEffect(() => {
    if (initialPrompt && !consumed.current) {
      consumed.current = true
      send(initialPrompt)
      onConsumedPrompt?.()
    }
  }, [initialPrompt, send, onConsumedPrompt])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    send(input, attachment)
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send(input, attachment)
    }
  }

  const onFile = async (f: File | undefined) => {
    if (!f) return
    if (!f.type.startsWith('image/')) {
      setNotice('Choose a photo (JPEG, PNG or WebP).')
      return
    }
    try {
      const att = await toAttachment(f, f.name)
      if (att.base64.length * 0.75 > MAX_IMAGE_BYTES) {
        setNotice('That photo is too large. Try one under 1.5 MB.')
        return
      }
      setAttachment(att)
      setNotice(null)
      textarea.current?.focus()
    } catch {
      setNotice('That photo could not be read. Try another one.')
    }
  }

  const trySample = async () => {
    setSampleBusy(true)
    try {
      const res = await fetch('/samples/blue-kurta.webp')
      if (!res.ok || !res.headers.get('content-type')?.includes('image')) throw new Error('missing')
      const att = await toAttachment(await res.blob(), 'blue-kurta.webp')
      send('Do you have this kurta? I need size L.', att)
    } catch {
      setNotice('The sample photo is not available yet. Upload your own with the camera button.')
    } finally {
      setSampleBusy(false)
    }
  }

  // Autosize the composer.
  useEffect(() => {
    const el = textarea.current
    if (!el) return
    el.style.height = 'auto'
    if (input) el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [input])

  const empty = turns.length === 0

  return (
    <div className="@container relative flex h-full min-h-0 flex-col bg-bg">
      {/* Header strip */}
      <div className={cx('border-b border-line bg-surface px-3 py-2', embedded ? 'pt-8' : '')}>
        <div className="mx-auto flex w-full max-w-[760px] items-center gap-2">
        <label className="relative flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-line px-2.5 py-1.5 focus-within:ring-2 focus-within:ring-[var(--focus)] hover:border-line-strong">
          <MapPin className="size-4 shrink-0 text-maroon-ink" aria-hidden />
          <span className="sr-only">Store for pickup and stock</span>
          <select
            value={storeId}
            onChange={(e) => setStoreId(e.target.value)}
            className="w-full min-w-0 appearance-none bg-transparent pr-1 text-sm font-semibold text-ink focus:outline-none"
          >
            {physicalStores.map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.name}, {s.city}
              </option>
            ))}
            {onlineStore && <option value={onlineStore.store_id}>{onlineStore.name}</option>}
          </select>
        </label>
        <div className="relative">
          <button
            onClick={() => {
              setInboxOpen((o) => !o)
              setUnread(0)
            }}
            className={cx('relative grid size-10 place-items-center rounded-xl border border-line text-ink-2 hover:bg-surface-2 hover:text-ink', unread > 0 && 'anim-ring border-marigold')}
            aria-label={`Alerts${unread ? `, ${unread} new` : ''}`}
            aria-expanded={inboxOpen}
          >
            {unread > 0 ? <BellRing className="size-[18px] text-marigold-ink" aria-hidden /> : <Bell className="size-[18px]" aria-hidden />}
            {unread > 0 && (
              <span className="absolute -top-1 -right-1 grid min-w-5 place-items-center rounded-full bg-maroon px-1 text-[11px] font-bold text-on-maroon">
                {unread}
              </span>
            )}
          </button>
          {inboxOpen && <Inbox items={notifications} onClose={() => setInboxOpen(false)} />}
        </div>
        </div>
      </div>

      {/* Notification banner */}
      {banner && (
        <div className={cx('pointer-events-none absolute inset-x-0 z-30 flex justify-center px-3', embedded ? 'top-[88px]' : 'top-16')}>
          <ToastCard
            t={{ tone: 'notify', title: banner.kind === 'reserved' ? 'Reserved for you' : banner.kind === 'back_in_stock' ? 'Back in stock' : 'On its way', body: banner.message }}
            onClose={() => setBanner(null)}
          />
        </div>
      )}

      {/* Conversation */}
      <div ref={scroller} className="scrollbar-thin relative min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto flex max-w-[760px] flex-col gap-5 px-3 py-5 @[480px]:px-5">
          {empty ? (
            <Welcome
              storeLabel={storeName(storeId)}
              prompts={boot.sample_prompts.shopper}
              onPrompt={(p) => send(p)}
              onSample={trySample}
              sampleBusy={sampleBusy}
            />
          ) : (
            <div role="log" aria-live="polite" aria-relevant="additions text" aria-label="Conversation" className="flex flex-col gap-5">
              {turns.map((t) =>
                t.role === 'user' ? (
                  <UserBubble key={t.id} t={t} />
                ) : (
                  <AssistantTurn key={t.id} t={t} onRetry={() => retry(t)} busy={busy} alerts={notifications} />
                ),
              )}
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <form onSubmit={onSubmit} className="border-t border-line bg-surface px-3 pt-2 pb-[max(env(safe-area-inset-bottom),0.5rem)]">
        <div className="mx-auto max-w-[760px]">
          {notice && (
            <p className="mb-2 flex items-start justify-between gap-2 rounded-lg bg-marigold-soft px-2.5 py-1.5 text-xs text-marigold-ink" role="status">
              {notice}
              <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss" className="rounded p-0.5">
                <X className="size-3.5" aria-hidden />
              </button>
            </p>
          )}
          {attachment && (
            <div className="mb-2 flex items-center gap-2 rounded-xl border border-line bg-surface-2 p-1.5 pr-2">
              <img src={attachment.dataUrl} alt="Photo to search with" className="size-10 rounded-lg object-cover" />
              <span className="min-w-0 flex-1 truncate text-xs text-ink-2">{attachment.name}</span>
              <button type="button" onClick={() => setAttachment(null)} className="rounded-lg p-1 text-ink-3 hover:bg-surface hover:text-ink" aria-label="Remove photo">
                <X className="size-4" aria-hidden />
              </button>
            </div>
          )}
          <div className="flex items-end gap-2">
            <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="sr-only" tabIndex={-1} aria-label="Upload a photo to search with" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = '' }} />
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="grid size-11 shrink-0 place-items-center rounded-full border border-line-strong text-ink-2 hover:bg-surface-2 hover:text-ink"
              aria-label="Search with a photo"
            >
              <Camera className="size-5" aria-hidden />
            </button>
            <label className="sr-only" htmlFor="chat-input">
              Message the Nova Bazaar concierge
            </label>
            <textarea
              id="chat-input"
              ref={textarea}
              rows={1}
              maxLength={MAX_LEN}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder={attachment ? 'Add a size or budget' : 'Ask for an outfit or a gift…'}
              className="h-11 max-h-[140px] min-h-11 min-w-0 flex-1 resize-none rounded-[22px] border border-line-strong bg-bg px-4 py-2.5 text-[16px] leading-6 text-ink placeholder:text-ink-3 focus:border-ink-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-marigold/50"
            />
            <button
              type="submit"
              disabled={busy || (!input.trim() && !attachment)}
              className="grid size-11 shrink-0 place-items-center rounded-full bg-maroon text-on-maroon transition-opacity hover:bg-maroon-hover disabled:opacity-40"
              aria-label="Send"
            >
              <ArrowUp className="size-5" aria-hidden />
            </button>
          </div>
          <p className="mt-1.5 text-center text-[11px] text-ink-3">
            {input.length > MAX_LEN - 120 ? `${MAX_LEN - input.length} characters left. ` : ''}Demo data is synthetic. Nova Bazaar is a fictional retailer.
          </p>
        </div>
      </form>
    </div>
  )
}

function Welcome({
  storeLabel,
  prompts,
  onPrompt,
  onSample,
  sampleBusy,
}: {
  storeLabel: string
  prompts: string[]
  onPrompt: (p: string) => void
  onSample: () => void
  sampleBusy: boolean
}) {
  return (
    <div className="anim-rise flex flex-col gap-5 pt-2 @[480px]:pt-8">
      <div>
        <p className="text-sm font-semibold text-maroon-ink">Nova Bazaar concierge</p>
        <h2 className="display mt-1 text-[34px] text-ink @[480px]:text-[44px]">Find it for Diwali, pick it up at {storeLabel.replace(/\. /g, '.\u00a0')}.</h2>
        <p className="mt-3 max-w-[52ch] text-[15px] text-ink-2">
          I only suggest items we actually carry and show live stock at every store. Ask in English, Hinglish or Tamil, or send a photo.
        </p>
      </div>
      <div>
        <p className="mb-2 text-xs font-medium text-ink-3">Try asking</p>
        <div className="flex flex-wrap gap-2">
          {prompts.slice(0, 5).map((p) => (
            <button
              key={p}
              onClick={() => onPrompt(p)}
              className="rounded-full border border-line-strong bg-surface px-3.5 py-2 text-left text-sm font-medium text-ink hover:border-maroon-ink hover:text-maroon-ink"
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      <button
        onClick={onSample}
        disabled={sampleBusy}
        className="group flex items-center gap-3 self-start rounded-2xl border border-dashed border-line-strong bg-surface p-2 pr-4 text-left hover:border-maroon-ink disabled:opacity-60"
      >
        <span className="relative grid size-12 place-items-center overflow-hidden rounded-xl bg-surface-2">
          <img src="/samples/blue-kurta.webp" alt="" className="size-full object-cover" onError={(e) => (e.currentTarget.style.display = 'none')} />
          <ImagePlus className="absolute size-5 text-ink-3" aria-hidden />
        </span>
        <span>
          <span className="block text-sm font-semibold text-ink">{sampleBusy ? 'Sending the photo…' : 'Try a sample photo'}</span>
          <span className="block text-xs text-ink-3">Search the catalog with a picture of a blue kurta</span>
        </span>
      </button>
    </div>
  )
}

function UserBubble({ t }: { t: Turn }) {
  return (
    <div className="anim-fade flex flex-col items-end gap-1.5">
      {t.image && <img src={t.image} alt="Photo you sent" className="h-36 w-auto max-w-[70%] rounded-2xl rounded-br-md object-cover" />}
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-maroon px-3.5 py-2 text-[15px] text-on-maroon">{t.text}</p>
    </div>
  )
}

function AssistantTurn({ t, onRetry, busy, alerts }: { t: Turn; onRetry: () => void; busy: boolean; alerts: Notification[] }) {
  const photo = Boolean(t.request?.image_base64)
  const thinking = t.streaming && !t.text && !t.activities.length && !photo
  // Photo turns take a while; show what is happening until the first real activity arrives.
  const activities: ActivityState[] =
    photo && t.streaming && !t.text && !t.activities.length
      ? [{ id: 'photo-pending', tool: 'photo', label: 'Looking at your photo', status: 'start' }]
      : t.activities
  return (
    <div className="flex flex-col gap-2.5">
      <ActivityChips items={activities} />
      {photo && t.streaming && !t.text && (
        <p className="text-xs text-ink-3">Photo searches take about 10 seconds.</p>
      )}
      {thinking && (
        <div className="flex items-center gap-1 py-1" aria-label="Concierge is thinking">
          {[0, 1, 2].map((i) => (
            <span key={i} className="typing-dot size-1.5 rounded-full bg-ink-3" style={{ animationDelay: `${i * 160}ms` }} />
          ))}
        </div>
      )}
      {t.text && (
        <div className="max-w-[62ch] text-[15px] leading-relaxed text-ink">
          <RichText text={t.text} />
          {t.streaming && <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse bg-maroon" aria-hidden />}
        </div>
      )}
      {t.products.length > 0 && (
        <div className="anim-rise -mx-3 @[480px]:mx-0">
          <div className="no-scrollbar flex snap-x snap-mandatory gap-3 overflow-x-auto px-3 pb-1 @[480px]:px-0 @[640px]:grid @[640px]:grid-cols-3 @[640px]:overflow-visible">
            {t.products.map((p) => (
              <ProductCard
                key={p.sku}
                p={p}
                alert={pickAlert(alerts, p.sku, p.requested_store_id)}
              />
            ))}
          </div>
        </div>
      )}
      {t.signal && <SignalNote s={t.signal} />}
      {t.error && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2.5 text-sm text-danger" role="alert">
          <span className="flex-1">{t.error.message}</span>
          {t.error.retryable && t.request && (
            <button onClick={onRetry} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-surface px-2.5 py-1 text-xs font-semibold text-ink hover:bg-surface-2 disabled:opacity-50">
              <RefreshCw className="size-3.5" aria-hidden />
              Try again
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** The most useful alert for a product card: a reservation beats an arrival estimate; this store beats others. */
function pickAlert(alerts: Notification[], sku: string, storeId: string): Notification | undefined {
  const mine = alerts.filter((n) => n.sku === sku)
  const rank = (n: Notification) => (n.kind === 'transfer_eta' ? 2 : 0) + (n.store_id === storeId ? 0 : 1)
  return [...mine].sort((a, b) => rank(a) - rank(b))[0]
}

function SignalNote({ s }: { s: DemandSignal }) {
  const tone = s.outcome === 'unmet' ? 'maroon' : s.outcome === 'substituted' ? 'marigold' : 'leaf'
  return (
    <p className="anim-fade flex flex-wrap items-center gap-2 text-xs text-ink-3">
      <Badge tone={tone}>Demand signal sent</Badge>
      <span>Your ask was shared anonymously with the {storeName(s.store_id)} team so they can stock what shoppers want.</span>
    </p>
  )
}

function Inbox({ items, onClose }: { items: Notification[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => e.key === 'Escape' && onClose()
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node) && !(e.target as HTMLElement).closest('[aria-label^="Alerts"]')) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDoc)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDoc)
    }
  }, [onClose])
  const sorted = useMemo(() => items, [items])
  return (
    <div ref={ref} className="anim-fade absolute top-12 right-0 z-40 w-[min(88vw,340px)] rounded-2xl border border-line bg-surface p-2 shadow-float" role="dialog" aria-label="Your alerts">
      <p className="px-2 pt-1 pb-2 text-sm font-semibold text-ink">Your alerts</p>
      {sorted.length === 0 ? (
        <p className="px-2 pb-2 text-sm text-ink-3">No alerts yet. Tap Notify me on a sold-out item and you'll hear here when it's back.</p>
      ) : (
        <ul className="scrollbar-thin relative max-h-80 space-y-1 overflow-y-auto">
          {sorted.map((n) => (
            <li key={n.notification_id} className="flex gap-2.5 rounded-xl px-2 py-2 hover:bg-surface-2">
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-marigold-soft text-marigold-ink">
                {n.kind === 'reserved' ? <PackageCheck className="size-4" aria-hidden /> : n.kind === 'transfer_eta' ? <Truck className="size-4" aria-hidden /> : <StoreIcon className="size-4" aria-hidden />}
              </span>
              <span className="min-w-0">
                <span className="block text-sm text-ink">{n.message}</span>
                <span className="block text-xs text-ink-3">
                  {storeName(n.store_id)}, {relativeTime(n.created_at)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
