import { useEffect, useId, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, MOCK } from '../api'
import { IconArrow, IconClose, IconDoc, IconLock, IconUpload } from '../components/icons'
import { ErrorState, Notice, StateView, errorMessage } from '../components/ui'
import { bytes } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import type { AuthMe, Limits } from '../types'

const MAX_BYTES = 2 * 1024 * 1024
const MIN_CHARS = 40

// ------------------------------------------------------------------ passcode gate

function PasscodeForm({ onSuccess }: { onSuccess: () => void }) {
  const [code, setCode] = useState('')
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
  const minutesLeft = Math.max(1, Math.ceil((lockedUntil - now) / 60000))

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

  return (
    <div className="gate card">
      <div className="gate__icon" aria-hidden="true">
        <IconLock size={22} />
      </div>
      <h1 className="gate__title">Live analysis is passcode-protected</h1>
      <p className="muted gate__lead">
        Live runs spend Qloo and model quota, so they are reserved for judges and invited testers. The showcase cases
        are open to everyone.
      </p>

      {disabled ? (
        <Notice kind="warn">
          <strong>Live mode is disabled right now.</strong> No passcode is configured on this server. You can still{' '}
          <Link to="/">open the pre-computed cases</Link>.
        </Notice>
      ) : (
        <form onSubmit={submit} className="gate__form" noValidate>
          <div className="field">
            <label className="label" htmlFor={inputId}>
              Passcode
            </label>
            <input
              id={inputId}
              className="input"
              type="password"
              autoComplete="current-password"
              value={code}
              onChange={(e) => {
                setCode(e.target.value)
                if (wrong) setErr(null)
              }}
              aria-invalid={wrong || undefined}
              aria-describedby={err ? errId : undefined}
              disabled={locked}
              autoFocus
            />
            {wrong && (
              <span className="field-error" id={errId} role="alert">
                That passcode is not right. Attempts are limited; five misses lock this connection for 15 minutes.
              </span>
            )}
          </div>
          {locked && (
            <div id={errId}>
              <Notice kind="warn">
                <strong>Too many attempts.</strong> Try again in about {minutesLeft} minute{minutesLeft === 1 ? '' : 's'}.
              </Notice>
            </div>
          )}
          {ae?.status === 429 && !locked && (
            <div id={errId}>
              <Notice kind="warn">{ae.detail || 'Too many requests. Wait a moment and try again.'}</Notice>
            </div>
          )}
          {err && !ae && (
            <div id={errId}>
              <Notice kind="error">{errorMessage(err)}</Notice>
            </div>
          )}
          {ae && ![401, 429, 503].includes(ae.status) && (
            <div id={errId}>
              <Notice kind="error">{errorMessage(ae)}</Notice>
            </div>
          )}
          <button className="btn btn--primary" type="submit" disabled={busy || locked || !code.trim()}>
            {busy ? <span className="spinner" aria-hidden="true" /> : null}
            {busy ? 'Checking' : 'Unlock live mode'}
          </button>
          {MOCK && <p className="hint">Mock mode: the passcode is “tearose”. Try “disabled” to see the 503 state.</p>}
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
    <span className={`chip ${low ? 'chip--warn' : 'chip--outline'}`}>
      <span className="num">Live runs: {parts.join(' · ')}</span>
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
      return e.kind === 'cap'
        ? e.detail || 'The live-analysis cap is reached. The showcase cases remain open.'
        : 'Too many requests in a short time. Wait a moment and try again.'
    case 503:
      return 'Live mode is disabled right now.'
    default:
      return errorMessage(e)
  }
}

function Intake({ me, limits, onSignedOut }: { me: AuthMe; limits?: Limits; onSignedOut: () => void }) {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [sampleName, setSampleName] = useState('')
  const [loadingSample, setLoadingSample] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const samples = useAsync(() => api.samples(), [])
  const textId = useId()
  const sampleId = useId()
  const hintId = useId()

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
    setSampleName(name)
    if (!name) return
    setLoadingSample(true)
    setError(null)
    try {
      setText(await api.sample(name))
      setFile(null)
      setError(null)
    } catch (e) {
      setError(`Could not load the sample: ${errorMessage(e)}`)
    } finally {
      setLoadingSample(false)
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

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
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
      <div className="intake__head">
        <div>
          <p className="eyebrow">New analysis</p>
          <h1>Paste the complaint or the letter</h1>
          <p className="muted intake__lead">
            Tea Rose reads it, decides which questions are live, and measures them on Qloo’s taste graph. A run takes
            about two minutes.
          </p>
        </div>
        <div className="intake__meta">
          <RunsLeft me={me} limits={limits} />
          <button type="button" className="btn btn--quiet btn--sm" onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>

      <div
        className="intake__card card"
        data-dragging={dragging}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <div className="intake__toolbar">
          <div className="intake__sample">
            <label className="sr-only" htmlFor={sampleId}>
              Load a sample document
            </label>
            <select
              id={sampleId}
              className="select"
              value={sampleName}
              onChange={(e) => void loadSample(e.target.value)}
              disabled={samples.loading || !!samples.error || !samples.data?.length}
            >
              <option value="">
                {samples.loading ? 'Loading samples…' : samples.error ? 'Samples unavailable' : samples.data?.length ? 'Load a sample…' : 'No samples'}
              </option>
              {samples.data?.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.title ?? s.name}
                </option>
              ))}
            </select>
            {loadingSample && <span className="spinner" aria-label="Loading sample" />}
          </div>
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
          <button type="button" className="btn btn--sm" onClick={() => fileInput.current?.click()}>
            <IconUpload size={15} /> Upload .pdf or .txt
          </button>
        </div>

        {file ? (
          <div className="intake__file">
            <span className="intake__file-icon" aria-hidden="true">
              <IconDoc size={22} />
            </span>
            <span className="intake__file-name">
              <strong>{file.name}</strong>
              <span className="faint caption num">{bytes(file.size)} · PDF text is extracted on the server</span>
            </span>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setFile(null)} aria-label={`Remove ${file.name}`}>
              <IconClose size={15} />
              Remove
            </button>
          </div>
        ) : (
          <div className="field">
            <label className="sr-only" htmlFor={textId}>
              Document text
            </label>
            <textarea
              id={textId}
              className="textarea intake__text"
              rows={14}
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
          <span className="hint num" id={hintId}>
            {file ? 'One file per run · max 2 MB' : `${text.length.toLocaleString('en-US')} characters · drop a file anywhere on this card`}
          </span>
          <button className="btn btn--primary" type="submit" disabled={busy || outOfRuns || loadingSample}>
            {busy ? <span className="spinner" aria-hidden="true" /> : null}
            {busy ? 'Starting' : 'Analyze'}
            {!busy && <IconArrow size={15} />}
          </button>
        </div>
        {dragging && (
          <div className="intake__drop" aria-hidden="true">
            <IconUpload size={22} /> Drop to attach
          </div>
        )}
      </div>

      <div aria-live="polite">
        {fileError && <Notice kind="error">{fileError}</Notice>}
        {error && <Notice kind="error">{error}</Notice>}
        {outOfRuns && (
          <Notice kind="warn">
            <strong>No live runs left.</strong> The cap resets daily. The <Link to="/">showcase cases</Link> remain open.
          </Notice>
        )}
      </div>

      <p className="caption faint intake__privacy">
        The document is sent to the Tea Rose server and to the language model to extract parties and goods. Only brand
        names and goods phrases go to Qloo; no personal data.
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
      <div className="gate card">
        <h1 className="gate__title">Live mode is off</h1>
        <Notice kind="warn">
          Live analysis is disabled on this server right now. The <Link to="/">showcase cases</Link> are pre-computed and
          open to everyone.
        </Notice>
      </div>
    )
  else if (!me.data?.authenticated) body = <PasscodeForm onSuccess={me.reload} />
  else body = <Intake me={me.data} limits={limits.data} onSignedOut={me.reload} />

  return <div className="container analyze page-enter">{body}</div>
}
