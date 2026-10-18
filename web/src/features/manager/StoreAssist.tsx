import { useState, type FormEvent } from 'react'
import { Check, ClipboardList } from 'lucide-react'
import type { AssistResponse } from '../../types'
import { api } from '../../lib/api'
import { emit } from '../../lib/bus'
import { storeName } from '../../lib/constants'
import { formatINR } from '../../lib/format'
import { Badge, Button, cx } from '../../components/ui'
import { MicButton, RecorderBar, useVoiceRecorder, voiceSupported, type Recording } from '../../components/VoiceRecorder'

/** §9.3 Store assist: staff log what a walk-in customer asked for, by typing or a voice note. */
export function StoreAssist({ storeId, className }: { storeId: string; className?: string }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<AssistResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = async (payload: { text?: string; rec?: Recording }) => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.assist({
        store_id: storeId,
        ...(payload.text ? { text: payload.text } : {}),
        ...(payload.rec ? { audio_base64: payload.rec.base64, audio_mime: payload.rec.mime } : {}),
      })
      setResult(r)
      setText('')
      if (r.signal) emit('signal', r.signal)
      emit('radarRefresh', null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const recorder = useVoiceRecorder((rec) => rec && void submit({ rec }))
  const recording = recorder.state === 'recording'
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim()) void submit({ text: text.trim() })
  }

  return (
    <section className={cx('rounded-2xl border border-line bg-surface p-4', className)} aria-labelledby="assist-title">
      <h2 id="assist-title" className="display-tight flex items-center gap-2 text-lg text-ink">
        <ClipboardList className="size-4 text-ink-3" aria-hidden />
        Log a walk-in request
      </h2>
      <p className="mt-0.5 text-xs text-ink-3">Capture what a customer asked for at the counter. It joins the demand signals for {storeName(storeId)}.</p>
      <form onSubmit={onSubmit} className="mt-3 space-y-2">
        {recording ? (
          <RecorderBar compact seconds={recorder.seconds} levels={recorder.levels} onCancel={recorder.cancel} onSend={async () => {
            const r = await recorder.stop()
            if (r) void submit({ rec: r })
          }} />
        ) : (
          <>
            <label htmlFor="assist-input" className="sr-only">
              What did the customer ask for?
            </label>
            <textarea
              id="assist-input"
              rows={2}
              maxLength={500}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Customer wanted a red Banarasi saree, about ₹8,000. We had none."
              className="w-full resize-none rounded-xl border border-line-strong bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-ink-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-marigold/50"
            />
            <div className="flex items-center justify-end gap-2">
              {voiceSupported() && <MicButton compact onClick={() => void recorder.start()} busy={busy || recorder.state === 'requesting'} label="Record the request as a voice note" />}
              <Button type="submit" variant="secondary" size="sm" loading={busy} disabled={!text.trim()}>
                Log request
              </Button>
            </div>
          </>
        )}
      </form>
      {(recorder.error || error) && (
        <p className="mt-2 text-xs text-danger" role="alert">
          {recorder.error || error}
        </p>
      )}
      {result && (
        <div className="anim-slide-down mt-3 rounded-xl bg-surface-2 px-3 py-2.5 text-sm" role="status">
          <p className="flex items-center gap-1.5 font-semibold text-leaf">
            <Check className="size-4" aria-hidden /> {result.message}
          </p>
          {result.transcript && <p className="mt-1 text-xs text-ink-2">Heard: “{result.transcript}”</p>}
          {result.signal && (
            <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-3">
              <Badge tone={result.signal.outcome === 'unmet' ? 'maroon' : result.signal.outcome === 'substituted' ? 'marigold' : 'leaf'}>
                {result.signal.outcome === 'unmet' ? 'Unmet' : result.signal.outcome === 'substituted' ? 'Substituted' : 'Fulfilled'}
              </Badge>
              <span className="num font-semibold text-ink">{formatINR(result.signal.est_value_inr)}</span>
              <span className="min-w-0 flex-1 truncate">{result.signal.summary}</span>
            </p>
          )}
        </div>
      )}
    </section>
  )
}
