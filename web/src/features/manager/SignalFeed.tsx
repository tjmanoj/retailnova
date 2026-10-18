import { useEffect, useState } from 'react'
import { Camera, MessageCircle, Mic, Store as StoreIcon, Radio } from 'lucide-react'
import type { DemandSignal } from '../../types'
import { useSignals } from '../../lib/realtime'
import { formatINR, relativeTime } from '../../lib/format'
import { storeName } from '../../lib/constants'
import { Badge, Skeleton, cx } from '../../components/ui'

const CHANNEL = {
  chat: { Icon: MessageCircle, label: 'Chat' },
  image_search: { Icon: Camera, label: 'Photo search' },
  store_assist: { Icon: StoreIcon, label: 'Store assist' },
  voice: { Icon: Mic, label: 'Voice note' },
} as const

const REASON: Record<string, string> = {
  out_of_stock: 'out of stock',
  size_unavailable: 'size unavailable',
  not_carried: 'not carried',
  price_too_high: 'over budget',
  other: 'other',
}

function OutcomeBadge({ s }: { s: DemandSignal }) {
  if (s.outcome === 'unmet') return <Badge tone="maroon">Unmet{s.reason ? `: ${REASON[s.reason] ?? s.reason}` : ''}</Badge>
  if (s.outcome === 'substituted') return <Badge tone="marigold">Substituted</Badge>
  return <Badge tone="leaf">Fulfilled</Badge>
}

function useNow(ms = 30_000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(t)
  }, [ms])
  return now
}

export function SignalFeed({ storeId, seed, maxHeight = 520, className }: { storeId: string; seed?: DemandSignal[]; maxHeight?: number | string; className?: string }) {
  const { signals, status, isNew, ready } = useSignals(storeId, seed)
  const now = useNow()

  return (
    <section className={cx('flex min-h-0 flex-col rounded-2xl border border-line bg-surface', className)} aria-labelledby="feed-title" data-feed>
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h2 id="feed-title" className="display-tight text-lg text-ink">
            Live demand signals
          </h2>
          <p className="text-xs text-ink-3">What shoppers asked for at {storeName(storeId)}, newest first</p>
        </div>
        <span
          className={cx(
            'inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-semibold',
            status === 'live' ? 'bg-leaf-soft text-leaf' : status === 'error' ? 'bg-surface-2 text-ink-3' : 'bg-surface-2 text-ink-3',
          )}
        >
          <Radio className={cx('size-3.5', status === 'live' && 'animate-pulse')} aria-hidden />
          {status === 'live' ? 'Live' : status === 'error' ? 'Reconnecting' : 'Connecting'}
        </span>
      </header>
      <div className="scrollbar-thin relative min-h-0 flex-1 overflow-y-auto" style={{ maxHeight }} tabIndex={0} role="region" aria-label="Signal list">
        {!ready ? (
          <ul className="space-y-3 p-4" aria-hidden>
            {Array.from({ length: 5 }).map((_, i) => (
              <li key={i} className="flex gap-3">
                <Skeleton className="size-8 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3.5 w-11/12" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              </li>
            ))}
          </ul>
        ) : signals.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm font-semibold text-ink">No signals for {storeName(storeId)} yet</p>
            <p className="mt-1 text-sm text-ink-3">Ask the shopper concierge for something. Each conversation shows up here within seconds.</p>
          </div>
        ) : (
          <ul aria-live="polite" aria-relevant="additions" className="divide-y divide-line">
            {signals.map((s) => {
              const ch = CHANNEL[s.channel] ?? CHANNEL.chat
              const fresh = isNew(s)
              return (
                <li key={s.signal_id} className={cx('relative flex gap-3 px-4 py-3', fresh && 'anim-flash')}>
                  <span
                    className={cx(
                      'mt-0.5 grid size-8 shrink-0 place-items-center rounded-full',
                      s.outcome === 'unmet' ? 'bg-maroon-soft text-maroon-ink' : 'bg-surface-2 text-ink-2',
                    )}
                    title={ch.label}
                  >
                    <ch.Icon className="size-4" aria-hidden />
                    <span className="sr-only">{ch.label}</span>
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm leading-snug text-ink">{s.summary}</p>
                      <span className="figure shrink-0 text-sm text-ink">{formatINR(s.est_value_inr)}</span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
                      <OutcomeBadge s={s} />
                      {s.channel === 'store_assist' ? (
                        <Badge tone="neutral" icon={<StoreIcon className="size-3" aria-hidden />}>
                          Store assist
                        </Badge>
                      ) : s.channel === 'voice' ? (
                        <Badge tone="peacock" icon={<Mic className="size-3" aria-hidden />}>
                          Voice note
                        </Badge>
                      ) : s.channel === 'image_search' && s.source === 'live' ? (
                        <Badge tone="peacock" icon={<Camera className="size-3" aria-hidden />}>
                          Photo search
                        </Badge>
                      ) : (
                        s.source === 'live' && <Badge tone="peacock">Live chat</Badge>
                      )}
                      {s.sku && <span className="num">{s.sku}</span>}
                      <time dateTime={s.ts}>{relativeTime(s.ts, now)}</time>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
