import { Check } from 'lucide-react'
import { Spinner, cx } from './ui'

export interface ActivityState {
  id: string
  tool: string
  label: string
  status: 'start' | 'end'
}

/** Live tool-activity chips: spinner while running, check when done. */
export function ActivityChips({ items, className }: { items: ActivityState[]; className?: string }) {
  if (!items.length) return null
  return (
    <ul className={cx('flex flex-wrap gap-1.5', className)} aria-label="What the assistant is doing">
      {items.map((a) => (
        <li
          key={a.id}
          className={cx(
            'anim-fade inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
            a.status === 'start' ? 'border-marigold/70 bg-marigold-soft text-marigold-ink' : 'border-line bg-surface text-ink-3',
          )}
        >
          {a.status === 'start' ? <Spinner className="size-3" /> : <Check className="size-3 text-leaf" aria-hidden />}
          <span>
            {a.label}
            {a.status === 'start' ? '…' : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}
