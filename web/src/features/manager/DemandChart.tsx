import { useMemo } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { RadarPoint } from '../../types'
import { useCssVars } from '../../lib/useCssVars'
import { formatNumber, shortDate } from '../../lib/format'
import { DEMO_TODAY, DIWALI_DATE } from '../../lib/constants'

type Row = RadarPoint & { band: [number, number] | null; gap: [number, number] | null }

const VARS = ['--maroon', '--marigold', '--marigold-ink', '--chart-sales', '--chart-actual', '--chart-unmet', '--chart-sensed', '--line', '--ink-3', '--surface'] as const

export function useForecastGap(series: RadarPoint[], days = 21) {
  return useMemo(() => {
    const future = series.filter((p) => p.date >= DEMO_TODAY && p.forecast_sales_only != null && p.forecast_demand_sensed != null).slice(0, days)
    const sales = future.reduce((a, p) => a + (p.forecast_sales_only ?? 0), 0)
    const sensed = future.reduce((a, p) => a + (p.forecast_demand_sensed ?? 0), 0)
    return { sales, sensed, gap: sensed - sales, pct: sales > 0 ? (sensed - sales) / sales : 0 }
  }, [series, days])
}

export function DemandChart({ series, height = 320 }: { series: RadarPoint[]; height?: number }) {
  const c = useCssVars(VARS)
  const rows: Row[] = useMemo(
    () =>
      series.map((p) => ({
        ...p,
        band: p.lower != null && p.upper != null ? [p.lower, p.upper] : null,
        gap:
          p.forecast_sales_only != null && p.forecast_demand_sensed != null
            ? [Math.min(p.forecast_sales_only, p.forecast_demand_sensed), Math.max(p.forecast_sales_only, p.forecast_demand_sensed)]
            : null,
      })),
    [series],
  )
  const hasDiwali = rows.some((r) => r.date === DIWALI_DATE)
  const hasToday = rows.some((r) => r.date === DEMO_TODAY)

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 22, right: 8, bottom: 0, left: -14 }}>
          <defs>
            <pattern id="rn-gap-hatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
              <rect width="6" height="6" fill={c['--marigold']} fillOpacity={0.22} />
              <line x1="0" y1="0" x2="0" y2="6" stroke={c['--marigold']} strokeWidth={2.4} strokeOpacity={0.75} />
            </pattern>
          </defs>
          <CartesianGrid vertical={false} stroke={c['--line']} />
          <XAxis
            dataKey="date"
            tickFormatter={(d: string) => shortDate(d)}
            minTickGap={36}
            tickLine={false}
            axisLine={{ stroke: c['--line'] }}
            tickMargin={8}
          />
          <YAxis tickLine={false} axisLine={false} width={44} allowDecimals={false} tickFormatter={(v: number) => formatNumber(v)} />
          <Tooltip content={(props) => <ChartTooltip active={props.active} payload={props.payload as unknown as { payload: Row }[]} label={props.label} />} cursor={{ stroke: c['--ink-3'], strokeDasharray: '3 3' }} />
          <Area dataKey="band" type="monotone" stroke="none" fill={c['--maroon']} fillOpacity={0.08} isAnimationActive={false} activeDot={false} />
          <Area dataKey="gap" type="monotone" stroke="none" fill="url(#rn-gap-hatch)" isAnimationActive animationDuration={900} activeDot={false} />
          <Bar dataKey="unmet_units" fill={c['--chart-unmet']} fillOpacity={0.5} barSize={4} radius={[2, 2, 0, 0]} isAnimationActive={false} />
          <Line dataKey="actual_units" type="monotone" stroke={c['--chart-actual']} strokeWidth={1.75} dot={false} isAnimationActive={false} />
          <Line dataKey="forecast_sales_only" type="monotone" stroke={c['--chart-sales']} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} />
          <Line dataKey="forecast_demand_sensed" type="monotone" stroke={c['--chart-sensed']} strokeWidth={2.75} dot={false} isAnimationActive={false} />
          {hasToday && (
            <ReferenceLine
              x={DEMO_TODAY}
              stroke={c['--ink-3']}
              strokeDasharray="2 3"
              label={{ value: 'Today', position: 'top', fill: c['--ink-3'], fontSize: 11, fontWeight: 600 }}
            />
          )}
          {hasDiwali && (
            <ReferenceLine
              x={DIWALI_DATE}
              stroke={c['--marigold']}
              strokeWidth={2}
              label={{ value: 'Diwali', position: 'top', fill: c['--marigold-ink'], fontSize: 12, fontWeight: 700 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: Row }[]; label?: string | number }) {
  if (!active || !payload?.length) return null
  const p = payload[0]?.payload
  if (!p) return null
  const rows: [string, string, string][] = []
  if (p.actual_units != null) rows.push(['Actual sales', formatNumber(p.actual_units), 'var(--chart-actual)'])
  if (p.unmet_units != null) rows.push(['Unmet asks', formatNumber(p.unmet_units), 'var(--chart-unmet)'])
  if (p.forecast_sales_only != null) rows.push(['Sales-only forecast', p.forecast_sales_only.toFixed(1), 'var(--chart-sales)'])
  if (p.forecast_demand_sensed != null) rows.push(['Demand-sensed forecast', p.forecast_demand_sensed.toFixed(1), 'var(--chart-sensed)'])
  if (p.forecast_sales_only != null && p.forecast_demand_sensed != null)
    rows.push(['Gap', `+${(p.forecast_demand_sensed - p.forecast_sales_only).toFixed(1)}`, 'var(--marigold)'])
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-float">
      <p className="mb-1 font-semibold text-ink">
        {shortDate(String(label))}
        {String(label) === DIWALI_DATE ? ', Diwali' : ''}
      </p>
      <table>
        <tbody>
          {rows.map(([k, v, col]) => (
            <tr key={k}>
              <td className="py-0.5 pr-3 text-ink-2">
                <span className="mr-1.5 inline-block size-2 rounded-full align-middle" style={{ background: col }} />
                {k}
              </td>
              <td className="num text-right font-semibold text-ink">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[11px] text-ink-3">Units per day</p>
    </div>
  )
}

export function ChartLegend() {
  const item = 'inline-flex items-center gap-1.5'
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2" aria-label="Chart legend">
      <li className={item}>
        <span className="h-[2px] w-5 bg-ink" aria-hidden /> Actual sales
      </li>
      <li className={item}>
        <span className="w-5 border-t-2 border-dashed border-ink-3" aria-hidden /> Sales-only forecast
      </li>
      <li className={item}>
        <span className="h-[3px] w-5 rounded bg-[var(--chart-sensed)]" aria-hidden /> Demand-sensed forecast
      </li>
      <li className={item}>
        <span className="hatch h-3 w-5 rounded-sm" aria-hidden /> Demand sales data misses
      </li>
      <li className={item}>
        <span className="h-3 w-1.5 rounded-sm bg-maroon/50" aria-hidden /> Unmet asks per day
      </li>
      <li className={item}>
        <span className="h-3 w-5 rounded-sm bg-maroon/10" aria-hidden /> 90% range
      </li>
    </ul>
  )
}
