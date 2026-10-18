import { useState } from 'react'
import { Shirt, Sparkles, Gift, Footprints, Lamp } from 'lucide-react'
import { cx } from './ui'

const SWATCH: Record<string, string> = {
  maroon: '#7b1e2e',
  wine: '#6b1d2f',
  red: '#b3262e',
  pink: '#d4577b',
  peach: '#f1b49a',
  mustard: '#d39b14',
  yellow: '#e5b31b',
  gold: '#c9a227',
  orange: '#e0731c',
  green: '#1f6b46',
  'bottle green': '#14513a',
  teal: '#0e6e73',
  blue: '#2347a6',
  navy: '#1d2a5a',
  purple: '#5b2a7a',
  black: '#222',
  white: '#e9e5df',
  ivory: '#efe6d2',
  cream: '#efe6d2',
  silver: '#a9adb3',
  brown: '#7a4b2a',
  beige: '#d8c3a5',
  grey: '#8a8f96',
}

function CategoryIcon({ category, className }: { category?: string; className?: string }) {
  switch (category) {
    case 'home_decor':
      return <Lamp className={className} aria-hidden />
    case 'gifting':
      return <Gift className={className} aria-hidden />
    case 'footwear':
      return <Footprints className={className} aria-hidden />
    case 'sarees':
      return <Sparkles className={className} aria-hidden />
    default:
      return <Shirt className={className} aria-hidden />
  }
}

/** Product photo with a graceful colour-swatch fallback while catalog images are generated. */
export function ProductImage({
  src,
  alt,
  color,
  category,
  className,
}: {
  src: string
  alt: string
  color?: string
  category?: string
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  const swatch = SWATCH[(color ?? '').toLowerCase()] ?? '#8a817f'
  if (failed || !src) {
    return (
      <div
        role="img"
        aria-label={alt}
        className={cx('relative grid place-items-center overflow-hidden', className)}
        style={{ background: `linear-gradient(160deg, ${swatch} 0%, color-mix(in oklab, ${swatch} 70%, black) 100%)` }}
      >
        <div
          className="absolute inset-x-0 bottom-0 h-[14%]"
          style={{ background: 'repeating-linear-gradient(90deg, #d9a93b 0 6px, #b8862a 6px 9px)' }}
          aria-hidden
        />
        <CategoryIcon category={category} className="size-8 text-white/70" />
      </div>
    )
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={cx('object-cover', className)}
      style={{ backgroundColor: `color-mix(in oklab, ${swatch} 18%, var(--surface-2))` }}
    />
  )
}
