import { useCallback, useEffect, useRef, useState } from 'react'
import { Pause, Play, X } from 'lucide-react'
import { api } from '../../lib/api'
import { emit, on, type LoopStep } from '../../lib/bus'
import { cx } from '../../components/ui'

export const HERO_PROMPT = 'Do you have the maroon Kanchipuram silk saree with gold zari border? Need it for Diwali, under ₹5,000.'

type Caption = { step: number; title: string; text: string; tone?: 'info' | 'wait' | 'done' | 'error' }

const TITLES = ['Ask', 'Signal', 'Plan', 'Approve & notify']

class Stopped extends Error {}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = window.setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      window.clearTimeout(t)
      reject(new Stopped())
    })
  })

/** Poll for a condition; after `slowAfter` ms call onSlow once, give up after `timeout` ms. */
async function waitFor<T>(fn: () => T | null | undefined | false, signal: AbortSignal, timeout: number, slowAfter?: number, onSlow?: () => void): Promise<T> {
  const t0 = performance.now()
  let slowFired = false
  for (;;) {
    if (signal.aborted) throw new Stopped()
    const v = fn()
    if (v) return v
    const dt = performance.now() - t0
    if (!slowFired && slowAfter && dt > slowAfter) {
      slowFired = true
      onSlow?.()
    }
    if (dt > timeout) throw new Error('timeout')
    await sleep(250, signal)
  }
}

function spotlight(el: Element | null) {
  document.querySelectorAll('.demo-spotlight').forEach((n) => n.classList.remove('demo-spotlight'))
  if (!el) return
  el.classList.add('demo-spotlight')
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center', inline: 'nearest' })
}

const q = <T extends Element = HTMLElement>(sel: string) => document.querySelector<T>(sel)
const visible = (el: HTMLElement | null) => (el && el.offsetParent !== null ? el : null)

/**
 * Drives the real Live Loop end to end: reset, ask, notify, signal, plan, approve, notification.
 * Every wait has a timeout; slow calls update the caption instead of failing.
 */
export function useGuidedDemo() {
  const [caption, setCaption] = useState<Caption | null>(null)
  const [running, setRunning] = useState(false)
  const ctrl = useRef<AbortController | null>(null)
  const reached = useRef<Set<LoopStep>>(new Set())

  useEffect(() => on('step', (s) => reached.current.add(s)), [])

  const stop = useCallback((silent = false) => {
    if (ctrl.current) emit('demoCancel', null)
    ctrl.current?.abort()
    ctrl.current = null
    spotlight(null)
    setRunning(false)
    if (!silent) setCaption(null)
  }, [])

  const start = useCallback(async () => {
    ctrl.current?.abort()
    const c = new AbortController()
    ctrl.current = c
    const signal = c.signal
    setRunning(true)
    const say = (step: number, text: string, tone: Caption['tone'] = 'info') => setCaption({ step, title: TITLES[Math.max(0, step - 1)] ?? '', text, tone })
    try {
      say(0, 'Resetting the demo so you see a clean run…', 'wait')
      try {
        await api.reset()
      } catch {
        /* keep going with the current state */
      }
      emit('reset', null)
      emit('newChat', null)
      reached.current = new Set()
      await sleep(900, signal)

      // 1. Ask
      emit('demoTab', 'shop')
      say(1, 'Priya asks the concierge for a maroon Kanchipuram silk saree for Diwali, under ₹5,000.')
      await sleep(600, signal)
      emit('demoType', HERO_PROMPT)
      const notify = await waitFor(
        () => visible(q('[data-demo="notify"][data-sku="SAR-001"]')) || visible(q('[data-demo="notify"]')),
        signal,
        75_000,
        12_000,
        () => say(1, 'The concierge is checking live stock across every store…', 'wait'),
      )
      say(1, "It's sold out at T. Nagar, so she sees where it is in stock and taps Notify me.")
      spotlight(notify)
      await sleep(2600, signal)
      notify.click()

      // 2. Signal
      await waitFor(() => reached.current.has('signal'), signal, 40_000, 8_000, () => say(2, 'Turning her ask into a demand signal…', 'wait')).catch((e) => {
        if (e instanceof Stopped) throw e
      })
      emit('demoTab', 'manager')
      await sleep(500, signal)
      say(2, "Her ask lands on Arjun's demand radar as unmet demand, live.")
      spotlight(q('[data-feed] li.anim-flash') || q('[data-feed] li'))
      await sleep(3200, signal)

      // 3. Plan
      const gen = await waitFor(() => visible(q('[data-demo="generate-plan"]')), signal, 10_000)
      say(3, 'Arjun asks the ops copilot for a Diwali plan. Agents read both forecasts, stock and transfer options in parallel.')
      spotlight(gen)
      await sleep(1800, signal)
      gen.click()
      const approve = await waitFor(
        () => visible(q('[data-demo="approve"][data-type="transfer"]')) || visible(q('[data-demo="approve"]')),
        signal,
        100_000,
        15_000,
        () => say(3, 'Still planning. The forecasts come from BigQuery, so this can take a few more seconds…', 'wait'),
      )
      await sleep(800, signal)
      say(3, 'The plan proposes a transfer, with the evidence and the revenue it protects.')
      spotlight(approve.closest('article') ?? approve)
      await sleep(3400, signal)

      // 4. Approve & notify
      say(4, 'Arjun approves. Stock moves now, and shoppers who were waiting are notified.')
      spotlight(approve)
      await sleep(1400, signal)
      approve.click()
      await waitFor(() => reached.current.has('notify'), signal, 30_000, 8_000, () => say(4, 'Sending the notification…', 'wait')).catch((e) => {
        if (e instanceof Stopped) throw e
      })
      emit('demoTab', 'shop')
      await sleep(900, signal)
      say(4, 'Priya gets "Reserved for you at T. Nagar" with a pickup pass. One conversation changed the stock plan.', 'done')
      spotlight(q('[data-sku="SAR-001"] [data-demo="pass"]') || q('[data-sku="SAR-001"]'))
      await sleep(7000, signal)
      spotlight(null)
      say(4, 'That was the loop. Now try it yourself: ask anything, send a photo or a voice note, or log a walk-in request.', 'done')
      setRunning(false)
    } catch (e) {
      spotlight(null)
      setRunning(false)
      if (e instanceof Stopped) return
      say(0, 'The service is taking longer than usual. The demo stopped here, and you can carry on by hand.', 'error')
    }
  }, [])

  useEffect(() => {
    if (!caption) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') stop()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [caption, stop])

  useEffect(() => () => ctrl.current?.abort(), [])

  return { caption, running, start, stop }
}

export function DemoCaptionBar({
  caption,
  running,
  onStop,
  onReplay,
  wide = false,
}: {
  caption: Caption
  running: boolean
  onStop: () => void
  onReplay: () => void
  wide?: boolean
}) {
  return (
    <div
      className={cx(
        'pointer-events-none fixed z-[70] flex justify-center px-3',
        // Wide Live Loop: float over the manager pane so the phone's composer stays visible.
        wide ? 'right-6 bottom-5 left-[470px]' : 'inset-x-0 bottom-[104px]',
      )}
      role="region"
      aria-label="Guided demo"
    >
      <div className="anim-toast pointer-events-auto flex w-full max-w-[760px] items-start gap-3 rounded-2xl bg-[#231c1d] p-3.5 pr-2.5 text-white shadow-float sm:items-center">
        <div className="hidden shrink-0 gap-1 sm:flex" aria-hidden>
          {[1, 2, 3, 4].map((n) => (
            <span key={n} className={cx('h-1.5 w-6 rounded-full', n < caption.step ? 'bg-marigold' : n === caption.step ? 'bg-marigold' : 'bg-white/20', n === caption.step && running && 'animate-pulse')} />
          ))}
        </div>
        <div className="min-w-0 flex-1" aria-live="polite">
          <p className="text-xs font-semibold text-marigold">
            {caption.step > 0 ? `Step ${caption.step} of 4: ${caption.title}` : 'Guided demo'}
          </p>
          <p className="text-sm leading-snug text-white/90">{caption.text}</p>
        </div>
        {running ? (
          <button onClick={onStop} className="flex shrink-0 items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1.5 text-xs font-semibold hover:bg-white/20">
            <Pause className="size-3.5" aria-hidden />
            Stop <span className="hidden text-white/60 sm:inline">(Esc)</span>
          </button>
        ) : (
          <div className="flex shrink-0 gap-1">
            <button onClick={onReplay} className="flex items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1.5 text-xs font-semibold hover:bg-white/20">
              <Play className="size-3.5" aria-hidden /> Replay
            </button>
            <button onClick={onStop} className="rounded-lg p-1.5 text-white/70 hover:bg-white/10 hover:text-white" aria-label="Close guided demo">
              <X className="size-4" aria-hidden />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
