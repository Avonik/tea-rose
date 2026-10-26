import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useId, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, MOCK } from '../api'
import { IconClose, IconDoc, IconLock, IconScale, IconSparkle, IconUpload } from '../components/icons'
import { ErrorState, Notice, StateView, errorMessage } from '../components/ui'
import { sampleLabel } from '../content/cases'
import { bytes } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { Page, Reveal } from '../motion/Reveal'
import { fade, springQuick } from '../motion/springs'
import type { AuthMe, Limits, SampleRef } from '../types'
import '../styles/analyze.css'

const MAX_BYTES = 2 * 1024 * 1024
const MIN_CHARS = 40

// ------------------------------------------------------------------ passcode gate

function GateIcon() {
  return (
    <span className="gate__icon" aria-hidden="true">
      <IconLock size={26} />
    </span>
  )
}

function PasscodeForm({ onSuccess }: { onSuccess: () => void }) {
  const [code, setCode] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<ApiError | Error | null>(null)
  const [lockedUntil, setLockedUntil] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const inputId = useId()
  const errId = useId()

  useEffect(() => {
    if (lockedUntil <= now) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [lockedUntil, now])

  const locked = lockedUntil > now
  const secondsLeft = Math.max(0, Math.ceil((lockedUntil - now) / 1000))
  const countdown = `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')}`

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!code.trim() || busy || locked) return
    setBusy(true)
    setErr(null)
    try {
      await api.login(code.trim())
      onSuccess()
    } catch (x) {
      const ae = x instanceof ApiError ? x : null
      if (ae?.status === 429 && (ae.kind === 'lockout' || ae.retryAfter)) {
        setLockedUntil(Date.now() + (ae.retryAfter ?? 900) * 1000)
        setNow(Date.now())
      }
      setErr(x as Error)
    } finally {
      setBusy(false)
    }
  }

  const ae = err instanceof ApiError ? err : null
  const wrong = ae?.status === 401
  const disabled = ae?.status === 503

  let message: { kind: 'warn' | 'error'; text: string } | null = null
  if (locked) message = { kind: 'warn', text: 'Too many attempts. This connection is locked for a short while.' }
  else if (wrong) message = { kind: 'error', text: 'That passcode is not right. Attempts are limited; five misses lock this connection for 15 minutes.' }
  else if (ae?.status === 429) message = { kind: 'warn', text: ae.detail || 'Too many requests. Wait a moment and try again.' }
  else if (err && !disabled) message = { kind: 'error', text: errorMessage(err) }

  return (
    <div className="gate">
      <GateIcon />
      <h1 className="t-headline gate__title">Live analysis is passcode-protected</h1>
      <p className="t-subtitle gate__lead">
        Live runs spend Qloo and model quota, so they are reserved for judges and invited testers. The showcase cases are open to
        everyone.
      </p>

      {disabled ? (
        <Notice kind="warn" title="Live mode is disabled right now.">
          No passcode is configured on this server. You can still <Link to="/">open the pre-computed cases</Link>.
        </Notice>
      ) : (
        <form onSubmit={submit} className="gate__form" noValidate>
          <div className="field">
            <label className="sr-only" htmlFor={inputId}>
              Passcode
            </label>
            <div className="gate__field">
              <input
                id={inputId}
                className="input gate__input"
                type={show ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Passcode"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value)
                  if (wrong) setErr(null)
                }}
                aria-invalid={wrong || undefined}
                aria-describedby={message ? errId : undefined}
                disabled={locked}
                autoFocus
              />
              <button
                type="button"
                className="gate__toggle pressable"
                onClick={() => setShow((s) => !s)}
                aria-pressed={show}
                aria-label={show ? 'Hide passcode' : 'Show passcode'}
              >
                {show ? 'Hide' : 'Show'}
              </button>
            </div>
            <AnimatePresence initial={false}>
              {message && (
                <Reveal key={message.text} from="above" quick distance={8}>
                  <div id={errId} className="gate__message">
                    <Notice kind={message.kind}>{message.text}</Notice>
                  </div>
                </Reveal>
              )}
            </AnimatePresence>
          </div>

          {locked ? (
            <span className="chip gate__countdown" role="status">
              <span className="dot" style={{ background: 'var(--warn)' }} aria-hidden="true" />
              Try again in <span className="num">{countdown}</span>
            </span>
          ) : (
            <button className="btn btn--primary btn--lg gate__submit" type="submit" disabled={busy || !code.trim()}>
              {busy && <span className="spinner spinner--sm" aria-hidden="true" />}
              {busy ? 'Checking' : 'Unlock live mode'}
            </button>
          )}
          {MOCK && <p className="hint gate__hint">Mock mode: the passcode is “tearose”. Try “disabled” to see the 503 state.</p>}
        </form>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ intake

function RunsLeft({ me, limits }: { me: AuthMe; limits?: Limits }) {
  const parts: string[] = []
  if (me.runs_left_session != null) parts.push(`${me.runs_left_session} left this session`)
  if (me.runs_left_today != null) parts.push(`${me.runs_left_today} left today`)
  if (!parts.length && limits?.daily_cap != null && limits.daily_used != null) parts.push(`${limits.daily_cap - limits.daily_used} left today`)
  if (!parts.length) return null
  const low = (me.runs_left_session ?? 99) <= 2 || (me.runs_left_today ?? 99) <= 2
  return (
    <span className="chip chip--quiet">
      {low && <span className="dot" style={{ background: 'var(--warn)' }} aria-hidden="true" />}
      <span className="num">Runs left: {parts.join(' · ')}</span>
    </span>
  )
}

function analyzeError(e: unknown): string {
  if (!(e instanceof ApiError)) return errorMessage(e)
  switch (e.status) {
    case 400:
      return e.detail || 'The document is empty or could not be read. If it is a scanned PDF, paste the text instead.'
    case 413:
      return 'The file is larger than 2 MB. Paste the relevant pages as text instead.'
    case 415:
      return 'Only .pdf and .txt files are supported.'
    case 429:
      return e.kind === 'cap' ? e.detail || 'The live-analysis cap is reached. The showcase cases remain open.' : 'Too many requests in a short time. Wait a moment and try again.'
    case 503:
      return 'Live mode is disabled right now.'
    default:
      return errorMessage(e)
  }
}

const NEXT_STEPS = [
  { icon: <IconDoc size={16} />, title: 'Reads the document', text: 'Parties, marks, goods quoted verbatim, and the claims pleaded.' },
  { icon: <IconScale size={16} />, title: 'Measures on Qloo', text: 'Shared purchasers, fame breadth and zone of reputation, every call logged.' },
  { icon: <IconSparkle size={16} />, title: 'Writes the memo', text: 'A preliminary read from the pleadings, factor findings, limitations and a query appendix. About two minutes.' },
]

function Intake({ me, limits, onSignedOut }: { me: AuthMe; limits?: Limits; onSignedOut: () => void }) {
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [sampleName, setSampleName] = useState('')
  const [loadingSample, setLoadingSample] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const dragDepth = useRef(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const samples = useAsync<SampleRef[]>(() => api.samples(), [])
  const textId = useId()
  const hintId = useId()
  const samplesId = useId()

  const outOfRuns = me.runs_left_session === 0 || me.runs_left_today === 0

  async function acceptFile(f: File) {
    setFileError(null)
    setError(null)
    const name = f.name.toLowerCase()
    const isPdf = name.endsWith('.pdf') || f.type === 'application/pdf'
    const isTxt = name.endsWith('.txt') || f.type === 'text/plain'
    if (!isPdf && !isTxt) return setFileError('Only .pdf and .txt files are supported.')
    if (f.size > MAX_BYTES) return setFileError(`That file is ${bytes(f.size)}; the limit is 2 MB.`)
    if (f.size === 0) return setFileError('That file is empty.')
    if (isTxt) {
      setText(await f.text())
      setFile(null)
      setSampleName('')
    } else {
      setFile(f)
      setSampleName('')
    }
  }

  async function loadSample(name: string) {
    if (!name || loadingSample) return
    setLoadingSample(name)
    setError(null)
    try {
      const t = await api.sample(name)
      setText(t)
      setFile(null)
      setSampleName(name)
      setError(null)
    } catch (e) {
      setError(`Could not load the sample: ${errorMessage(e)}`)
    } finally {
      setLoadingSample(null)
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    if (!file && text.trim().length < MIN_CHARS) {
      setError(`Paste at least ${MIN_CHARS} characters, upload a file, or pick a sample.`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const { run_id } = await api.analyze(file ? { file } : { text })
      navigate(`/run/${encodeURIComponent(run_id)}`)
    } catch (x) {
      if (x instanceof ApiError && x.status === 401) return onSignedOut()
      setError(analyzeError(x))
      setBusy(false)
    }
  }

  const onDragEnter = (e: DragEvent) => {
    e.preventDefault()
    dragDepth.current += 1
    setDragging(true)
  }
  const onDragLeave = () => {
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setDragging(false)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    dragDepth.current = 0
    setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) void acceptFile(f)
  }

  async function signOut() {
    try {
      await api.logout()
    } finally {
      onSignedOut()
    }
  }

  return (
    <form className="intake" onSubmit={submit} noValidate>
      <header className="intake__head">
        <p className="eyebrow">New analysis</p>
        <h1 className="t-headline">Paste the pleadings or the letter</h1>
        <p className="t-subtitle">
          The complaint, plus the defendant’s answer if you have it. Tea Rose reads it, decides which questions are live, and measures them on Qloo’s taste graph. A run takes about two
          minutes.
        </p>
      </header>

      <div
        className="group intake__group"
        data-dragging={dragging || undefined}
        onDragEnter={onDragEnter}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <div className="intake__samples" role="group" aria-labelledby={samplesId}>
          <span className="caption secondary" id={samplesId}>
            Start from a sample
          </span>
          {samples.loading && <span className="chip chip--quiet">Loading samples…</span>}
          {!samples.loading && !!samples.error && <span className="chip chip--quiet">Samples unavailable</span>}
          {!samples.loading && !samples.error && !samples.data?.length && <span className="chip chip--quiet">No samples</span>}
          {!!samples.data?.length && (
            <div className="sample-tiles">
              {samples.data.map((s) => {
                const on = sampleName === s.name
                const loading = loadingSample === s.name
                const { title, kind } = sampleLabel(s.name)
                return (
                  <button
                    key={s.name}
                    type="button"
                    className="sample-tile pressable"
                    aria-pressed={on}
                    disabled={!!loadingSample}
                    onClick={() => void loadSample(s.name)}
                  >
                    <span className="sample-tile__icon" aria-hidden="true">
                      {loading ? <span className="spinner spinner--sm" /> : <IconDoc size={14} />}
                    </span>
                    <span className="sample-tile__text">
                      <span className="sample-tile__title">{title}</span>
                      {kind && <span className="sample-tile__kind caption">{kind}</span>}
                    </span>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {file ? (
          <div className="intake__file">
            <span className="intake__file-icon" aria-hidden="true">
              <IconDoc size={22} />
            </span>
            <span className="intake__file-name">
              <strong>{file.name}</strong>
              <span className="caption secondary num">{bytes(file.size)} · PDF text is extracted on the server</span>
            </span>
            <button type="button" className="btn btn--sm" onClick={() => setFile(null)} aria-label={`Remove ${file.name}`}>
              <IconClose size={14} />
              Remove
            </button>
          </div>
        ) : (
          <div className="intake__textwrap">
            <label className="sr-only" htmlFor={textId}>
              Document text
            </label>
            <textarea
              id={textId}
              className="intake__text serif"
              rows={16}
              placeholder="Paste a complaint, a cease-and-desist letter, a TTAB petition or your own notes. Or drop a .pdf / .txt here."
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                setSampleName('')
                if (error) setError(null)
              }}
              aria-describedby={hintId}
            />
          </div>
        )}

        <div className="intake__foot">
          <span className="caption tertiary num" id={hintId}>
            {file ? 'One file per run · max 2 MB' : `${text.length.toLocaleString('en-US')} characters · drop a file anywhere here`}
          </span>
          <span className="intake__actions">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              className="sr-only"
              tabIndex={-1}
              aria-hidden="true"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void acceptFile(f)
                e.target.value = ''
              }}
            />
            <button type="button" className="btn" onClick={() => fileInput.current?.click()}>
              <IconUpload size={15} /> Upload .pdf or .txt
            </button>
            <button className="btn btn--primary" type="submit" disabled={busy || outOfRuns || !!loadingSample}>
              {busy ? <span className="spinner spinner--sm" aria-hidden="true" /> : null}
              {busy ? 'Starting' : 'Analyze'}
            </button>
          </span>
        </div>

        <AnimatePresence>
          {dragging && (
            <motion.div
              className="intake__drop"
              aria-hidden="true"
              initial={{ opacity: 0, scale: reduce ? 1 : 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: reduce ? 1 : 0.98 }}
              transition={reduce ? fade : springQuick}
            >
              <span className="intake__drop-inner">
                <IconUpload size={22} /> Drop to attach
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div aria-live="polite" className="intake__messages">
        <AnimatePresence initial={false}>
          {fileError && (
            <Reveal key={`f-${fileError}`} from="above" quick distance={8}>
              <Notice kind="error">{fileError}</Notice>
            </Reveal>
          )}
          {error && (
            <Reveal key={`e-${error}`} from="above" quick distance={8}>
              <Notice kind="error">{error}</Notice>
            </Reveal>
          )}
          {outOfRuns && (
            <Reveal key="cap" from="above" quick distance={8}>
              <Notice kind="warn" title="No live runs left.">
                The cap resets daily. The <Link to="/">showcase cases</Link> remain open.
              </Notice>
            </Reveal>
          )}
        </AnimatePresence>
      </div>

      <div className="intake__meta">
        <RunsLeft me={me} limits={limits} />
        <button type="button" className="linklike footnote" onClick={signOut}>
          Sign out
        </button>
      </div>

      <section aria-labelledby="next-title" className="intake__next">
        <h2 id="next-title" className="group-label">
          What happens next
        </h2>
        <ol className="group next">
          {NEXT_STEPS.map((s, i) => (
            <li key={s.title} className="group__row group__row--top">
              <span className="next__icon" aria-hidden="true">
                {s.icon}
              </span>
              <span className="group__main">
                <span className="group__title">
                  <span className="tertiary num">{i + 1}. </span>
                  {s.title}
                </span>
                <span className="group__sub">{s.text}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <p className="caption tertiary intake__privacy">
        The document is sent to the Tea Rose server and to the language model to extract parties and goods. Only brand names and
        goods phrases go to Qloo; no personal data.
      </p>
    </form>
  )
}

// ------------------------------------------------------------------ page

export default function AnalyzePage() {
  const me = useAsync(() => api.me(), [])
  const limits = useAsync(() => api.limits(), [])

  let body
  if (me.loading && !me.data) body = <StateView kind="loading" title="Checking your session" />
  else if (me.error) body = <ErrorState error={me.error} onRetry={me.reload} title="Could not check your session" />
  else if (limits.data && limits.data.live_mode_enabled === false && !me.data?.authenticated)
    body = (
      <div className="gate">
        <GateIcon />
        <h1 className="t-headline gate__title">Live mode is off</h1>
        <Notice kind="warn">
          Live analysis is disabled on this server right now. The <Link to="/">showcase cases</Link> are pre-computed and open to
          everyone.
        </Notice>
      </div>
    )
  else if (!me.data?.authenticated) body = <PasscodeForm onSuccess={me.reload} />
  else body = <Intake me={me.data} limits={limits.data} onSignedOut={me.reload} />

  return (
    <Page className="band analyze page-top">
      <div className="wrap">{body}</div>
    </Page>
  )
}
