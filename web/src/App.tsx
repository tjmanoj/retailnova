import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Route, Routes, useLocation, Link } from 'react-router-dom'
import { AppHeader } from './components/AppHeader'
import { ToastProvider } from './components/Toast'
import { BootstrapProvider } from './lib/bootstrap'
import { Spinner, cx } from './components/ui'
import Landing from './pages/Landing'

const ShopPage = lazy(() => import('./pages/ShopPage'))
const ManagerPage = lazy(() => import('./pages/ManagerPage'))
const LivePage = lazy(() => import('./pages/LivePage'))

function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const fixed = pathname.startsWith('/shop') || pathname.startsWith('/live')
  return (
    <div className={cx('flex flex-col', fixed ? 'h-dvh overflow-hidden' : 'min-h-dvh')}>
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-surface px-3 py-2 text-sm font-semibold text-ink focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <AppHeader />
      <Suspense
        fallback={
          <div className="grid flex-1 place-items-center py-24 text-ink-3" role="status">
            <Spinner className="size-6" />
            <span className="sr-only">Loading</span>
          </div>
        }
      >
        {children}
      </Suspense>
    </div>
  )
}

function NotFound() {
  return (
    <main id="main" className="mx-auto max-w-xl px-6 py-24 text-center">
      <h1 className="display text-5xl text-ink">Page not found</h1>
      <p className="mt-3 text-ink-2">That page doesn't exist. Start from the overview instead.</p>
      <Link to="/" className="mt-6 inline-flex h-11 items-center rounded-xl bg-maroon px-5 font-semibold text-on-maroon">
        Go to the overview
      </Link>
    </main>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <BootstrapProvider>
        <ToastProvider>
          <Shell>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/shop" element={<ShopPage />} />
              <Route path="/manager" element={<ManagerPage />} />
              <Route path="/live" element={<LivePage />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Shell>
        </ToastProvider>
      </BootstrapProvider>
    </BrowserRouter>
  )
}
