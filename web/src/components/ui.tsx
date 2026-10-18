import { forwardRef, type ButtonHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(' ')
}

type Variant = 'primary' | 'secondary' | 'ghost' | 'quiet' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const variants: Record<Variant, string> = {
  primary: 'bg-maroon text-on-maroon hover:bg-maroon-hover disabled:opacity-60',
  secondary: 'bg-surface text-ink border border-line-strong hover:border-ink-3 hover:bg-surface-2 disabled:opacity-60',
  ghost: 'text-ink-2 hover:text-ink hover:bg-surface-2 disabled:opacity-50',
  quiet: 'bg-surface-2 text-ink hover:bg-surface-3 disabled:opacity-60',
  danger: 'bg-danger text-white hover:opacity-90 disabled:opacity-60',
}
const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-[13px] gap-1.5 rounded-lg',
  md: 'h-10 px-4 text-sm gap-2 rounded-xl',
  lg: 'h-12 px-5 text-[15px] gap-2 rounded-xl',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cx(
        'inline-flex shrink-0 items-center justify-center font-semibold whitespace-nowrap transition-colors duration-150 select-none disabled:cursor-not-allowed',
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
})

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx('animate-spin', className ?? 'size-4')} aria-hidden />
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('skeleton', className)} aria-hidden />
}

type Tone = 'neutral' | 'maroon' | 'marigold' | 'peacock' | 'leaf' | 'danger'
const tones: Record<Tone, string> = {
  neutral: 'bg-surface-2 text-ink-2',
  maroon: 'bg-maroon-soft text-maroon-ink',
  marigold: 'bg-marigold-soft text-marigold-ink',
  peacock: 'bg-peacock-soft text-peacock',
  leaf: 'bg-leaf-soft text-leaf',
  danger: 'bg-danger-soft text-danger',
}

export function Badge({ tone = 'neutral', children, className, icon }: { tone?: Tone; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap', tones[tone], className)}>
      {icon}
      {children}
    </span>
  )
}

export function Select({
  label,
  className,
  children,
  hideLabel,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hideLabel?: boolean }) {
  return (
    <label className={cx('relative inline-flex flex-col gap-1', className)}>
      <span className={cx('text-xs font-medium text-ink-3', hideLabel && 'sr-only')}>{label}</span>
      <span className="relative">
        <select
          className="h-10 w-full appearance-none rounded-xl border border-line-strong bg-surface pr-9 pl-3 text-sm font-semibold text-ink hover:border-ink-3"
          {...rest}
        >
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
      </span>
    </label>
  )
}

export function Panel({ className, children, as: As = 'section', ...rest }: { className?: string; children: ReactNode; as?: 'section' | 'div' | 'aside' } & Record<string, unknown>) {
  return (
    <As className={cx('rounded-2xl border border-line bg-surface', className)} {...rest}>
      {children}
    </As>
  )
}

export function SyntheticBadge({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-md border border-marigold/60 bg-marigold-soft px-2 py-1 text-[11px] leading-none font-bold tracking-wide whitespace-nowrap text-marigold-ink',
        className,
      )}
      title="All data in this demo is synthetic. Nova Bazaar is a fictional retailer."
    >
      <span className="size-1.5 rounded-full bg-marigold" aria-hidden />
      SYNTHETIC DATA
    </span>
  )
}
