const KEY = 'rn_session'

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

let cached: string | null = null

/** Browser session id shared by every view (the Live Loop uses the same id for both panes). */
export function getSessionId(): string {
  if (cached) return cached
  try {
    const existing = localStorage.getItem(KEY)
    if (existing) return (cached = existing)
    const id = uuid()
    localStorage.setItem(KEY, id)
    return (cached = id)
  } catch {
    return (cached = uuid())
  }
}
