const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const num = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const rtf = new Intl.RelativeTimeFormat('en-IN', { numeric: 'auto', style: 'short' })

export function formatINR(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return inr.format(Math.round(n))
}

/** Compact Indian notation for tight spaces: ₹4.8K, ₹1.2L, ₹3.4Cr */
export function formatINRCompact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  const a = Math.abs(n)
  if (a >= 1e7) return `₹${trim(n / 1e7)}Cr`
  if (a >= 1e5) return `₹${trim(n / 1e5)}L`
  if (a >= 1e3) return `₹${trim(n / 1e3)}K`
  return inr.format(n)
}

function trim(x: number): string {
  return x >= 100 ? x.toFixed(0) : x.toFixed(1).replace(/\.0$/, '')
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return num.format(n)
}

export function discountPct(price: number, mrp: number): number {
  if (!mrp || mrp <= price) return 0
  return Math.round(((mrp - price) / mrp) * 100)
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const s = Math.round((t - now) / 1000)
  const a = Math.abs(s)
  if (a < 45) return 'just now'
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute')
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour')
  return rtf.format(Math.round(s / 86400), 'day')
}

const dShort = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const dLong = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const tShort = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit' })

/** "12 Oct" from YYYY-MM-DD */
export function shortDate(ymd: string): string {
  const d = new Date(`${ymd.slice(0, 10)}T00:00:00Z`)
  return Number.isNaN(d.getTime()) ? ymd : dShort.format(d)
}

export function longDate(ymd: string): string {
  const d = new Date(`${ymd.slice(0, 10)}T00:00:00Z`)
  return Number.isNaN(d.getTime()) ? ymd : dLong.format(d)
}

export function clockTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : tShort.format(d)
}

export function daysBetween(fromYmd: string, toYmd: string): number {
  const a = new Date(`${fromYmd.slice(0, 10)}T00:00:00Z`).getTime()
  const b = new Date(`${toYmd.slice(0, 10)}T00:00:00Z`).getTime()
  return Math.round((b - a) / 86400000)
}

export function sizeLabel(size: string): string {
  return size === 'FREE' ? 'Free size' : size
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`
}
