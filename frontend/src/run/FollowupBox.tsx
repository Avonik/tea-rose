import { useId, useState, type FormEvent } from 'react'
import { ApiError } from '../api'
import { IconSend } from '../components/icons'
import { Notice, errorMessage } from '../components/ui'

const SUGGESTIONS = [
  'What if the junior goods were luxury dog collars instead of toys?',
  'Re-run the overlap with only the two largest comparator brands.',
  'Does the picture change for the zone of reputation in the Pacific Northwest?',
]

export default function FollowupBox({ running, onAsk }: { running: boolean; onAsk: (q: string) => Promise<void> }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [sent, setSent] = useState<string | null>(null)
  const id = useId()

  async function submit(e: FormEvent) {
    e.preventDefault()
    const question = q.trim()
    if (!question || busy || running) return
    setBusy(true)
    setErr(null)
    try {
      await onAsk(question)
      setSent(question)
      setQ('')
    } catch (x) {
      if (x instanceof ApiError && x.status === 409) setErr('The run is still working. Ask again once it finishes.')
      else if (x instanceof ApiError && x.status === 429) setErr(x.detail || 'The live-analysis cap is reached for now.')
      else if (x instanceof ApiError && x.status === 401) setErr('Your session ended. Unlock live mode again on the Analyze page.')
      else setErr(errorMessage(x))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card followup no-print" id="followup" aria-labelledby={`${id}-t`}>
      <h3 id={`${id}-t`}>Ask a follow-up</h3>
      <p className="muted footnote">
        The agent re-enters at <em>resolve</em> with your instruction and reruns only what it affects. New queries join
        the appendix; scores still come from code.
      </p>
      <form onSubmit={submit} className="followup__form">
        <label htmlFor={id} className="sr-only">
          Follow-up question
        </label>
        <textarea
          id={id}
          className="textarea followup__input"
          rows={2}
          placeholder="What if the goods are luxury handbags, not apparel?"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submit(e)
          }}
          disabled={running}
        />
        <button type="submit" className="btn btn--primary" disabled={!q.trim() || busy || running}>
          {busy || running ? <span className="spinner" aria-hidden="true" /> : <IconSend size={15} />}
          {running ? 'Working' : 'Ask'}
        </button>
      </form>
      {!q && !running && (
        <div className="chips followup__suggest">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip chip--outline followup__chip" onClick={() => setQ(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
      <div aria-live="polite">
        {err && <Notice kind="error">{err}</Notice>}
        {sent && running && <p className="caption faint">Working on: “{sent}”. Watch the trace for progress.</p>}
      </div>
    </section>
  )
}
