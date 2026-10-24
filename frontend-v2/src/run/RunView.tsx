import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { IconBack, IconChevron, IconPrint } from '../components/icons'
import { Notice, SkeletonCard } from '../components/ui'
import { sideNames } from '../lib/format'
import { usePublishSections } from '../lib/sections'
import type { Connection } from '../lib/useLiveRun'
import { Sheet, type Snap } from '../motion/Sheet'
import { fade, spring, springQuick } from '../motion/springs'
import type { Analysis, AnalysisResult, RunStatus, TraceEvent } from '../types'
import BottomLine from './BottomLine'
import BridgingPanel from './BridgingPanel'
import { CaseOpening, CaseParties } from './CaseHeader'
import FamePanel from './FamePanel'
import FollowupBox from './FollowupBox'
import MemoView from './MemoView'
import OverlapPanel from './OverlapPanel'
import ResolutionCard from './ResolutionCard'
import TracePanel, { TraceAnnouncer, traceProgress } from './TracePanel'
import ZonePanel from './ZonePanel'
import './run.css'

const EVIDENCE_LABEL: Record<Analysis, string> = {
  overlap: 'Shared purchasers',
  bridging: 'Bridging the gap',
  fame: 'Fame',
  zone: 'Zone of reputation',
}

const ORDER: Analysis[] = ['overlap', 'bridging', 'fame', 'zone']
const DESKTOP = '(min-width: 1080px)'
const PEEK = 76

function useMediaQuery(query: string) {
  const [match, setMatch] = useState(() => (typeof window === 'undefined' ? true : window.matchMedia(query).matches))
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}

/**
 * A reserved slot whose content is replaced in place: the leaving element pops out of layout while
 * the arriving one takes its place, so nothing above the reader shifts.
 */
function Slot({ state, children }: { state: string; children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <div className="slot">
      <AnimatePresence initial={false} mode="popLayout">
        <motion.div
          key={state}
          initial={{ opacity: 0, y: reduce ? 0 : 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={reduce ? fade : spring}
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

function NotRun({ analysis, why }: { analysis: Analysis; why?: string }) {
  return (
    <div className="group not-run">
      <div className="group__row">
        <span className="not-run__dash" aria-hidden="true" />
        <span className="group__main">
          <span className="group__title">{EVIDENCE_LABEL[analysis]}</span>
          <span className="group__sub">Not measured{why ? `: ${why}` : ''}</span>
        </span>
      </div>
    </div>
  )
}

function StatusPill({ status, running }: { status: RunStatus; running: boolean }) {
  if (running)
    return (
      <span className="tb__status">
        <span className="spinner spinner--sm" aria-hidden="true" /> Running
      </span>
    )
  if (status === 'failed')
    return (
      <span className="tb__status">
        <span className="dot" style={{ background: 'var(--error)' }} aria-hidden="true" /> Failed
      </span>
    )
  return (
    <span className="tb__status">
      <span className="dot" style={{ background: 'var(--ok)' }} aria-hidden="true" /> Finished
    </span>
  )
}

/** Desktop trace: a floating glass panel docked bottom-right that collapses into a pill. */
function TraceDock({
  events,
  status,
  streaming,
  connection,
  onReconnect,
  defaultOpen,
}: {
  events: TraceEvent[]
  status: RunStatus
  streaming: boolean
  connection?: Connection
  onReconnect?: () => void
  defaultOpen: boolean
}) {
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(defaultOpen)
  const touched = useRef(false)
  const wasStreaming = useRef(streaming)
  const { summary } = useMemo(() => traceProgress(events, status), [events, status])

  // Opened for a live run; folds itself away once when the run settles, unless the reader chose.
  useEffect(() => {
    if (wasStreaming.current && !streaming && !touched.current) setOpen(false)
    if (!wasStreaming.current && streaming && !touched.current) setOpen(true)
    wasStreaming.current = streaming
  }, [streaming])

  const toggle = (v: boolean) => {
    touched.current = true
    setOpen(v)
  }

  const t = reduce ? fade : springQuick
  const hidden = { opacity: 0, scale: reduce ? 1 : 0.92 }
  return (
    <div className="dock no-print">
      <AnimatePresence initial={false} mode="popLayout">
        {open ? (
          <motion.div key="panel" className="dock__panel" initial={hidden} animate={{ opacity: 1, scale: 1 }} exit={hidden} transition={t}>
            <TracePanel events={events} status={status} streaming={streaming} connection={connection} onReconnect={onReconnect} onCollapse={() => toggle(false)} />
          </motion.div>
        ) : (
          <motion.button
            key="pill"
            type="button"
            className="dock__pill pressable"
            onClick={() => toggle(true)}
            aria-expanded={false}
            aria-label={`Show the agent trace: ${summary}`}
            initial={hidden}
            animate={{ opacity: 1, scale: 1 }}
            exit={hidden}
            transition={t}
          >
            {streaming ? <span className="live-dot" aria-hidden="true" /> : null}
            <span className="dock__pill-text num">
              <strong>Agent trace</strong>
              <span className="secondary"> · {summary}</span>
            </span>
            <span className="dock__chev" aria-hidden="true">
              <IconChevron size={14} />
            </span>
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function RunView({
  result: r,
  events,
  live,
  streaming = false,
  connection,
  onFollowup,
  onReconnect,
}: {
  result: AnalysisResult
  events: TraceEvent[]
  live: boolean
  streaming?: boolean
  connection?: Connection
  onFollowup?: (q: string) => Promise<void>
  onReconnect?: () => void
}) {
  const running = r.status === 'running' || r.status === 'queued' || streaming
  const names = sideNames(r)
  const ev = r.evidence
  const routed = r.routing?.analyses
  const title = r.extraction ? `${names.senior} v. ${names.junior}` : undefined
  const desktop = useMediaQuery(DESKTOP)

  useEffect(() => {
    document.title = `${title ?? (running ? 'Analyzing' : 'Run')} · Tea Rose`
  }, [title, running])

  // Phone sheet: starts at peek; the first time the run streams it rises to half once, then the
  // reader's own choice wins.
  const [snap, setSnap] = useState<Snap>('peek')
  const autoOpened = useRef(false)
  const tap = useRef<{ x: number; y: number; t: number } | null>(null)
  useEffect(() => {
    if (streaming && !autoOpened.current) {
      autoOpened.current = true
      setSnap('half')
    }
  }, [streaming])

  const memoExpected = running && !!r.routing
  const showEvidence = !!(r.resolution || ev) || running

  usePublishSections(
    [
      { id: 'case', label: 'Case', show: true },
      { id: 'bottom-line', label: 'Bottom line', show: !!r.memo || memoExpected },
      { id: 'parties', label: 'Parties', show: !!r.extraction || running },
      { id: 'resolution', label: 'Who was measured', show: !!r.resolution || running },
      { id: 'evidence', label: 'Evidence', show: showEvidence },
      { id: 'memo', label: 'Memo', show: !!r.memo || running },
    ]
      .filter((s) => s.show)
      .map(({ id, label }) => ({ id, label })),
  )

  function evidenceFor(a: Analysis): ReactNode {
    if (ev?.[a]) {
      let panel: ReactNode
      switch (a) {
        case 'overlap':
          panel = <OverlapPanel ev={ev.overlap!} resolution={r.resolution} names={names} />
          break
        case 'bridging':
          panel = <BridgingPanel ev={ev.bridging!} resolution={r.resolution} senior={names.senior} />
          break
        case 'fame':
          panel = <FamePanel ev={ev.fame!} senior={names.senior} />
          break
        case 'zone':
          panel = <ZonePanel ev={ev.zone!} senior={names.senior} junior={names.junior} juniorIsProxy={!!r.resolution?.junior_proxy} />
          break
      }
      return <Slot state="panel">{panel}</Slot>
    }
    if (routed && !routed.includes(a))
      return (
        <Slot state="notrun">
          <NotRun analysis={a} why={r.routing?.rationale[a]} />
        </Slot>
      )
    if (running)
      return (
        <Slot state="skeleton">
          <SkeletonCard lines={4} tall label={`${EVIDENCE_LABEL[a]}: waiting for scores`} />
        </Slot>
      )
    if (routed?.includes(a))
      return (
        <Slot state="noevidence">
          <NotRun analysis={a} why="no evidence was produced; see the trace" />
        </Slot>
      )
    return null
  }

  // Bands alternate white and gray in the order they appear. While a run streams every band that
  // will exist is reserved (skeleton), so the alternation never flips under the reader.
  const bands: { key: string; id?: string; label?: string; className?: string; wide?: boolean; node: ReactNode }[] = []

  bands.push({
    key: 'case',
    id: 'case',
    className: 'page-top run-open',
    node: (
      <>
        {r.status === 'failed' && (
          <div className="run-open__notice">
            <Notice kind="error" title="The run failed.">
              {r.error ?? 'See the trace for the last step that ran.'} Partial results are shown below.
            </Notice>
          </div>
        )}
        <Slot state={r.extraction ? 'case' : running ? 'case-skeleton' : 'case-input'}>
          {r.extraction ? (
            <CaseOpening extraction={r.extraction}>
              <Toolbar live={live} r={r} running={running} />
            </CaseOpening>
          ) : (
            <div className="opening">
              <p className="eyebrow">{running ? 'New analysis' : 'Input'}</p>
              <h1 className="t-headline opening__title">{running ? 'Reading the document' : 'Run'}</h1>
              <Toolbar live={live} r={r} running={running} />
              {running ? (
                <SkeletonCard lines={3} label="Reading the document" />
              ) : (
                r.input_excerpt && <p className="t-subtitle opening__summary">{r.input_excerpt}</p>
              )}
            </div>
          )}
        </Slot>
        <BottomLine memo={r.memo} expected={memoExpected} />
      </>
    ),
  })

  if (r.extraction || running)
    bands.push({
      key: 'parties',
      id: 'parties',
      node: (
        <Slot state={r.extraction ? 'parties' : 'parties-skeleton'}>
          {r.extraction ? <CaseParties extraction={r.extraction} routing={r.routing} /> : <SkeletonCard lines={4} tall label="Parties: reading the document" />}
        </Slot>
      ),
    })

  if (r.resolution || running)
    bands.push({
      key: 'resolution',
      id: 'resolution',
      node: (
        <Slot state={r.resolution ? 'resolution' : 'resolution-skeleton'}>
          {r.resolution ? <ResolutionCard resolution={r.resolution} /> : <SkeletonCard lines={3} tall label="Resolving brands in Qloo" />}
        </Slot>
      ),
    })

  if (showEvidence) {
    bands.push({
      key: 'evidence',
      id: 'evidence',
      className: 'band--tight evidence-intro',
      node: (
        <div className="band__head band__head--center evidence-intro__head">
          <p className="eyebrow">Evidence</p>
          <h2 className="t-display evidence-intro__title">What the taste graph shows.</h2>
          <p className="t-subtitle">Computed by code from the queries in the appendix. No model touches these numbers.</p>
        </div>
      ),
    })
    for (const a of ORDER) {
      const node = evidenceFor(a)
      if (node) bands.push({ key: `ev-${a}`, wide: true, label: EVIDENCE_LABEL[a], node })
    }
  }

  if (r.memo || running)
    bands.push({
      key: 'memo',
      id: 'memo-band',
      node: (
        <>
          <Slot state={r.memo ? 'memo' : 'memo-skeleton'}>
            {r.memo ? <MemoView memo={r.memo} title={title} /> : <SkeletonCard lines={6} tall label="Writing the memo" />}
          </Slot>
          {live && onFollowup && r.memo && <FollowupBox running={running} onAsk={onFollowup} />}
        </>
      ),
    })

  return (
    <div className="run" data-sheet={!desktop || undefined}>
      {bands.map((b, i) => (
        <section
          key={b.key}
          id={b.id}
          aria-label={b.label}
          className={`band ${i % 2 === 1 ? 'band--alt' : ''} ${b.className ?? ''}`}
          data-band={b.key}
        >
          <div className={`wrap ${b.wide ? 'wrap--wide' : ''}`}>{b.node}</div>
        </section>
      ))}

      <div className={`band band--tight ${bands.length % 2 === 1 ? 'band--alt' : ''} run-foot`}>
        <p className="wrap caption tertiary">
          Run <code>{r.run_id}</code> · {new Date(r.created_at).toLocaleString()} · Tea Rose produces triage evidence, not a consumer survey.
        </p>
      </div>

      <TraceAnnouncer events={events} status={r.status} streaming={streaming} />

      {desktop ? (
        <TraceDock events={events} status={r.status} streaming={streaming} connection={connection} onReconnect={onReconnect} defaultOpen={live && running} />
      ) : (
        <div
          className="no-print"
          onPointerDown={(e) => {
            if ((e.target as HTMLElement).closest('.sheet__grab')) tap.current = { x: e.clientX, y: e.clientY, t: performance.now() }
          }}
          onPointerUp={(e) => {
            // A tap on the grab area toggles the sheet. Pointer capture retargets the click away from
            // the handle button, so the tap is recognised here, after the sheet has settled.
            const t = tap.current
            tap.current = null
            if (!t || Math.hypot(e.clientX - t.x, e.clientY - t.y) > 6 || performance.now() - t.t > 350) return
            setSnap((s) => (s === 'peek' ? 'half' : 'peek'))
          }}
        >
          <div className="sheet-spacer" style={{ height: `calc(${PEEK}px + env(safe-area-inset-bottom))` }} aria-hidden="true" />
          <Sheet snap={snap} onSnap={setSnap} peekHeight={PEEK} label="Agent trace" header={<TracePanel events={events} status={r.status} streaming={streaming} compact />}>
            <TracePanel events={events} status={r.status} streaming={streaming} connection={connection} onReconnect={onReconnect} hideStepper />
          </Sheet>
        </div>
      )}
    </div>
  )
}

function Toolbar({ live, r, running }: { live: boolean; r: AnalysisResult; running: boolean }) {
  return (
    <div className="tb no-print" role="toolbar" aria-label="Run">
      <Link to={live ? '/analyze' : '/'} className="tb__item tb__back pressable">
        <IconBack size={14} /> {live ? 'New analysis' : 'All cases'}
      </Link>
      <span className="tb__sep" aria-hidden="true" />
      <span role="status" className="tb__item">
        <StatusPill status={r.status} running={running} />
      </span>
      <span className="tb__item tb__mode secondary" title={r.mode === 'fixture' ? 'Served from recorded fixtures or cache' : 'Live Qloo API'}>
        {r.showcase_slug ? 'Pre-computed' : r.mode === 'fixture' ? 'Fixture data' : 'Live Qloo'}
      </span>
      <span className="tb__sep" aria-hidden="true" />
      <button type="button" className="tb__item tb__print pressable" onClick={() => window.print()} disabled={!r.memo}>
        <IconPrint size={14} /> Print memo
      </button>
    </div>
  )
}
