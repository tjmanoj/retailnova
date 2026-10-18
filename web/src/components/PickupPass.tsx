import { useEffect, useRef, useState } from 'react'
import { Maximize2, QrCode, Store as StoreIcon, X } from 'lucide-react'
import { storeName } from '../lib/constants'
import { cx } from './ui'

/** Lazily renders a QR code as crisp SVG modules (qrcode-generator is loaded on demand). */
export function QR({ value, size = 112, className }: { value: string; size?: number; className?: string }) {
  const [cells, setCells] = useState<boolean[][] | null>(null)
  useEffect(() => {
    let alive = true
    import('qrcode-generator')
      .then((mod) => {
        const factory = ((mod as unknown as { default?: unknown }).default ?? mod) as (
          t: number,
          e: 'L' | 'M' | 'Q' | 'H',
        ) => { addData: (d: string) => void; make: () => void; getModuleCount: () => number; isDark: (r: number, c: number) => boolean }
        const qr = factory(0, 'M')
        qr.addData(value)
        qr.make()
        const n = qr.getModuleCount()
        const grid = Array.from({ length: n }, (_, r) => Array.from({ length: n }, (_, c) => qr.isDark(r, c)))
        if (alive) setCells(grid)
      })
      .catch(() => alive && setCells(null))
    return () => {
      alive = false
    }
  }, [value])

  if (!cells) {
    return (
      <div className={cx('grid place-items-center rounded-lg bg-white', className)} style={{ width: size, height: size }} aria-hidden>
        <QrCode className="size-8 text-[#8a817f]" />
      </div>
    )
  }
  const n = cells.length
  const q = 2 // quiet zone in modules
  let d = ''
  cells.forEach((row, r) =>
    row.forEach((dark, c) => {
      if (dark) d += `M${c + q} ${r + q}h1v1h-1z`
    }),
  )
  return (
    <svg
      viewBox={`0 0 ${n + q * 2} ${n + q * 2}`}
      width={size}
      height={size}
      className={cx('rounded-lg bg-white', className)}
      shapeRendering="crispEdges"
      role="img"
      aria-label="Pickup QR code"
    >
      <rect width="100%" height="100%" fill="#fff" />
      <path d={d} fill="#1f1a1a" />
    </svg>
  )
}

const holdFmt = new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

export interface PassData {
  ref: string // reservation id (or notification id when that's all we have)
  storeId: string
  sku: string
  productName?: string
  holdUntil?: string | null
}

function passPayload(p: PassData) {
  return JSON.stringify({ t: 'nova-pickup', r: p.ref, s: p.storeId, k: p.sku })
}

function shortRef(ref: string) {
  return ref.replace(/^[a-z]+[_-]/i, '').slice(-6).toUpperCase()
}

/** Pickup pass: QR with the reservation id and store, the counter to visit, and the hold time. */
export function PickupPass({ data, compact = false }: { data: PassData; compact?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const store = storeName(data.storeId)
  const hold = data.holdUntil ? new Date(data.holdUntil) : null
  const holdText = hold && !Number.isNaN(hold.getTime()) ? holdFmt.format(hold) : null

  const body = (big: boolean) => (
    <div className={cx('flex gap-3', big ? 'flex-col items-center text-center' : 'items-center')}>
      <QR value={passPayload(data)} size={big ? 220 : 76} className="shrink-0 ring-1 ring-line" />
      <div className="min-w-0">
        <p className={cx('font-semibold text-ink', big ? 'text-lg' : 'text-[13px] leading-snug')}>Show this at the {store} counter</p>
        {holdText && <p className={cx('text-ink-2', big ? 'mt-1 text-sm' : 'text-[11px]')}>Held until {holdText}</p>}
        <p className={cx('num text-ink-3', big ? 'mt-1 text-sm' : 'text-[11px]')}>Ref {shortRef(data.ref)}</p>
      </div>
    </div>
  )

  return (
    <>
      <div className={cx('anim-slide-down rounded-xl border border-dashed border-leaf/60 bg-surface p-2.5', compact && 'p-2')} data-demo="pass">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-leaf">
            <StoreIcon className="size-3.5" aria-hidden /> Pickup pass
          </span>
          <button
            type="button"
            onClick={() => dialog.current?.showModal()}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-ink-2 hover:bg-surface-2 hover:text-ink"
          >
            <Maximize2 className="size-3" aria-hidden /> Open
          </button>
        </div>
        {body(false)}
      </div>
      <dialog
        ref={dialog}
        className="m-auto w-[min(92vw,380px)] rounded-3xl border border-line bg-surface p-0 text-ink shadow-float backdrop:bg-black/50"
        aria-label="Pickup pass"
        onClick={(e) => e.target === dialog.current && dialog.current?.close()}
      >
        <div className="relative p-6">
          <button
            onClick={() => dialog.current?.close()}
            className="absolute top-3 right-3 rounded-lg p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink"
            aria-label="Close pickup pass"
          >
            <X className="size-5" aria-hidden />
          </button>
          <p className="text-sm font-semibold text-maroon-ink">Nova Bazaar pickup pass</p>
          {data.productName && <p className="display-tight mt-1 mb-4 text-xl text-ink">{data.productName}</p>}
          {body(true)}
        </div>
      </dialog>
    </>
  )
}
