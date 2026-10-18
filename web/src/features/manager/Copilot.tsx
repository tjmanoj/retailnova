import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  Boxes,
  Check,
  CircleDashed,
  Globe,
  LineChart,
  MessagesSquare,
  Minus,
  PackagePlus,
  RefreshCw,
  Send,
  Sparkles,
  Truck,
  X,
} from 'lucide-react'
import type { ActionProposal, ApproveResponse, Category, EvidenceKind, PlanStep, PlanStepId } from '../../types'
import { api } from '../../lib/api'
import { emit, on } from '../../lib/bus'
import { categoryLabel, DIWALI_DATE, storeName } from '../../lib/constants'
import { daysBetween, formatINR, formatNumber, longDate, pct, shortDate, sizeLabel } from '../../lib/format'
import { getSessionId } from '../../lib/session'
import { useActionUpdates, useProductInfo } from '../../lib/realtime'
import { useBootstrap } from '../../lib/bootstrap'
import { ActivityChips, type ActivityState } from '../../components/ActivityChips'
import { RichText } from '../../components/RichText'
import { ProductImage } from '../../components/ProductImage'
import { Badge, Button, Skeleton, Spinner, cx } from '../../components/ui'

const STEP_ORDER: PlanStepId[] = ['forecast', 'unmet_demand', 'inventory', 'transfers', 'trends', 'planner']

type PlanState = 'idle' | 'running' | 'done' | 'error'

export function Copilot({ storeId, category }: { storeId: string; category: Category }) {
  const [state, setState] = useState<PlanState>('idle')
  const [steps, setSteps] = useState<Record<string, PlanStep>>({})
  const [summary, setSummary] = useState('')
  const [proposals, setProposals] = useState<ActionProposal[]>([])
  const [error, setError] = useState<string | null>(null)
  const [meta, setMeta] = useState<{ latency_ms: number; model: string } | null>(null)
  const [planId, setPlanId] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)
  const proposalsRef = useRef<HTMLDivElement>(null)
  const hasProposals = proposals.length > 0

  // Bring the first proposal into view once, so Approve is one click away.
  useEffect(() => {
    if (!hasProposals) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const el = proposalsRef.current
    if (el && el.getBoundingClientRect().top > window.innerHeight - 220) el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  }, [hasProposals])

  useActionUpdates(planId, (u) =>
    setProposals((ps) =>
      ps.map((p) => (p.action_id === u.action_id && u.status && u.status !== p.status ? { ...p, status: u.status, decided_at: u.decided_at ?? p.decided_at } : p)),
    ),
  )

  const clear = () => {
    setSteps({})
    setSummary('')
    setProposals([])
    setError(null)
    setMeta(null)
    setPlanId(null)
  }

  useEffect(
    () =>
      on('reset', () => {
        abort.current?.abort()
        clear()
        setState('idle')
      }),
    [],
  )

  // A new store or category invalidates the current plan.
  useEffect(() => {
    abort.current?.abort()
    clear()
    setState('idle')
  }, [storeId, category])

  const generate = useCallback(async () => {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    clear()
    setState('running')
    emit('step', 'plan')
    let failed = false
    await api.plan(
      { store_id: storeId, category, horizon_days: 21, session_id: getSessionId() },
      (e) => {
        if (e.event === 'step') setSteps((s) => ({ ...s, [e.data.step.id]: { ...s[e.data.step.id], ...e.data.step } }))
        else if (e.event === 'text') setSummary((t) => t + e.data.delta)
        else if (e.event === 'proposal') setProposals((ps) => [...ps.filter((p) => p.action_id !== e.data.proposal.action_id), e.data.proposal])
        else if (e.event === 'error') {
          failed = true
          setError(e.data.message)
        } else if (e.event === 'done') {
          setMeta({ latency_ms: e.data.latency_ms, model: e.data.model })
          if (e.data.plan_id) setPlanId(e.data.plan_id)
        }
      },
      ctrl.signal,
    )
    if (!ctrl.signal.aborted) setState(failed ? 'error' : 'done')
  }, [storeId, category])

  const stepList = STEP_ORDER.map((id) => steps[id]).filter(Boolean) as PlanStep[]
  const extra = Object.values(steps).filter((s) => !STEP_ORDER.includes(s.id))

  return (
    <section className="@container rounded-2xl border border-line bg-surface" aria-labelledby="copilot-title">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3.5 @[560px]:px-5">
        <div className="min-w-0">
          <h2 id="copilot-title" className="display-tight flex items-center gap-2 text-lg text-ink">
            <Sparkles className="size-4 text-marigold" aria-hidden />
            Ops copilot
          </h2>
          <p className="text-xs text-ink-3">
            Plans transfers and reorders for {storeName(storeId)}, {categoryLabel(category).toLowerCase()}, before Diwali. You approve every action.
          </p>
        </div>
        <Button
          variant="primary"
          size="md"
          onClick={generate}
          loading={state === 'running'}
          icon={state === 'done' || state === 'error' ? <RefreshCw className="size-4" aria-hidden /> : <Sparkles className="size-4" aria-hidden />}
        >
          {state === 'running' ? 'Planning…' : state === 'idle' ? 'Generate Diwali action plan' : 'Regenerate plan'}
        </Button>
      </header>

      {state === 'idle' ? (
        <div className="grid gap-4 px-4 py-5 @[560px]:grid-cols-[1fr_auto] @[560px]:px-5">
          <ol className="grid gap-2 text-sm text-ink-2 @[720px]:grid-cols-3">
            {[
              ['Reads both forecasts', LineChart],
              ['Counts unmet asks and stock', MessagesSquare],
              ['Proposes moves with evidence', Truck],
            ].map(([t, Icon], i) => {
              const I = Icon as typeof LineChart
              return (
                <li key={i} className="flex items-center gap-2.5 rounded-xl bg-surface-2 px-3 py-2.5">
                  <I className="size-4 shrink-0 text-ink-3" aria-hidden />
                  {t as string}
                </li>
              )
            })}
          </ol>
        </div>
      ) : (
        <div className="grid gap-0 @[760px]:grid-cols-[minmax(260px,0.8fr)_1.6fr]">
          <div className="border-b border-line px-4 py-4 @[560px]:px-5 @[760px]:border-r @[760px]:border-b-0">
            <h3 className="mb-3 text-xs font-semibold text-ink-3">Agent steps</h3>
            {stepList.length === 0 && state === 'running' ? (
              <div className="space-y-3" aria-hidden>
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="flex gap-3">
                    <Skeleton className="size-6 rounded-full" />
                    <Skeleton className="h-4 flex-1" />
                  </div>
                ))}
              </div>
            ) : (
              <ol className="relative" aria-live="polite">
                {[...stepList, ...extra].map((s, i, arr) => (
                  <StepItem key={s.id} s={s} last={i === arr.length - 1} />
                ))}
              </ol>
            )}
            {meta && meta.latency_ms > 0 && (
              <p className="mt-3 text-[11px] text-ink-3">
                Finished in {(meta.latency_ms / 1000).toFixed(1)}s
                {meta.model === 'rules' ? ', using the rule-based planner' : meta.model.startsWith('gemini') ? ' with Gemini' : ''}
              </p>
            )}
          </div>
          <div className="min-w-0 px-4 py-4 @[560px]:px-5">
            {error && (
              <div role="alert" className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2.5 text-sm text-danger">
                <AlertTriangle className="size-4 shrink-0" aria-hidden />
                <span className="flex-1">{error}</span>
                <button onClick={generate} className="inline-flex items-center gap-1.5 rounded-lg bg-surface px-2.5 py-1 text-xs font-semibold text-ink hover:bg-surface-2">
                  <RefreshCw className="size-3.5" aria-hidden /> Try again
                </button>
              </div>
            )}
            {summary ? (
              <div className="mb-4 rounded-xl bg-surface-2 px-3.5 py-3 text-sm leading-relaxed text-ink" aria-live="polite">
                <RichText text={summary} />
              </div>
            ) : (
              state === 'running' && (
                <div className="mb-4 space-y-2" aria-hidden>
                  <Skeleton className="h-3.5 w-full" />
                  <Skeleton className="h-3.5 w-4/5" />
                </div>
              )
            )}
            <div className="scroll-mt-4 space-y-3" ref={proposalsRef}>
              {proposals.map((p) => (
                <ProposalCard key={p.action_id} p={p} />
              ))}
              {state === 'running' && proposals.length === 0 && (
                <div className="rounded-2xl border border-dashed border-line-strong p-4 text-sm text-ink-3">Proposals appear here as soon as the planner finishes.</div>
              )}
              {state === 'done' && proposals.length === 0 && !error && (
                <div className="rounded-2xl border border-dashed border-line-strong p-4 text-sm text-ink-3">
                  No actions needed for {categoryLabel(category).toLowerCase()} at {storeName(storeId)} right now.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      <AskBox storeId={storeId} />
    </section>
  )
}

function StepItem({ s, last }: { s: PlanStep; last: boolean }) {
  const dur = s.started_at && s.finished_at ? (new Date(s.finished_at).getTime() - new Date(s.started_at).getTime()) / 1000 : null
  const icon =
    s.status === 'running' ? (
      <span className="grid size-6 place-items-center rounded-full bg-marigold-soft text-marigold-ink ring-1 ring-marigold">
        <Spinner className="size-3.5" />
      </span>
    ) : s.status === 'done' ? (
      <span className="grid size-6 place-items-center rounded-full bg-leaf text-white">
        <Check className="size-3.5" strokeWidth={3} aria-hidden />
      </span>
    ) : s.status === 'skipped' ? (
      <span className="grid size-6 place-items-center rounded-full bg-surface-3 text-ink-3">
        <Minus className="size-3.5" aria-hidden />
      </span>
    ) : (
      <span className="grid size-6 place-items-center rounded-full bg-danger-soft text-danger">
        <AlertTriangle className="size-3.5" aria-hidden />
      </span>
    )
  return (
    <li className="anim-fade relative flex gap-3 pb-4 last:pb-0">
      {!last && <span className="absolute top-7 bottom-1 left-[11px] w-px bg-line-strong" aria-hidden />}
      <span className="relative z-10 shrink-0">{icon}</span>
      <div className="min-w-0 pt-0.5">
        <p className="flex items-baseline gap-2 text-sm font-semibold text-ink">
          {s.label}
          {dur != null && dur > 0 && <span className="num text-[11px] font-normal text-ink-3">{dur.toFixed(1)}s</span>}
          <span className="sr-only">, {s.status}</span>
        </p>
        {s.summary ? (
          <p className="mt-0.5 text-[13px] leading-snug text-ink-2">{s.summary}</p>
        ) : s.status === 'running' ? (
          <p className="mt-0.5 text-[13px] text-ink-3">Working…</p>
        ) : null}
      </div>
    </li>
  )
}

function formatEvidence(v: number) {
  return Number.isInteger(v) ? formatNumber(v) : v.toFixed(Math.abs(v) < 10 ? 1 : 0)
}

const EVIDENCE_ICON: Record<EvidenceKind, typeof LineChart> = {
  forecast: LineChart,
  signals: MessagesSquare,
  inventory: Boxes,
  trend: Globe,
}

function ProposalCard({ p: initial }: { p: ActionProposal }) {
  const [p, setP] = useState(initial)
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [result, setResult] = useState<ApproveResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const info = useProductInfo(p.sku)

  useEffect(() => setP(initial), [initial])

  const decide = async (kind: 'approve' | 'reject') => {
    setBusy(kind)
    setErr(null)
    try {
      if (kind === 'approve') {
        const r = await api.approve(p.action_id)
        setP(r.action)
        setResult(r)
        emit('step', 'approve')
      } else {
        const r = await api.reject(p.action_id)
        setP(r.action)
      }
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const isTransfer = p.type === 'transfer'
  const typeLabel = { transfer: 'Transfer', reorder: 'Reorder', markdown: 'Markdown', assortment: 'Assortment' }[p.type]
  const TypeIcon = isTransfer ? Truck : PackagePlus
  const daysBefore = daysBetween(p.eta_date, DIWALI_DATE)
  const decided = p.status !== 'proposed'
  const title = isTransfer
    ? `Move ${p.quantity} units from ${storeName(p.from_store_id)} to ${storeName(p.store_id)}`
    : p.type === 'reorder'
      ? `Reorder ${p.quantity} units for ${storeName(p.store_id)}`
      : `${typeLabel}: ${p.quantity} units at ${storeName(p.store_id)}`

  return (
    <article
      className={cx(
        'anim-rise rounded-2xl border bg-surface transition-colors',
        p.status === 'approved' || p.status === 'executed' ? 'border-leaf/50' : p.status === 'rejected' ? 'border-line opacity-70' : 'border-line-strong',
      )}
      aria-label={title}
    >
      <div className="flex flex-wrap items-center gap-2 px-4 pt-3.5">
        <Badge tone={isTransfer ? 'peacock' : 'marigold'} icon={<TypeIcon className="size-3.5" aria-hidden />}>
          {typeLabel}
        </Badge>
        {p.status === 'approved' || p.status === 'executed' ? (
          <Badge tone="leaf" icon={<Check className="size-3" aria-hidden />}>
            Approved
          </Badge>
        ) : p.status === 'rejected' ? (
          <Badge tone="neutral">Rejected</Badge>
        ) : null}
        <Confidence value={p.confidence} />
      </div>

      <div className="px-4 pt-2">
        <h4 className="display-tight text-[21px] leading-tight text-ink">{title}</h4>
        <div className="mt-2 flex items-center gap-2.5">
          {p.sku && (
            <ProductImage
              src={info?.image_url ?? `/products/${p.sku}.webp`}
              alt={info?.image_alt ?? p.sku}
              category={p.category}
              color={p.sku.startsWith('SAR-001') ? 'maroon' : undefined}
              className="size-10 shrink-0 rounded-lg"
            />
          )}
          <p className="min-w-0 text-sm text-ink-2">
            <span className="num font-semibold text-ink">{p.sku ?? categoryLabel(p.category)}</span>
            {info?.name ? ` ${info.name}` : ''}
            {p.size && p.size !== 'FREE' ? `, size ${sizeLabel(p.size)}` : ''}
          </p>
        </div>
        {isTransfer && p.from_store_id && (
          <p className="mt-2 flex items-center gap-2 text-xs font-semibold text-ink-2">
            <span className="rounded-md bg-surface-2 px-2 py-1">{storeName(p.from_store_id)}</span>
            <ArrowRight className="size-3.5 text-ink-3" aria-label="to" />
            <span className="rounded-md bg-surface-2 px-2 py-1">{storeName(p.store_id)}</span>
            <span className="num ml-1 font-normal text-ink-3">{p.quantity} units</span>
          </p>
        )}
        <p className="mt-3 text-sm leading-relaxed text-ink">{p.rationale}</p>
      </div>

      {p.evidence.length > 0 && (
        <ul className="mx-4 mt-3 space-y-1.5 border-t border-line pt-3" aria-label="Evidence">
          {p.evidence.map((ev, i) => {
            const I = EVIDENCE_ICON[ev.kind] ?? LineChart
            return (
              <li key={i} className="flex items-start gap-2 text-[13px] text-ink-2">
                <I className="mt-0.5 size-3.5 shrink-0 text-ink-3" aria-hidden />
                <span className="sr-only">{ev.kind}: </span>
                <span className="flex-1">{ev.text}</span>
                {ev.value != null && !ev.text.includes(formatNumber(ev.value)) && !ev.text.includes(String(ev.value)) && (
                  <span className="figure shrink-0 text-sm text-ink">{formatEvidence(ev.value)}</span>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <dl className="mx-4 mt-3 grid grid-cols-2 gap-3 border-t border-line pt-3">
        <div>
          <dt className="text-xs text-ink-3">Revenue protected</dt>
          <dd className="figure text-xl text-leaf">{formatINR(p.expected_revenue_protected_inr)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-3">{isTransfer ? 'Arrives' : `Arrives (${p.supplier_lead_days ?? '?'}-day lead)`}</dt>
          <dd className="text-sm font-semibold text-ink">
            {shortDate(p.eta_date)}
            {daysBefore > 0 && <span className="block text-xs font-normal text-ink-3">{daysBefore} days before Diwali</span>}
          </dd>
        </div>
      </dl>

      <div className="px-4 pt-3 pb-4" aria-live="polite">
        {!decided ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => decide('approve')} loading={busy === 'approve'} disabled={busy !== null} icon={<Check className="size-4" aria-hidden />}>
              Approve {typeLabel.toLowerCase()}
            </Button>
            <Button variant="ghost" onClick={() => decide('reject')} loading={busy === 'reject'} disabled={busy !== null} icon={<X className="size-4" aria-hidden />}>
              Reject
            </Button>
          </div>
        ) : result ? (
          <ApprovedResult r={result} type={p.type} />
        ) : p.status === 'rejected' ? (
          <p className="text-sm text-ink-3">Rejected{p.decided_at ? ` on ${longDate(p.decided_at)}` : ''}. Nothing changed.</p>
        ) : (
          <p className="text-sm text-leaf">Approved.</p>
        )}
        {err && <p className="mt-2 text-sm text-danger">{err}</p>}
      </div>
    </article>
  )
}

function Confidence({ value }: { value: number }) {
  const v = Math.max(0, Math.min(1, value))
  return (
    <span className="ml-auto inline-flex items-center gap-2 text-xs text-ink-3" title="Model confidence">
      <span className="sr-only">Confidence</span>
      <span className="relative h-1.5 w-16 overflow-hidden rounded-full bg-surface-3" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)} aria-label="Confidence">
        <span className="absolute inset-y-0 left-0 rounded-full bg-ink-2" style={{ width: `${v * 100}%` }} />
      </span>
      <span className="num font-semibold text-ink">{pct(v)}</span>
      <span aria-hidden>confidence</span>
    </span>
  )
}

function ApprovedResult({ r, type }: { r: ApproveResponse; type: ActionProposal['type'] }) {
  const n = r.notifications_created
  const reorder = type === 'reorder'
  const notified = reorder
    ? n === 0
      ? 'No shoppers waiting yet'
      : `${n === 1 ? '1 waiting shopper' : `${n} waiting shoppers`} told when it arrives`
    : n === 0
      ? 'No shoppers waiting yet'
      : `${n === 1 ? '1 shopper' : `${n} shoppers`} notified, with the item reserved`
  return (
    <div className="anim-slide-down rounded-xl border border-leaf/30 bg-leaf-soft px-3.5 py-3">
      <p className="flex items-center gap-1.5 text-sm font-semibold text-leaf">
        <Check className="size-4" aria-hidden /> {reorder ? 'Approved. Purchase order placed.' : 'Approved. Inventory updated.'}
      </p>
      {r.inventory_changes.length > 0 && (
        <ul className="mt-2 space-y-1 text-[13px] text-ink">
          {r.inventory_changes.map((c, i) => {
            const incoming = c.incoming_delta != null && c.incoming_delta !== 0
            return (
              <li key={i} className="flex flex-wrap items-center justify-between gap-x-3">
                <span>
                  {storeName(c.store_id)} <span className="num text-ink-3">{c.sku}</span>
                  {c.size && c.size !== 'FREE' ? <span className="text-ink-3">, {sizeLabel(c.size)}</span> : null}
                </span>
                {incoming ? (
                  <span className="num shrink-0">
                    <span className="font-semibold text-peacock">+{c.incoming_delta} incoming</span>
                    <span className="text-ink-3">
                      {c.incoming_eta ? `, arrives ${shortDate(c.incoming_eta)}` : ''}
                      {c.incoming_after != null ? ` (${c.incoming_after} on order)` : ''}
                    </span>
                  </span>
                ) : (
                  <span className="num shrink-0">
                    <span className={cx('font-semibold', c.delta > 0 ? 'text-leaf' : c.delta < 0 ? 'text-maroon-ink' : 'text-ink-3')}>
                      {c.delta > 0 ? `+${c.delta}` : c.delta}
                    </span>
                    <span className="text-ink-3"> → {c.on_hand_after} on hand</span>
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <p className="mt-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
        {reorder ? <Truck className="size-4 text-peacock" aria-hidden /> : <BellRing className="size-4 text-marigold-ink" aria-hidden />}
        {notified}
      </p>
    </div>
  )
}

function AskBox({ storeId }: { storeId: string }) {
  const boot = useBootstrap()
  const [q, setQ] = useState('')
  const [answer, setAnswer] = useState('')
  const [asked, setAsked] = useState('')
  const [acts, setActs] = useState<ActivityState[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => on('reset', () => (setAnswer(''), setAsked(''), setActs([]))), [])

  const ask = async (question: string) => {
    const text = question.trim()
    if (!text || busy) return
    setBusy(true)
    setAnswer('')
    setActs([])
    setErr(null)
    setAsked(text)
    setQ('')
    await api.ask({ store_id: storeId, question: text, session_id: getSessionId() }, (e) => {
      if (e.event === 'activity')
        setActs((as) => (as.some((a) => a.id === e.data.id) ? as.map((a) => (a.id === e.data.id ? { ...a, ...e.data } : a)) : [...as, e.data]))
      else if (e.event === 'text') setAnswer((a) => a + e.data.delta)
      else if (e.event === 'error') setErr(e.data.message)
      else if (e.event === 'done') setActs((as) => as.map((a) => ({ ...a, status: 'end' as const })))
    })
    setBusy(false)
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void ask(q)
  }

  return (
    <div className="border-t border-line px-4 py-4 @[560px]:px-5">
      <form onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="ask-input" className="sr-only">
          Ask about demand, stock or forecasts
        </label>
        <input
          id="ask-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          maxLength={500}
          placeholder="Ask about demand, stock or the forecast…"
          className="h-10 min-w-0 flex-1 rounded-xl border border-line-strong bg-bg px-3 text-sm text-ink placeholder:text-ink-3 focus:border-ink-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-marigold/50"
        />
        <Button type="submit" variant="secondary" loading={busy} disabled={!q.trim()} icon={<Send className="size-4" aria-hidden />}>
          Ask
        </Button>
      </form>
      {!asked && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {boot.sample_prompts.manager.slice(0, 3).map((p) => (
            <button key={p} onClick={() => void ask(p)} className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-2 hover:border-ink-3 hover:text-ink">
              {p}
            </button>
          ))}
        </div>
      )}
      {asked && (
        <div className="mt-3 space-y-2" aria-live="polite">
          <p className="text-xs font-semibold text-ink-3">{asked}</p>
          <ActivityChips items={acts} />
          {answer ? (
            <div className="text-sm leading-relaxed text-ink">
              <RichText text={answer} />
            </div>
          ) : busy && acts.length === 0 ? (
            <CircleDashed className="size-4 animate-spin text-ink-3" aria-label="Thinking" />
          ) : null}
          {err && (
            <p className="flex items-center gap-2 text-sm text-danger" role="alert">
              {err}
              <button onClick={() => void ask(asked)} className="rounded-md bg-surface-2 px-2 py-0.5 text-xs font-semibold text-ink">
                Try again
              </button>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
