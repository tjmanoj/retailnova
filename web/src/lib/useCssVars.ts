import { useEffect, useState } from 'react'

function read(names: readonly string[]): Record<string, string> {
  const cs = getComputedStyle(document.documentElement)
  return Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(n).trim()]))
}

/** Resolve CSS custom properties to concrete colours (for SVG charts) and track theme changes. */
export function useCssVars<T extends readonly string[]>(names: T): Record<T[number], string> {
  const [vals, setVals] = useState(() => read(names))
  useEffect(() => {
    const update = () => setVals(read(names))
    const mo = new MutationObserver(update)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', update)
    return () => {
      mo.disconnect()
      mq.removeEventListener('change', update)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return vals as Record<T[number], string>
}
