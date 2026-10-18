import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BarChart3, Check, Smartphone } from 'lucide-react'
import { ShopView } from '../features/shop/ShopView'
import { ManagerView } from '../features/manager/ManagerView'
import { on, type LoopStep } from '../lib/bus'
import { cx } from '../components/ui'

const STEPS: { key: LoopStep; title: string; short: string; who: string }[] = [
  { key: 'ask', title: 'Ask', short: 'Ask', who: 'Priya asks the concierge' },
  { key: 'signal', title: 'Signal', short: 'Signal', who: 'Her ask becomes a demand signal' },
  { key: 'plan', title: 'Plan', short: 'Plan', who: 'Arjun generates the action plan' },
  { key: 'approve', title: 'Approve & notify', short: 'Approve', who: 'Approve, and Priya hears back' },
]

function useMedia(q: string) {
  const [m, setM] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const mq = window.matchMedia(q)
    const h = () => setM(mq.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [q])
  return m
}

function useLoopProgress() {
  const [reached, setReached] = useState<Set<LoopStep>>(new Set())
  const [last, setLast] = useState<LoopStep | null>(null)
  useEffect(() => {
    const off = on('step', (s) => {
      setReached((r) => new Set(r).add(s))
      setLast(s)
    })
    const offReset = on('reset', () => {
      setReached(new Set())
      setLast(null)
    })
    return () => {
      off()
      offReset()
    }
  }, [])
  return { reached, last }
}

function LoopStrip({ reached, last }: { reached: Set<LoopStep>; last: LoopStep | null }) {
  const notified = reached.has('notify')
  return (
    <nav aria-label="The demand loop" className="border-b border-line bg-surface">
      <ol className="no-scrollbar relative mx-auto flex max-w-[1440px] items-stretch gap-1 overflow-x-auto px-2 py-2 sm:px-6" aria-live="polite">
        {STEPS.map((s, i) => {
          const on = reached.has(s.key)
          const current = last === s.key || (s.key === 'approve' && last === 'notify')
          const done = on && (s.key !== 'approve' || notified)
          return (
            <li key={s.key} className="flex min-w-0 flex-1 items-center gap-2">
              <div
                className={cx(
                  'flex min-w-0 flex-1 items-center gap-1.5 rounded-xl px-1.5 py-1.5 transition-colors duration-500 sm:min-w-[150px] sm:gap-2.5 sm:px-2.5',
                  on ? 'bg-marigold-soft' : 'bg-transparent',
                  current && 'ring-1 ring-marigold',
                )}
              >
                <span
                  className={cx(
                    'grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold transition-colors duration-500',
                    done ? 'bg-maroon text-on-maroon' : on ? 'bg-marigold text-[#3b2400]' : 'bg-surface-2 text-ink-3',
                  )}
                >
                  {done ? <Check className="size-3.5" strokeWidth={3} aria-hidden /> : i + 1}
                </span>
                <span className="min-w-0 leading-tight">
                  <span className={cx('block text-[13px] font-semibold sm:text-sm', on ? 'text-ink' : 'text-ink-2')}>
                    <span className="sm:hidden">{s.short}</span>
                    <span className="hidden sm:inline">{s.title}</span>
                  </span>
                  <span className="hidden truncate text-[11px] text-ink-3 sm:block">{s.who}</span>
                </span>
                <span className="sr-only">{done ? ', done' : on ? ', in progress' : ', not started'}</span>
              </div>
              {i < STEPS.length - 1 && <span className={cx('hidden h-px w-4 shrink-0 transition-colors sm:block', on ? 'bg-marigold' : 'bg-line-strong')} aria-hidden />}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function PhoneFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative h-full w-[380px] shrink-0 rounded-[44px] border-[9px] border-[#231c1d] bg-[#231c1d] shadow-[0_30px_60px_-30px_rgba(35,28,29,0.55)] dark:border-[#3a3132] dark:bg-[#3a3132]">
      <div className="absolute top-1.5 left-1/2 z-50 h-5 w-24 -translate-x-1/2 rounded-full bg-[#231c1d] dark:bg-[#3a3132]" aria-hidden />
      <div className="h-full overflow-hidden rounded-[35px] bg-bg">{children}</div>
    </div>
  )
}

/** Animated pulse that travels from the shopper's phone toward the manager's feed when a signal lands. */
function Connector({ pulse }: { pulse: number }) {
  return (
    <div className="relative w-14 shrink-0" aria-hidden>
      <div className="absolute top-[28%] right-0 left-0 h-px bg-line-strong" />
      {pulse > 0 && (
        <div key={pulse} className="absolute top-[28%] right-0 left-0">
          <span className="absolute -top-[5px] size-[11px] rounded-full bg-marigold shadow-[0_0_0_4px_color-mix(in_oklab,var(--marigold)_30%,transparent)]" style={{ animation: 'rn-travel 1100ms ease-in-out 2' }} />
        </div>
      )}
    </div>
  )
}

export default function LivePage() {
  const wide = useMedia('(min-width: 1100px)')
  const [params, setParams] = useSearchParams()
  const q = params.get('q')
  const { reached, last } = useLoopProgress()
  const [pulse, setPulse] = useState(0)
  const [tab, setTab] = useState<'shop' | 'manager'>('shop')
  const [managerDot, setManagerDot] = useState(false)
  const [shopDot, setShopDot] = useState(false)

  useEffect(() => {
    const off = on('signal', () => {
      setPulse((p) => p + 1)
      setManagerDot(true)
    })
    const offN = on('notification', () => setShopDot(true))
    return () => {
      off()
      offN()
    }
  }, [])

  useEffect(() => {
    if (tab === 'manager') setManagerDot(false)
    if (tab === 'shop') setShopDot(false)
  }, [tab, managerDot, shopDot])

  const consumed = useCallback(() => {
    const next = new URLSearchParams(params)
    next.delete('q')
    setParams(next, { replace: true })
  }, [params, setParams])

  return (
    <main id="main" className="flex min-h-0 flex-1 flex-col">
      <h1 className="sr-only">Live loop: shopper and store manager side by side</h1>
      <LoopStrip reached={reached} last={last} />
      {wide ? (
        <div className="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 gap-0 px-6 py-5">
          <section aria-label="Shopper, Priya" className="flex min-h-0 flex-col items-center">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink-3">
              <Smartphone className="size-3.5" aria-hidden /> Priya, shopper
            </p>
            <div className="min-h-0 flex-1">
              <PhoneFrame>
                <ShopView embedded initialPrompt={q} onConsumedPrompt={consumed} />
              </PhoneFrame>
            </div>
          </section>
          <Connector pulse={pulse} />
          <section aria-label="Store manager, Arjun" className="flex min-h-0 min-w-0 flex-1 flex-col">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink-3">
              <BarChart3 className="size-3.5" aria-hidden /> Arjun, store manager
            </p>
            <div className="scrollbar-thin relative min-h-0 flex-1 overflow-y-auto rounded-3xl border border-line bg-bg p-5">
              <ManagerView variant="live" />
            </div>
          </section>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div role="tablist" aria-label="Choose a side" className="grid grid-cols-2 gap-1 border-b border-line bg-surface p-1.5">
            {(
              [
                ['shop', 'Shopper', Smartphone, shopDot],
                ['manager', 'Store manager', BarChart3, managerDot],
              ] as const
            ).map(([k, label, Icon, dot]) => (
              <button
                key={k}
                role="tab"
                id={`tab-${k}`}
                aria-selected={tab === k}
                aria-controls={`panel-${k}`}
                onClick={() => setTab(k)}
                className={cx(
                  'relative flex h-10 items-center justify-center gap-2 rounded-lg text-sm font-semibold',
                  tab === k ? 'bg-ink text-surface' : 'text-ink-2 hover:bg-surface-2',
                )}
              >
                <Icon className="size-4" aria-hidden />
                {label}
                {dot && tab !== k && <span className="size-2 rounded-full bg-marigold" aria-label="New activity" />}
              </button>
            ))}
          </div>
          <div id="panel-shop" role="tabpanel" aria-labelledby="tab-shop" hidden={tab !== 'shop'} className="relative min-h-0 flex-1">
            <ShopView initialPrompt={q} onConsumedPrompt={consumed} />
          </div>
          <div id="panel-manager" role="tabpanel" aria-labelledby="tab-manager" hidden={tab !== 'manager'} className="scrollbar-thin relative min-h-0 flex-1 overflow-y-auto px-4 py-5">
            <ManagerView variant="live" />
          </div>
        </div>
      )}
    </main>
  )
}
