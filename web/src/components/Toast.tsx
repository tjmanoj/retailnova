import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { BellRing, CheckCircle2, AlertTriangle, X } from 'lucide-react'
import { cx } from './ui'

type ToastTone = 'success' | 'info' | 'error' | 'notify'
export interface ToastItem {
  id: number
  title: string
  body?: string
  tone: ToastTone
  scope?: string
}

interface ToastApi {
  push: (t: Omit<ToastItem, 'id'>, ms?: number) => void
}

const Ctx = createContext<ToastApi>({ push: () => {} })

export function useToast() {
  return useContext(Ctx)
}

const icons: Record<ToastTone, ReactNode> = {
  success: <CheckCircle2 className="size-5 text-leaf" aria-hidden />,
  info: <CheckCircle2 className="size-5 text-peacock" aria-hidden />,
  error: <AlertTriangle className="size-5 text-danger" aria-hidden />,
  notify: <BellRing className="size-5 text-marigold-ink" aria-hidden />,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), [])
  const push = useCallback(
    (t: Omit<ToastItem, 'id'>, ms = 5000) => {
      const id = nextId.current++
      setItems((xs) => [...xs.slice(-3), { ...t, id }])
      window.setTimeout(() => dismiss(id), ms)
    },
    [dismiss],
  )
  const api = useMemo(() => ({ push }), [push])

  return (
    <Ctx.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 top-3 z-[60] flex flex-col items-center gap-2 px-4 sm:top-auto sm:right-5 sm:bottom-5 sm:left-auto sm:items-end"
        role="region"
        aria-label="Notifications"
        aria-live="polite"
      >
        {items.filter((t) => !t.scope).map((t) => (
          <ToastCard key={t.id} t={t} onClose={() => dismiss(t.id)} />
        ))}
      </div>
    </Ctx.Provider>
  )
}

export function ToastCard({ t, onClose }: { t: Omit<ToastItem, 'id'>; onClose: () => void }) {
  return (
    <div
      className={cx(
        'anim-toast pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl border bg-surface p-3.5 pr-2 shadow-float',
        t.tone === 'notify' ? 'border-marigold' : 'border-line',
      )}
      role="status"
    >
      <div className="mt-0.5">{icons[t.tone]}</div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink">{t.title}</p>
        {t.body && <p className="mt-0.5 text-sm text-ink-2">{t.body}</p>}
      </div>
      <button onClick={onClose} className="rounded-lg p-1 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Dismiss">
        <X className="size-4" aria-hidden />
      </button>
    </div>
  )
}
