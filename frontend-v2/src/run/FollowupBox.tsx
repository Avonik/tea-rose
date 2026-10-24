import { AnimatePresence } from 'motion/react'
import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError } from '../api'
import { IconSend } from '../components/icons'
import { Notice, errorMessage } from '../components/ui'
import { Reveal } from '../motion/Reveal'
import './memo.css'

const SUGGESTIONS = [
  'What if the junior goods were luxury dog collars instead of toys?',
  'Re-run the overlap with only the two largest comparator brands.',
  'Does the picture change for the zone of reputation in the Pacific Northwest?',
]

function followupError(x: unknown): string {
  if (x instanceof ApiError) {
    switch (x.status) {
      case 409:
        return 'The run is still working. Ask again once it finishes.'
      case 429:
        return x.detail || 'The live-analysis cap is reached for now.'
      case 401:
        return 'Your session ended. Unlock live mode again on the Analyze page.'
      default:
        return errorMessage(x)
    }
  }
  return errorMessage(x)
}

export default function FollowupBox({ running, onAsk }: { running: boolean; onAsk: (q: string) => Promise<void> }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [sent, setSent] = useState<string | null>(null)
  const id = useId()

  async function submit(e?: FormEvent | KeyboardEvent) {
    e?.preventDefault()
    const question = q.trim()
    if (!question || busy || running) return
    setBusy(true)
    setErr(null)
    try {
      await onAsk(question)
      setSent(question)
      setQ('')
    } catch (x) {
      setErr(followupError(x))
    } finally {
      setBusy(false)
    }
  }

  const working = busy || running
  const state = err ? 'error' : sent && running ? 'working' : sent ? 'done' : 'idle'

  return (
    <section className="followup no-print" id="followup" aria-labelledby={`${id}-t`}>
      <div className="followup__head">
        <h3 id={`${id}-t`} className="t-title">
          Ask a follow-up
        </h3>
        <p className="secondary callout">
          The agent re-enters at <em>resolve</em> with your instruction and reruns only what it affects. New queries join the
          appendix; scores still come from code.
        </p>
      </div>
      <form onSubmit={submit} className="group followup__form">
        <label htmlFor={id} className="sr-only">
          Follow-up question
        </label>
        <textarea
          id={id}
          className="followup__input"
          rows={3}
          placeholder="What if the goods are luxury handbags, not apparel?"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            if (err) setErr(null)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submit(e)
          }}
          disabled={running}
          aria-describedby={`${id}-hint`}
        />
        <div className="followup__actions">
          <span className="caption tertiary" id={`${id}-hint`}>
            ⌘/Ctrl + Enter to ask
          </span>
          <button type="submit" className="btn btn--primary" disabled={!q.trim() || working}>
            {working ? <span className="spinner spinner--sm" aria-hidden="true" /> : <IconSend size={15} />}
            {running ? 'Working' : 'Ask'}
          </button>
        </div>
      </form>

      <AnimatePresence initial={false} mode="popLayout">
        {!q && !running && (
          <Reveal key="suggest" quick className="followup__suggest">
            <p className="caption secondary">Try one:</p>
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="chip followup__chip" onClick={() => setQ(s)}>
                  {s}
                </button>
              ))}
            </div>
          </Reveal>
        )}
      </AnimatePresence>

      <div aria-live="polite" className="followup__status">
        <AnimatePresence initial={false} mode="wait">
          {state === 'error' && (
            <Reveal key="err" quick>
              <Notice kind="error">{err}</Notice>
            </Reveal>
          )}
          {state === 'working' && (
            <Reveal key="working" quick>
              <p className="footnote secondary followup__working">
                <span className="spinner spinner--sm" aria-hidden="true" />
                Working on: “{sent}”. Watch the trace for progress.
              </p>
            </Reveal>
          )}
          {state === 'done' && (
            <Reveal key="done" quick>
              <Notice kind="ok" title="Answered.">
                “{sent}”. The memo above now has the new section, and any new queries are in its appendix.{' '}
                <a href="#memo">Go to the memo</a>
              </Notice>
            </Reveal>
          )}
        </AnimatePresence>
      </div>
    </section>
  )
}
