import { useMemo, useState } from 'react'
import { BellPlus, Check, MapPin, PackageCheck, ShoppingBag, Truck } from 'lucide-react'
import type { Notification, ProductCard as Product } from '../../types'
import { ProductImage } from '../../components/ProductImage'
import { Badge, Button, cx } from '../../components/ui'
import { discountPct, formatINR, sizeLabel } from '../../lib/format'
import { storeName } from '../../lib/constants'
import { api } from '../../lib/api'
import { getSessionId } from '../../lib/session'

type Done = { kind: 'notify' | 'reserve'; message: string; store: string }

export function ProductCard({ p, onDone, alert }: { p: Product; onDone?: (d: Done) => void; alert?: Notification }) {
  const here = p.availability.find((a) => a.store_id === p.requested_store_id)
  const herePhysical = p.requested_store_id !== 'ONLINE'
  const freeOnly = p.sizes.length === 1 && p.sizes[0] === 'FREE'
  const [size, setSize] = useState<string>(() => here?.sizes_in_stock[0] ?? p.sizes[0] ?? 'FREE')
  const [busy, setBusy] = useState<'notify' | 'reserve' | null>(null)
  const [done, setDone] = useState<Done | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const sizeHere = Boolean(here?.sizes_in_stock.includes(size))

  // Best other physical store that has the chosen size, for pickup.
  const elsewhere = useMemo(
    () =>
      p.availability
        .filter((a) => a.store_id !== p.requested_store_id && a.store_id !== 'ONLINE' && a.sizes_in_stock.includes(size))
        .sort((a, b) => b.on_hand - a.on_hand),
    [p.availability, p.requested_store_id, size],
  )
  const others = useMemo(
    () => p.availability.filter((a) => a.store_id !== p.requested_store_id && a.on_hand > 0).sort((a, b) => b.on_hand - a.on_hand),
    [p.availability, p.requested_store_id],
  )

  const hereName = storeName(p.requested_store_id)
  const off = discountPct(p.price_inr, p.mrp_inr)

  const act = async (kind: 'notify' | 'reserve', storeId: string) => {
    setBusy(kind)
    setErr(null)
    try {
      const body = { session_id: getSessionId(), sku: p.sku, size, store_id: storeId }
      const res = kind === 'notify' ? await api.notify(body) : await api.reserve(body)
      const d: Done = { kind, message: res.message, store: storeId }
      setDone(d)
      onDone?.(d)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const badge = (() => {
    if (alert)
      return alert.kind === 'transfer_eta' ? (
        <Badge tone="peacock" icon={<Truck className="size-3" aria-hidden />}>
          On its way
        </Badge>
      ) : (
        <Badge tone="leaf" icon={<PackageCheck className="size-3" aria-hidden />}>
          {alert.kind === 'reserved' ? 'Reserved for you' : 'Back in stock'}
        </Badge>
      )
    switch (p.badge) {
      case 'in_stock':
        return <Badge tone="leaf">In stock at {hereName}</Badge>
      case 'low':
        return <Badge tone="marigold">Only {p.requested_store_on_hand} left at {hereName}</Badge>
      case 'other_store': {
        const physical = others.find((o) => o.store_id !== 'ONLINE')
        return (
          <Badge tone="peacock" icon={<MapPin className="size-3" aria-hidden />}>
            {physical ? `At ${physical.store_name}` : others[0] ? 'Available online' : 'At another store'}
          </Badge>
        )
      }
      default:
        return <Badge tone="danger">Out of stock</Badge>
    }
  })()

  return (
    <article className="flex w-[244px] shrink-0 snap-start flex-col overflow-hidden rounded-2xl border border-line bg-surface @[640px]:w-auto">
      <div className="relative">
        <ProductImage src={p.image_url} alt={p.image_alt} color={p.color} category={p.category} className="aspect-square w-full" />
        <div className="absolute top-2 left-2 max-w-[calc(100%-1rem)] [&>span]:shadow-sm">{badge}</div>
      </div>
      <div className="flex flex-1 flex-col gap-2.5 p-3">
        <div>
          <h2 className="line-clamp-2 text-[15px] leading-snug font-semibold text-ink">{p.name}</h2>
          <p className="mt-1 flex flex-wrap items-baseline gap-x-2">
            <span className="figure text-lg text-ink">{formatINR(p.price_inr)}</span>
            {p.mrp_inr > p.price_inr && (
              <>
                <s className="num text-sm text-ink-3">
                  <span className="sr-only">MRP </span>
                  {formatINR(p.mrp_inr)}
                </s>
                <span className="text-xs font-semibold text-leaf">{off}% off</span>
              </>
            )}
          </p>
          {p.reason && <p className="mt-1 line-clamp-2 text-xs text-ink-3">{p.reason}</p>}
        </div>

        <div className="rounded-xl bg-surface-2 px-2.5 py-2 text-xs">
        <dl className="space-y-1">
          <div className="flex items-center justify-between gap-2">
            <dt className="font-semibold text-ink">{hereName}</dt>
            <dd className={cx('num font-semibold', p.requested_store_on_hand > 0 ? 'text-leaf' : 'text-danger')}>
              {p.requested_store_on_hand > 0 ? `${p.requested_store_on_hand} in stock` : 'Sold out'}
            </dd>
          </div>
          {others.slice(0, 2).map((o) => (
            <div key={o.store_id} className="flex items-center justify-between gap-2 text-ink-2">
              <dt>{o.store_name}</dt>
              <dd className="num">{o.on_hand}</dd>
            </div>
          ))}
        </dl>
          {others.length > 2 && <p className="mt-1 text-ink-3">+{others.length - 2} more stores</p>}
        </div>

        {!freeOnly && (
          <fieldset>
            <legend className="mb-1 text-xs font-medium text-ink-3">Size</legend>
            <div className="flex flex-wrap gap-1">
              {p.sizes.map((s) => {
                const inHere = here?.sizes_in_stock.includes(s)
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSize(s)}
                    aria-pressed={size === s}
                    aria-label={`Size ${s}${inHere ? '' : `, not in stock at ${hereName}`}`}
                    className={cx(
                      'h-7 min-w-8 rounded-lg border px-2 text-xs font-semibold',
                      size === s ? 'border-ink bg-ink text-surface' : 'border-line-strong text-ink hover:border-ink-3',
                      !inHere && size !== s && 'text-ink-3 line-through decoration-1',
                    )}
                  >
                    {sizeLabel(s)}
                  </button>
                )
              })}
            </div>
          </fieldset>
        )}

        <div className="mt-auto pt-1" aria-live="polite">
          {alert ? (
            alert.kind === 'transfer_eta' ? (
              <div className="anim-slide-down rounded-xl border border-peacock/40 bg-peacock-soft px-2.5 py-2 text-xs text-peacock">
                <p className="flex items-center gap-1.5 text-[13px] font-semibold">
                  <Truck className="size-4 shrink-0" aria-hidden />
                  On its way to {storeName(alert.store_id)}
                </p>
                <p className="mt-1 text-ink-2">{alert.message}</p>
              </div>
            ) : (
              <div className="anim-slide-down rounded-xl border border-leaf/40 bg-leaf-soft px-2.5 py-2 text-xs text-leaf">
                <p className="flex items-center gap-1.5 text-[13px] font-semibold">
                  <PackageCheck className="size-4 shrink-0" aria-hidden />
                  {alert.kind === 'reserved' ? `Reserved for you at ${storeName(alert.store_id)}` : `Back at ${storeName(alert.store_id)}`}
                </p>
                <p className="mt-1 text-ink-2">{alert.message}</p>
              </div>
            )
          ) : done ? (
            <p className="anim-fade flex items-start gap-2 rounded-xl bg-leaf-soft px-2.5 py-2 text-xs font-medium text-leaf">
              <Check className="mt-px size-3.5 shrink-0" aria-hidden />
              <span>{done.message}</span>
            </p>
          ) : sizeHere && herePhysical ? (
            <Button
              variant="primary"
              size="md"
              className="w-full"
              loading={busy === 'reserve'}
              icon={<ShoppingBag className="size-4" aria-hidden />}
              onClick={() => act('reserve', p.requested_store_id)}
            >
              Reserve for pickup
            </Button>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Button
                variant="primary"
                size="md"
                className="w-full"
                loading={busy === 'notify'}
                icon={<BellPlus className="size-4" aria-hidden />}
                onClick={() => act('notify', p.requested_store_id)}
              >
                Notify me
              </Button>
              {elsewhere[0] && (
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full"
                  loading={busy === 'reserve'}
                  onClick={() => act('reserve', elsewhere[0].store_id)}
                >
                  Reserve at {elsewhere[0].store_name}
                </Button>
              )}
            </div>
          )}
          {err && <p className="mt-1.5 text-xs text-danger">{err}</p>}
          {!done && !alert && !sizeHere && (
            <p className="mt-1.5 text-[11px] text-ink-3">
              {freeOnly ? `We'll alert you when it's back at ${hereName}.` : `Size ${sizeLabel(size)} isn't at ${hereName} yet. We'll alert you.`}
            </p>
          )}
        </div>
      </div>
    </article>
  )
}
