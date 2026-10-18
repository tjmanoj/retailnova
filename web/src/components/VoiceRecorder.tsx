import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUp, Mic, X } from 'lucide-react'
import type { AudioMime } from '../types'
import { cx } from './ui'

export interface Recording {
  base64: string
  mime: AudioMime
  seconds: number
  size: number
}

type RecState = 'idle' | 'requesting' | 'recording'

const MAX_SECONDS = 60
const MAX_BYTES = 2 * 1024 * 1024
const BARS = 28

const CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg']

function pickMime(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  return CANDIDATES.find((m) => {
    try {
      return MediaRecorder.isTypeSupported(m)
    } catch {
      return false
    }
  })
}

function toAudioMime(m: string): AudioMime {
  const base = m.split(';')[0].trim()
  if (base === 'audio/webm' || base === 'audio/ogg' || base === 'audio/mp4' || base === 'audio/mpeg' || base === 'audio/wav') return base
  if (base === 'video/webm') return 'audio/webm'
  if (base === 'video/mp4') return 'audio/mp4'
  return 'audio/webm'
}

function blobToBase64(b: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => {
      const s = String(r.result)
      resolve(s.slice(s.indexOf(',') + 1))
    }
    r.onerror = () => reject(r.error)
    r.readAsDataURL(b)
  })
}

export function voiceSupported() {
  return typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)
}

/**
 * Press-to-record voice notes with MediaRecorder (webm/opus where supported, mp4 on Safari),
 * a live timer and input level, 60 s maximum. `onAutoStop` fires when the limit is reached.
 */
export function useVoiceRecorder(onAutoStop?: (r: Recording | null) => void) {
  const [state, setState] = useState<RecState>('idle')
  const [seconds, setSeconds] = useState(0)
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0))
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const stream = useRef<MediaStream | null>(null)
  const ctx = useRef<AudioContext | null>(null)
  const raf = useRef<number | null>(null)
  const timer = useRef<number | null>(null)
  const startedAt = useRef(0)
  const resolver = useRef<((r: Recording | null) => void) | null>(null)
  const cancelled = useRef(false)
  const autoStopRef = useRef(onAutoStop)
  autoStopRef.current = onAutoStop

  const cleanup = useCallback(() => {
    if (raf.current) cancelAnimationFrame(raf.current)
    if (timer.current) window.clearInterval(timer.current)
    raf.current = null
    timer.current = null
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    void ctx.current?.close().catch(() => {})
    ctx.current = null
    setLevels(Array(BARS).fill(0))
  }, [])

  useEffect(() => () => {
    cancelled.current = true
    try {
      rec.current?.stop()
    } catch {
      /* already stopped */
    }
    cleanup()
  }, [cleanup])

  const stop = useCallback((): Promise<Recording | null> => {
    const r = rec.current
    if (!r || r.state === 'inactive') return Promise.resolve(null)
    return new Promise((resolve) => {
      resolver.current = resolve
      cancelled.current = false
      r.stop()
    })
  }, [])

  const cancel = useCallback(() => {
    cancelled.current = true
    try {
      rec.current?.stop()
    } catch {
      /* ignore */
    }
  }, [])

  const start = useCallback(async () => {
    setError(null)
    if (!voiceSupported()) {
      setError('Voice notes are not supported in this browser. Type your request instead.')
      return
    }
    setState('requesting')
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      stream.current = media
      const mime = pickMime()
      const mr = new MediaRecorder(media, mime ? { mimeType: mime, audioBitsPerSecond: 32000 } : undefined)
      rec.current = mr
      chunks.current = []
      cancelled.current = false
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      mr.onstop = async () => {
        const secs = Math.max(1, Math.round((performance.now() - startedAt.current) / 1000))
        const type = mr.mimeType || mime || 'audio/webm'
        cleanup()
        setState('idle')
        setSeconds(0)
        const res = resolver.current
        resolver.current = null
        if (cancelled.current) {
          res?.(null)
          return
        }
        const blob = new Blob(chunks.current, { type })
        if (blob.size > MAX_BYTES) {
          setError('That voice note is too long. Keep it under a minute.')
          res?.(null)
          return
        }
        const out: Recording = { base64: await blobToBase64(blob), mime: toAudioMime(type), seconds: Math.min(secs, MAX_SECONDS), size: blob.size }
        if (res) res(out)
        else autoStopRef.current?.(out)
      }
      // Input level for the live waveform.
      try {
        const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
        const ac = new AC()
        ctx.current = ac
        const src = ac.createMediaStreamSource(media)
        const an = ac.createAnalyser()
        an.fftSize = 512
        src.connect(an)
        const buf = new Uint8Array(an.fftSize)
        let last = 0
        const tick = (t: number) => {
          if (t - last > 70) {
            last = t
            an.getByteTimeDomainData(buf)
            let sum = 0
            for (let i = 0; i < buf.length; i++) {
              const v = (buf[i] - 128) / 128
              sum += v * v
            }
            const rms = Math.min(1, Math.sqrt(sum / buf.length) * 6)
            setLevels((prev) => [...prev.slice(1), rms])
          }
          raf.current = requestAnimationFrame(tick)
        }
        raf.current = requestAnimationFrame(tick)
      } catch {
        /* the waveform is decorative; recording still works */
      }
      startedAt.current = performance.now()
      setSeconds(0)
      timer.current = window.setInterval(() => {
        const s = Math.floor((performance.now() - startedAt.current) / 1000)
        setSeconds(s)
        if (s >= MAX_SECONDS && mr.state === 'recording') mr.stop()
      }, 250)
      mr.start(250)
      setState('recording')
    } catch (e) {
      cleanup()
      setState('idle')
      const name = (e as Error)?.name
      setError(
        name === 'NotAllowedError' || name === 'SecurityError'
          ? 'Microphone access is blocked. Allow it in your browser settings, or type instead.'
          : name === 'NotFoundError'
            ? 'No microphone found. Type your request instead.'
            : 'The microphone could not start. Try again, or type instead.',
      )
    }
  }, [cleanup])

  return { state, seconds, levels, error, setError, start, stop, cancel }
}

export function formatClock(s: number) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** The recording strip: cancel, live timer with level bars, and send. */
export function RecorderBar({
  seconds,
  levels,
  onCancel,
  onSend,
  compact = false,
}: {
  seconds: number
  levels: number[]
  onCancel: () => void
  onSend: () => void
  compact?: boolean
}) {
  const left = MAX_SECONDS - seconds
  return (
    <div className="flex w-full items-center gap-2" role="group" aria-label="Recording a voice note">
      <button
        type="button"
        onClick={onCancel}
        className={cx('grid shrink-0 place-items-center rounded-full border border-line-strong text-ink-2 hover:bg-surface-2 hover:text-ink', compact ? 'size-9' : 'size-11')}
        aria-label="Cancel voice note"
      >
        <X className="size-5" aria-hidden />
      </button>
      <div className={cx('flex min-w-0 flex-1 items-center gap-2.5 rounded-[22px] border border-maroon/40 bg-maroon-soft px-3', compact ? 'h-9' : 'h-11')}>
        <span className="relative flex size-2.5 shrink-0" aria-hidden>
          <span className="absolute inset-0 animate-ping rounded-full bg-danger opacity-60" />
          <span className="relative size-2.5 rounded-full bg-danger" />
        </span>
        <span className="num w-9 shrink-0 text-sm font-semibold text-maroon-ink" aria-live="off">
          {formatClock(seconds)}
        </span>
        <span className="flex h-6 min-w-0 flex-1 items-center gap-[3px] overflow-hidden" aria-hidden>
          {levels.map((l, i) => (
            <span
              key={i}
              className="w-[3px] shrink-0 rounded-full bg-maroon-ink/70 transition-[height] duration-75"
              style={{ height: `${Math.max(12, Math.round(l * 100))}%` }}
            />
          ))}
        </span>
        {left <= 10 && <span className="shrink-0 text-xs text-maroon-ink">{left}s left</span>}
        <span className="sr-only">Recording. {seconds} seconds.</span>
      </div>
      <button
        type="button"
        onClick={onSend}
        className={cx('grid shrink-0 place-items-center rounded-full bg-maroon text-on-maroon hover:bg-maroon-hover', compact ? 'size-9' : 'size-11')}
        aria-label="Send voice note"
      >
        <ArrowUp className="size-5" aria-hidden />
      </button>
    </div>
  )
}

export function MicButton({ onClick, busy, compact = false, label = 'Record a voice note' }: { onClick: () => void; busy?: boolean; compact?: boolean; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={cx(
        'grid shrink-0 place-items-center rounded-full border border-line-strong text-ink-2 hover:border-maroon-ink hover:bg-maroon-soft hover:text-maroon-ink disabled:opacity-50',
        compact ? 'size-9' : 'size-11',
      )}
      aria-label={label}
      title="Speak in Tamil, Hindi or English"
    >
      <Mic className="size-5" aria-hidden />
    </button>
  )
}

export const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  hi: 'Hindi',
  ta: 'Tamil',
  te: 'Telugu',
  kn: 'Kannada',
  ml: 'Malayalam',
  mr: 'Marathi',
  bn: 'Bengali',
  gu: 'Gujarati',
  pa: 'Punjabi',
  ur: 'Urdu',
}

export function languageName(code: string | null | undefined) {
  if (!code) return ''
  const k = code.toLowerCase().split(/[-_]/)[0]
  return LANGUAGE_NAMES[k] ?? code
}
