import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, RefreshCw } from 'lucide-react'
import type { Category, Radar } from '../../types'
import { api } from '../../lib/api'
import { on } from '../../lib/bus'
import { useBootstrap } from '../../lib/bootstrap'
import { categoryLabel, DEFAULT_CATEGORY, DEFAULT_STORE, storeName } from '../../lib/constants'
import { formatINR, formatNumber, longDate } from '../../lib/format'
import { Badge, Select, Skeleton, cx } from '../../components/ui'
import { ChartLegend, DemandChart, useForecastGap } from './DemandChart'
import { SignalFeed } from './SignalFeed'
import { Copilot } from './Copilot'

function useRadar(storeId: string, category: Category) {
  const [data, setData] = useState<Radar | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const reqId = useRef(0)

  const load = useCallback(
    async (quiet = false) => {
      const id = ++reqId.current
      if (!quiet) setLoading(true)
      setError(null)
      // Retry twice with a short backoff: the API may be cold-starting.
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const r = await api.radar(storeId, category)
          if (id === reqId.current) {
            setData(r)
            setLoading(false)
          }
          return
        } catch (e) {
          if (id !== reqId.current) return
          if (attempt === 2) {
            if (!quiet) setError((e as Error).message)
            setLoading(false)
            return
          }
          await new Promise((res) => setTimeout(res, 1200 * (attempt + 1)))
        }
      }
    },
    [storeId, category],
  )

  useEffect(() => {
    setData(null)
    void load()
  }, [load])

  // Refresh KPIs quietly when a live signal lands for this store, and after a reset.
  useEffect(() => {
    let t: number | undefined
    const offSignal = on('signal', (s) => {
      if (s.store_id !== storeId) return
      window.clearTimeout(t)
      t = window.setTimeout(() => void load(true), 1500)
    })
    const offApprove = on('step', (st) => {
      if (st !== 'approve') return
      window.clearTimeout(t)
      t = window.setTimeout(() => void load(true), 800)
    })
    const offReset = on('reset', () => void load(true))
    return () => {
      window.clearTimeout(t)
      offSignal()
      offApprove()
      offReset()
    }
  }, [load, storeId])

  return { data, error, loading, reload: () => load() }
}

export function ManagerView({ variant = 'page' }: { variant?: 'page' | 'live' }) {
  const boot = useBootstrap()
  const [storeId, setStoreId] = useState(DEFAULT_STORE)
  const [category, setCategory] = useState<Category>(DEFAULT_CATEGORY)
  const { data, error, loading, reload } = useRadar(storeId, category)
  const live = variant === 'live'

  const header = (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-maroon-ink">Store manager view</p>
        <h1 className={cx('display text-ink', live ? 'text-[30px]' : 'text-[36px] @[900px]:text-[44px]')}>Demand radar</h1>
        <p className="mt-1 text-sm text-ink-3">
          {storeName(storeId)}, as of {longDate(data?.as_of ?? boot.demo_today)}
        </p>
      </div>
      <div className="flex w-full gap-2 @[640px]:w-auto">
        <Select label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)} className="min-w-0 flex-1 @[640px]:w-[170px] @[640px]:flex-none">
          {boot.stores
            .filter((s) => s.type === 'store')
            .map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.name}
              </option>
            ))}
        </Select>
        <Select label="Category" value={category} onChange={(e) => setCategory(e.target.value as Category)} className="min-w-0 flex-1 @[640px]:w-[200px] @[640px]:flex-none">
          {boot.categories.map((c) => (
            <option key={c.category} value={c.category}>
              {c.label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  )

  const kpis = <KpiStrip radar={data} loading={loading && !data} daysToDiwali={boot.days_to_diwali} compact={live} />

  const chart = (
    <section className="rounded-2xl border border-line bg-surface p-4 @[560px]:p-5" aria-labelledby="chart-title">
      {data ? (
        <ChartHeader radar={data} category={category} />
      ) : error ? (
        <h2 id="chart-title" className="display-tight text-lg text-ink">
          What sales say vs what customers asked for
        </h2>
      ) : (
        <Skeleton className="h-12 w-2/3" />
      )}
      <div className="mt-3">
        {data ? (
          <DemandChart series={data.series} height={live ? 260 : 330} />
        ) : error ? (
          <div className={cx('grid place-items-center rounded-xl bg-surface-2 text-sm text-ink-3', live ? 'h-[260px]' : 'h-[330px]')}>
            The forecast chart is unavailable right now.
          </div>
        ) : (
          <Skeleton className={live ? 'h-[260px]' : 'h-[330px]'} />
        )}
      </div>
      <div className="mt-3">
        <ChartLegend />
      </div>
      <p className="mt-2 text-[11px] text-ink-3">Daily units. Last 56 days of sales and the next 42 days of forecasts from BigQuery TimesFM.</p>
    </section>
  )

  const gaps = <TopGaps radar={data} loading={loading && !data} failed={Boolean(error) && !data} />
  const feed = <SignalFeed storeId={storeId} seed={data?.recent_signals} maxHeight={live ? 360 : 640} className="h-full" />
  const copilot = <Copilot storeId={storeId} category={category} />

  const errorBanner = error && (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
      <AlertTriangle className="size-4" aria-hidden />
      <span className="flex-1">Couldn't load the radar. {error}</span>
      <button onClick={reload} className="inline-flex items-center gap-1.5 rounded-lg bg-surface px-2.5 py-1 text-xs font-semibold text-ink hover:bg-surface-2">
        <RefreshCw className="size-3.5" aria-hidden /> Try again
      </button>
    </div>
  )

  if (live) {
    return (
      <div className="@container flex flex-col gap-4">
        {header}
        {errorBanner}
        {kpis}
        <div className="grid gap-4 @[680px]:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div className="min-h-0 @[680px]:sticky @[680px]:top-0 @[680px]:self-start">{feed}</div>
          <div className="min-w-0">{copilot}</div>
        </div>
        {chart}
        {gaps}
      </div>
    )
  }

  return (
    <div className="@container flex flex-col gap-5">
      {header}
      {errorBanner}
      {kpis}
      <div className="grid gap-5 @[1000px]:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <div className="flex min-w-0 flex-col gap-5">
          {chart}
          {gaps}
        </div>
        <div className="min-h-0 @[1000px]:relative">
          <div className="@[1000px]:absolute @[1000px]:inset-0">{feed}</div>
        </div>
      </div>
      {copilot}
    </div>
  )
}

function KpiStrip({ radar, loading, daysToDiwali, compact = false }: { radar: Radar | null; loading: boolean; daysToDiwali: number; compact?: boolean }) {
  const k = radar?.kpis
  const tiles: { label: string; value: string; note?: string; strong?: boolean }[] = [
    { label: 'Unmet demand, 7 days', value: formatINR(k?.unmet_value_7d_inr), note: 'Asked for, not sold', strong: true },
    { label: 'Unmet units, 7 days', value: formatNumber(k?.unmet_units_7d) },
    { label: 'Stockouts now', value: formatNumber(k?.stockouts_now), note: 'SKU-sizes at zero' },
    { label: 'Signals today', value: formatNumber(k?.signals_today) },
    { label: 'Days to Diwali', value: String(radar?.days_to_diwali ?? daysToDiwali), note: '8 November' },
  ]
  if (compact) {
    return (
      <section aria-label="Key numbers" className="grid grid-cols-4 overflow-hidden rounded-2xl border border-line bg-surface @[560px]:grid-cols-5">
        {tiles.map((t, i) => (
          <div
            key={t.label}
            className={cx(
              'border-line px-3 py-2.5',
              i === 0 ? 'col-span-4 border-b @[560px]:col-span-1 @[560px]:border-b-0' : '',
              i > 0 && i !== 1 ? 'border-l' : '',
              i === 1 ? '@[560px]:border-l' : '',
              t.strong && 'bg-maroon-soft',
            )}
          >
            <p className={cx('text-[11px] leading-tight font-medium', t.strong ? 'text-maroon-ink' : 'text-ink-3')}>{t.label}</p>
            {loading ? (
              <Skeleton className="mt-1.5 h-6 w-16" />
            ) : (
              <p className={cx('figure mt-1 text-[22px] leading-none', t.strong ? 'text-maroon-ink' : 'text-ink')}>{t.value}</p>
            )}
          </div>
        ))}
      </section>
    )
  }
  return (
    <section aria-label="Key numbers" className="grid grid-cols-2 overflow-hidden rounded-2xl border border-line bg-surface @[700px]:grid-cols-5">
      {tiles.map((t, i) => (
        <div
          key={t.label}
          className={cx(
            'border-line px-4 py-3.5',
            i === 0 ? 'col-span-2 border-b @[700px]:col-span-1 @[700px]:border-b-0' : '',
            i > 0 && i % 2 === 0 ? 'border-l @[700px]:border-l' : '',
            i > 0 && i < 3 ? 'border-b @[700px]:border-b-0' : '',
            i > 0 ? '@[700px]:border-l' : '',
            t.strong && 'bg-maroon-soft',
          )}
        >
          <p className={cx('text-xs font-medium', t.strong ? 'text-maroon-ink' : 'text-ink-3')}>{t.label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-7 w-20" />
          ) : (
            <p className={cx('figure mt-1 text-[28px] leading-none', t.strong ? 'text-maroon-ink' : 'text-ink')}>{t.value}</p>
          )}
          {t.note && <p className="mt-1 text-[11px] text-ink-3">{t.note}</p>}
        </div>
      ))}
    </section>
  )
}

function ChartHeader({ radar, category }: { radar: Radar; category: Category }) {
  const g = useForecastGap(radar.series)
  const gapUnits = radar.kpis.forecast_gap_units_21d || Math.round(g.gap)
  const pctText = g.pct > 0 ? `${Math.round(g.pct * 100)}%` : null
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 id="chart-title" className="display-tight text-lg text-ink">
          What sales say vs what customers asked for
        </h2>
        <p className="text-sm text-ink-3">{categoryLabel(category)} at {storeName(radar.store_id)}</p>
      </div>
      {gapUnits > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-marigold/60 bg-marigold-soft px-3 py-2">
          <span className="hatch h-8 w-3 shrink-0 rounded-sm" aria-hidden />
          <p className="text-sm leading-tight text-ink">
            <span className="figure text-xl text-marigold-ink">+{formatNumber(gapUnits)} units</span>
            <span className="block text-xs text-ink-2">
              customers asked for over the next 21 days{pctText ? `, ${pctText} above the sales-only forecast` : ''}
            </span>
          </p>
        </div>
      )}
    </div>
  )
}

function TopGaps({ radar, loading, failed }: { radar: Radar | null; loading: boolean; failed?: boolean }) {
  return (
    <section className="rounded-2xl border border-line bg-surface" aria-labelledby="gaps-title">
      <header className="px-4 pt-4 pb-2 @[560px]:px-5">
        <h2 id="gaps-title" className="display-tight text-lg text-ink">
          Top gaps
        </h2>
        <p className="text-xs text-ink-3">Items shoppers asked for in the last 7 days that the store couldn't sell, by value</p>
      </header>
      {loading ? (
        <div className="space-y-2 px-5 pb-5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : failed || !radar ? (
        <p className="px-5 pb-5 text-sm text-ink-3">Top gaps will appear when the radar loads.</p>
      ) : radar.top_gaps.length === 0 ? (
        <p className="px-5 pb-5 text-sm text-ink-3">No unmet demand in the last 7 days. Shoppers found what they asked for.</p>
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-line bg-surface-2 text-left text-xs text-ink-3">
                <th scope="col" className="py-2 pr-3 pl-4 font-medium @[560px]:pl-5">
                  Item
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Asked
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Value
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  On hand
                </th>
                <th scope="col" className="hidden py-2 pr-4 pl-3 font-medium @[560px]:table-cell @[560px]:pr-5">
                  Trend
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {radar.top_gaps.map((g, i) => (
                <tr key={`${g.sku ?? g.label}-${i}`}>
                  <td className="py-2.5 pr-3 pl-4 @[560px]:pl-5">
                    <p className="font-semibold text-ink">{g.label}</p>
                    <p className="text-xs text-ink-3">
                      {[g.sku, ...Object.values(g.attributes ?? {})].filter(Boolean).join(', ')}
                    </p>
                    <div className="mt-1 @[560px]:hidden">
                      <Trend t={g.trend} />
                    </div>
                  </td>
                  <td className="num px-3 py-2.5 text-right text-ink">{formatNumber(g.unmet_units_7d)}</td>
                  <td className="num px-3 py-2.5 text-right font-semibold text-ink">{formatINR(g.unmet_value_7d_inr)}</td>
                  <td className={cx('num px-3 py-2.5 text-right', g.on_hand === 0 ? 'font-semibold text-danger' : 'text-ink')}>{g.on_hand}</td>
                  <td className="hidden py-2.5 pr-4 pl-3 @[560px]:table-cell @[560px]:pr-5">
                    <Trend t={g.trend} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Trend({ t }: { t: 'rising' | 'flat' | 'falling' }) {
  if (t === 'rising')
    return (
      <Badge tone="maroon" icon={<ArrowUpRight className="size-3" aria-hidden />}>
        Rising
      </Badge>
    )
  if (t === 'falling')
    return (
      <Badge tone="leaf" icon={<ArrowDownRight className="size-3" aria-hidden />}>
        Easing
      </Badge>
    )
  return (
    <Badge tone="neutral" icon={<ArrowRight className="size-3" aria-hidden />}>
      Flat
    </Badge>
  )
}
