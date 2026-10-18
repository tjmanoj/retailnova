import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ShopView } from '../features/shop/ShopView'

export default function ShopPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q')
  const consumed = useCallback(() => {
    const next = new URLSearchParams(params)
    next.delete('q')
    setParams(next, { replace: true })
  }, [params, setParams])
  return (
    <main id="main" className="min-h-0 flex-1">
      <h1 className="sr-only">Shopper concierge</h1>
      <ShopView initialPrompt={q} onConsumedPrompt={consumed} />
    </main>
  )
}
