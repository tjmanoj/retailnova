const KEY = 'rn_mock'

/** Mock mode: VITE_MOCK=1 at build/dev time, or ?mock=1 in the URL (remembered for the tab). */
export function isMock(): boolean {
  if (import.meta.env.VITE_MOCK === '1') return true
  if (typeof window === 'undefined') return false
  try {
    const p = new URLSearchParams(window.location.search).get('mock')
    if (p === '1') sessionStorage.setItem(KEY, '1')
    if (p === '0') sessionStorage.removeItem(KEY)
    return sessionStorage.getItem(KEY) === '1'
  } catch {
    return new URLSearchParams(window.location.search).get('mock') === '1'
  }
}
