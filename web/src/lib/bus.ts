import type { DemandSignal, Notification } from '../types'

/** In-tab event bus: lets the shopper and manager panes react to each other instantly. */
export type LoopStep = 'ask' | 'signal' | 'plan' | 'approve' | 'notify'

type BusEvents = {
  step: LoopStep
  signal: DemandSignal
  notification: Notification
  reset: null
}

type Handler<T> = (payload: T) => void
const handlers = new Map<keyof BusEvents, Set<Handler<never>>>()

export function on<K extends keyof BusEvents>(name: K, h: Handler<BusEvents[K]>): () => void {
  let set = handlers.get(name)
  if (!set) handlers.set(name, (set = new Set()))
  set.add(h as Handler<never>)
  return () => {
    set.delete(h as Handler<never>)
  }
}

export function emit<K extends keyof BusEvents>(name: K, payload: BusEvents[K]) {
  handlers.get(name)?.forEach((h) => (h as Handler<BusEvents[K]>)(payload))
}
