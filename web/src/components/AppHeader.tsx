import { useEffect, useRef, useState } from 'react'
import { NavLink, Link } from 'react-router-dom'
import { Flame, Monitor, Moon, MoreHorizontal, RotateCcw, Sun } from 'lucide-react'
import { Button, SyntheticBadge, cx } from './ui'
import { useBootstrap } from '../lib/bootstrap'
import { api } from '../lib/api'
import { emit } from '../lib/bus'
import { getThemePref, setThemePref, type ThemePref } from '../lib/theme'
import { useToast } from './Toast'
import { isMock } from '../lib/mockMode'

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--maroon)" />
      <path d="M7 22 L13 16 L18 19 L25 10" fill="none" stroke="var(--marigold)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="25" cy="10" r="2.6" fill="var(--marigold)" />
    </svg>
  )
}

export function DiwaliChip({ className }: { className?: string }) {
  const b = useBootstrap()
  return (
    <span
      className={cx('inline-flex items-center gap-1.5 rounded-full bg-maroon-soft px-2.5 py-1 text-xs font-semibold text-maroon-ink', className)}
      title={`Diwali is on 8 November 2026. Demo date: 18 October 2026.`}
    >
      <Flame className="size-3.5 text-marigold" aria-hidden />
      <span className="num">{b.days_to_diwali}</span> days to Diwali
    </span>
  )
}

const NAV = [
  { to: '/live', label: 'Live loop' },
  { to: '/shop', label: 'Shopper' },
  { to: '/manager', label: 'Store manager' },
]

export function AppHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface/92 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="zari-rule" aria-hidden />
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5 rounded-lg" aria-label="RetailNova home">
          <BrandMark className="size-7" />
          <span className="flex flex-col leading-none">
            <span className="display-tight text-[19px] text-ink">RetailNova</span>
            <span className="mt-0.5 hidden text-[11px] font-medium text-ink-3 sm:block">for Nova Bazaar</span>
          </span>
        </Link>
        <nav aria-label="Main" className="ml-4 hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                cx(
                  'rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors',
                  isActive ? 'bg-surface-2 text-ink' : 'text-ink-2 hover:bg-surface-2 hover:text-ink',
                )
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden sm:block">
            <DiwaliChip />
          </span>
          {isMock() && (
            <span className="hidden rounded-md bg-surface-2 px-2 py-1 text-[11px] leading-none font-semibold text-ink-2 sm:inline" title="Answers come from local fixtures, not the live service">
              Mock mode
            </span>
          )}
          <SyntheticBadge />
          <HeaderMenu />
        </div>
      </div>
    </header>
  )
}

function HeaderMenu() {
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState<ThemePref>(getThemePref())
  const btn = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const [resetting, setResetting] = useState(false)
  const toast = useToast()

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!menu.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        btn.current?.focus()
      }
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    menu.current?.querySelector<HTMLElement>('a,button')?.focus()
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const chooseTheme = (t: ThemePref) => {
    setTheme(t)
    setThemePref(t)
  }

  const doReset = async () => {
    setResetting(true)
    try {
      await api.reset()
      emit('reset', null)
      toast.push({ tone: 'success', title: 'Demo reset', body: 'Inventory is restored and live signals, plans and notifications are cleared.' })
      dialog.current?.close()
    } catch (e) {
      toast.push({ tone: 'error', title: 'Reset failed', body: (e as Error).message })
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="relative">
      <button
        ref={btn}
        className="grid size-9 place-items-center rounded-xl text-ink-2 hover:bg-surface-2 hover:text-ink"
        aria-label="Menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <MoreHorizontal className="size-5" aria-hidden />
      </button>
      {open && (
        <div
          ref={menu}
          role="menu"
          className="anim-fade absolute top-11 right-0 z-50 w-64 rounded-2xl border border-line bg-surface p-2 shadow-float"
        >
          <div className="md:hidden">
            {NAV.map((n) => (
              <Link
                key={n.to}
                role="menuitem"
                to={n.to}
                onClick={() => setOpen(false)}
                className="block rounded-lg px-3 py-2 text-sm font-semibold text-ink hover:bg-surface-2"
              >
                {n.label}
              </Link>
            ))}
            <div className="my-2 h-px bg-line" />
          </div>
          <p className="px-3 pt-1 pb-1.5 text-xs font-medium text-ink-3">Theme</p>
          <div className="mx-1 grid grid-cols-3 gap-1 rounded-xl bg-surface-2 p-1" role="group" aria-label="Theme">
            {(
              [
                ['system', 'Auto', Monitor],
                ['light', 'Light', Sun],
                ['dark', 'Dark', Moon],
              ] as const
            ).map(([k, label, Icon]) => (
              <button
                key={k}
                role="menuitemradio"
                aria-checked={theme === k}
                onClick={() => chooseTheme(k)}
                className={cx(
                  'flex items-center justify-center gap-1 rounded-lg py-1.5 text-xs font-semibold',
                  theme === k ? 'bg-surface text-ink shadow-sm' : 'text-ink-2 hover:text-ink',
                )}
              >
                <Icon className="size-3.5" aria-hidden />
                {label}
              </button>
            ))}
          </div>
          <div className="my-2 h-px bg-line" />
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              dialog.current?.showModal()
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-semibold text-ink hover:bg-surface-2"
          >
            <RotateCcw className="size-4 text-ink-3" aria-hidden />
            Reset demo
          </button>
          {isMock() && <p className="px-3 pt-1 pb-1 text-xs text-ink-3">Mock mode: answers come from local fixtures.</p>}
        </div>
      )}

      <dialog
        ref={dialog}
        className="m-auto w-[min(92vw,420px)] rounded-2xl border border-line bg-surface p-0 text-ink shadow-float backdrop:bg-black/40"
        aria-labelledby="reset-title"
      >
        <div className="p-5">
          <h2 id="reset-title" className="display-tight text-xl">
            Reset the demo?
          </h2>
          <p className="mt-2 text-sm text-ink-2">
            This restores store inventory and clears live signals, plans, approvals, reservations and notifications for everyone using
            the demo. Simulated history stays.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => dialog.current?.close()}>
              Cancel
            </Button>
            <Button variant="primary" onClick={doReset} loading={resetting} icon={<RotateCcw className="size-4" aria-hidden />}>
              Reset demo
            </Button>
          </div>
        </div>
      </dialog>
    </div>
  )
}

export function Footer({ className }: { className?: string }) {
  return (
    <footer className={cx('border-t border-line', className)}>
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-2 px-4 py-5 text-xs text-ink-3 sm:px-6">
        <p>Demo data is synthetic. Nova Bazaar is a fictional retailer.</p>
        <p>Built on Google Cloud: Gemini, BigQuery TimesFM forecasts, Firestore, Cloud Run.</p>
      </div>
    </footer>
  )
}
