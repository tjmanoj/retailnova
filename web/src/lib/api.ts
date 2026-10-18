import type {
  ApproveResponse,
  AskRequest,
  Bootstrap,
  ChatRequest,
  HealthResponse,
  ItemRequest,
  Notification,
  NotifyResponse,
  PlanRequest,
  Radar,
  RejectResponse,
  ReserveResponse,
  ResetResponse,
  SSEEvent,
  ApiErrorBody,
} from '../types'
import { isMock } from './mockMode'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

const loadMocks = () => import('../mocks')

/**
 * Origin for the three streaming routes (/api/chat, /api/plan, /api/ask). Firebase Hosting buffers
 * streamed responses, so production calls Cloud Run directly (CORS enabled there). Empty means same
 * origin, which keeps local dev on the Vite proxy. Every JSON route always stays same-origin.
 */
export const STREAM_BASE = ((import.meta.env.VITE_STREAM_BASE as string | undefined) ?? '').replace(/\/$/, '')

function friendlyStatus(status: number, fallback: string): string {
  if (status === 429) return 'That was a lot of requests in a short time. Wait a minute, then try again.'
  if (status === 413) return 'That message or photo is too large. Keep photos under 1.5 MB and messages under 1,000 characters.'
  if (status >= 500) return 'The service hit a problem. Try again in a moment.'
  return fallback
}

async function readError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`
  let message = res.statusText || 'Request failed'
  try {
    const body = (await res.json()) as Partial<ApiErrorBody>
    if (body?.error) {
      code = body.error.code || code
      message = body.error.message || message
    }
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, code, friendlyStatus(res.status, message))
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  if (isMock()) {
    const m = await loadMocks()
    return m.mockRequest<T>(method, path, body)
  }
  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'network', 'Could not reach RetailNova. Check your connection and try again.')
  }
  if (!res.ok) throw await readError(res)
  return (await res.json()) as T
}

export type SSEHandler = (e: SSEEvent) => void

/**
 * POST a JSON body and read a text/event-stream response.
 * Parses `event:` / `data:` frames from the fetch ReadableStream and calls onEvent for each.
 * HTTP and network failures are delivered as an `error` event followed by `done`, so callers
 * handle every failure in one place.
 */
export async function streamSSE(path: string, body: unknown, onEvent: SSEHandler, signal?: AbortSignal): Promise<void> {
  if (isMock()) {
    const m = await loadMocks()
    return m.mockStream(path, body, onEvent, signal)
  }
  const fail = (message: string, retryable = true) => {
    onEvent({ event: 'error', data: { message, retryable } })
    onEvent({ event: 'done', data: { latency_ms: 0, model: '' } })
  }

  let res: Response
  try {
    res = await fetch(STREAM_BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') return
    return fail('Could not reach RetailNova. Check your connection and try again.')
  }
  if (!res.ok || !res.body) {
    const e = await readError(res)
    return fail(e.message, res.status === 429 || res.status >= 500)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sawDone = false

  const dispatch = (frame: string) => {
    let name = 'message'
    const data: string[] = []
    for (const raw of frame.split('\n')) {
      const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw
      if (!line || line.startsWith(':')) continue
      const idx = line.indexOf(':')
      const field = idx === -1 ? line : line.slice(0, idx)
      let value = idx === -1 ? '' : line.slice(idx + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') name = value
      else if (field === 'data') data.push(value)
    }
    if (!data.length) return
    let payload: unknown
    try {
      payload = JSON.parse(data.join('\n'))
    } catch {
      return
    }
    if (name === 'done') sawDone = true
    onEvent({ event: name, data: payload } as SSEEvent)
  }

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let sep = buffer.indexOf('\n\n')
      while (sep !== -1) {
        dispatch(buffer.slice(0, sep))
        buffer = buffer.slice(sep + 2)
        sep = buffer.indexOf('\n\n')
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) dispatch(buffer)
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') return
    return fail('The connection dropped before the answer finished. Try again.')
  }
  if (!sawDone) onEvent({ event: 'done', data: { latency_ms: 0, model: '' } })
}

export const api = {
  health: () => request<HealthResponse>('GET', '/api/health'),
  /** Wake the streaming origin too (a no-op when it is the same origin). */
  warmStream: async () => {
    if (!STREAM_BASE || isMock()) return
    try {
      await fetch(`${STREAM_BASE}/api/health`, { mode: 'cors' })
    } catch {
      /* best effort */
    }
  },
  bootstrap: () => request<Bootstrap>('GET', '/api/bootstrap'),
  notify: (b: ItemRequest) => request<NotifyResponse>('POST', '/api/notify', b),
  reserve: (b: ItemRequest) => request<ReserveResponse>('POST', '/api/reserve', b),
  notifications: (sessionId: string) =>
    request<{ items: Notification[] }>('GET', `/api/notifications?session_id=${encodeURIComponent(sessionId)}`),
  radar: (storeId: string, category?: string) =>
    request<Radar>(
      'GET',
      `/api/radar?store_id=${encodeURIComponent(storeId)}${category ? `&category=${encodeURIComponent(category)}` : ''}`,
    ),
  approve: (actionId: string) => request<ApproveResponse>('POST', `/api/actions/${encodeURIComponent(actionId)}/approve`),
  reject: (actionId: string) => request<RejectResponse>('POST', `/api/actions/${encodeURIComponent(actionId)}/reject`),
  reset: () => request<ResetResponse>('POST', '/api/demo/reset'),
  chat: (b: ChatRequest, onEvent: SSEHandler, signal?: AbortSignal) => streamSSE('/api/chat', b, onEvent, signal),
  plan: (b: PlanRequest, onEvent: SSEHandler, signal?: AbortSignal) => streamSSE('/api/plan', b, onEvent, signal),
  ask: (b: AskRequest, onEvent: SSEHandler, signal?: AbortSignal) => streamSSE('/api/ask', b, onEvent, signal),
}
