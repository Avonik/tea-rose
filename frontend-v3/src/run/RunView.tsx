import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { IconBack, IconChevron, IconPrint } from '../components/icons'
import { Disclosure, Notice, SkeletonCard } from '../components/ui'
import { caseStory, type CaseStory } from '../content/cases'
import { courtFraming } from '../content/copy'
import { displayNames } from '../lib/format'
import { usePublishSections } from '../lib/sections'
import type { Connection } from '../lib/useLiveRun'
import { Sheet, type Snap } from '../motion/Sheet'
import { fade, spring, springQuick } from '../motion/springs'
import type { Analysis, AnalysisResult, RunStatus, TraceEvent } from '../types'
import BottomLine from './BottomLine'
import { CaseOpening, CaseParties, outcomeText } from './CaseHeader'
import { ContextOnly } from './EvidenceKit'
import FamePanel from './FamePanel'
import FollowupBox from './FollowupBox'
import { MemoLimits, MemoMeaning, QueryAppendix, useQueryNav } from './MemoView'
import OverlapPanel from './OverlapPanel'
import PreliminaryReadCard from './PreliminaryRead'
import ResolutionCard from './ResolutionCard'
import TracePanel, { TraceAnnouncer, traceProgress } from './TracePanel'
import ZonePanel from './ZonePanel'
import './run.css'

/** The three questions, in page order. Bridging rides along under question 1. */
type Question = 'overlap' | 'fame' | 'zone'
const QUESTIONS: Question[] = ['overlap', 'fame', 'zone']
const QUESTION_LABEL: Record<Question, string> = {
  overlap: 'Do the same people buy both?',
  fame: 'Is it known by everyone?',
  zone: 'Where is it known?',
}
const ANALYSES_FOR: Record<Question, Analysis[]> = { overlap: ['overlap', 'bridging'], fame: ['fame'], zone: ['zone'] }

/** Which analysis measures each memo factor. */
const FACTOR_ANALYSIS: Record<string, Analysis> = {
  relatedness_of_goods: 'overlap',
  channels_and_purchasers: 'overlap',
  bridging_the_gap: 'bridging',
  fame: 'fame',
  zone_of_reputation: 'zone',
}

/**
 * The reveal, below the preliminary read: what the court decided, the outcome, and one sentence
 * computed from the read's lean against that outcome.
 */
function CourtReveal({ story, r, names }: { story: CaseStory; r: AnalysisResult; names: { senior: string; junior: string } }) {
  const read = r.memo?.preliminary_read
  const framing = read ? courtFraming(read.lean, story.outcome, read.turns_on, names) : ''
  return (
    <section className="routing" aria-labelledby="court-title">
      <h2 id="court-title" className="group-label">
        What the court decided
      </h2>
      <div className="group">
        <div className="group__row group__row--top">
          <span className="group__main">
            <span className="group__title">{story.court}</span>
            {framing && <span className="group__sub">{framing}</span>}
            <span className="chips">
              <span className="chip chip--quiet chip--sm">Outcome: {outcomeText(story.outcome, names)}</span>
            </span>
          </span>
        </div>
      </div>
    </section>
  )
}

/** Showcase slugs used by the mock dataset, mapped onto the story keys in content/cases.ts. */
const STORY_ALIAS: Record<string, string> = {
  'bad_spaniels': 'bad_spaniels',
  'coach_triumph': 'coach_triumph',
  'starbucks-v-charbucks': 'charbucks',
  'louis-vuitton-v-chewy-vuiton': 'chewy_vuiton',
  'vans-v-mschf': 'vans_mschf',
}

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

function NotRun({ title, why }: { title: string; why?: string }) {
  return (
    <div className="group not-run">
      <div className="group__row">
        <span className="not-run__dash" aria-hidden="true" />
        <span className="group__main">
          <span className="group__title">{title}</span>
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
  openRequest,
}: {
  events: TraceEvent[]
  status: RunStatus
  streaming: boolean
  connection?: Connection
  onReconnect?: () => void
  defaultOpen: boolean
  /** Bumped by "Open the agent trace" in How we got here. */
  openRequest: number
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

  useEffect(() => {
    if (openRequest > 0) {
      touched.current = true
      setOpen(true)
    }
  }, [openRequest])

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

function BandHead({ eyebrow, title, sub, id }: { eyebrow: string; title: string; sub?: ReactNode; id?: string }) {
  return (
    <div className="band__head">
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={id} className="t-headline">
        {title}
      </h2>
      {sub && <p className="t-subtitle">{sub}</p>}
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
  year,
}: {
  result: AnalysisResult
  events: TraceEvent[]
  live: boolean
  streaming?: boolean
  connection?: Connection
  onFollowup?: (q: string) => Promise<void>
  onReconnect?: () => void
  /** Decision year for a showcase case, from the showcase list. */
  year?: number | null
}) {
  const running = r.status === 'running' || r.status === 'queued' || streaming
  const story: CaseStory | undefined = caseStory(r.showcase_slug) ?? caseStory(STORY_ALIAS[r.showcase_slug ?? ''])
  const names = displayNames(r, story?.short)
  const ev = r.evidence
  const routed = r.routing?.analyses
  const context = r.routing?.context_only ?? []
  const contextFactors = Object.keys(FACTOR_ANALYSIS).filter((f) => context.includes(FACTOR_ANALYSIS[f]))
  const title = story?.short ?? (r.extraction ? `${names.senior} v. ${names.junior}` : undefined)
  const desktop = useMediaQuery(DESKTOP)
  const nav = useQueryNav()

  useEffect(() => {
    document.title = `${title ?? (running ? 'Analyzing' : 'Run')} · Tea Rose`
  }, [title, running])

  // "How we got here" is collapsed on case pages and open while a live run streams.
  const { setHowOpen } = nav
  const wasRunning = useRef(false)
  useEffect(() => {
    if (live && running && !wasRunning.current) setHowOpen(true)
    wasRunning.current = running
  }, [live, running, setHowOpen])

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

  const [traceRequest, setTraceRequest] = useState(0)
  const openTrace = () => {
    if (desktop) setTraceRequest((n) => n + 1)
    else setSnap('half')
  }

  const memoExpected = running && !!r.routing
  const showQuestions = !!(r.resolution || ev) || running

  usePublishSections(
    [
      { id: 'case', label: 'The case', show: true },
      { id: 'read', label: 'Preliminary read', show: !!r.memo?.preliminary_read },
      { id: 'bottom-line', label: 'Bottom line', show: !!r.memo || memoExpected },
      { id: 'questions', label: 'Three questions', show: showQuestions },
      { id: 'meaning', label: 'What it means', show: !!r.memo || running },
      { id: 'limits', label: 'Limits', show: true },
      { id: 'how', label: 'How we got here', show: true },
    ]
      .filter((s) => s.show)
      .map(({ id, label }) => ({ id, label })),
  )

  function questionFor(q: Question): ReactNode {
    const has = q === 'overlap' ? !!(ev?.overlap || ev?.bridging) : !!ev?.[q]
    if (has) {
      let panel: ReactNode
      switch (q) {
        case 'overlap':
          panel = <OverlapPanel ev={ev!.overlap} bridging={ev!.bridging} resolution={r.resolution} names={names} />
          break
        case 'fame':
          panel = <FamePanel ev={ev!.fame!} senior={names.senior} proxy={r.resolution?.senior_proxy} />
          break
        case 'zone':
          panel = <ZonePanel ev={ev!.zone!} senior={names.senior} junior={names.junior} juniorProxy={r.resolution?.junior_proxy} />
          break
      }
      const forContext = ANALYSES_FOR[q].filter((a) => routed?.includes(a) ?? true)
      const isContext = forContext.length > 0 && forContext.every((a) => context.includes(a))
      return (
        <Slot state="panel">
          <ContextOnly.Provider value={isContext}>{panel}</ContextOnly.Provider>
        </Slot>
      )
    }
    const wanted = ANALYSES_FOR[q]
    if (routed && !wanted.some((a) => routed.includes(a)))
      return (
        <Slot state="notrun">
          <NotRun title={QUESTION_LABEL[q]} why={r.routing?.rationale[q]} />
        </Slot>
      )
    if (running)
      return (
        <Slot state="skeleton">
          <SkeletonCard lines={4} tall label={`${QUESTION_LABEL[q]} Waiting for the scores`} />
        </Slot>
      )
    if (routed)
      return (
        <Slot state="noevidence">
          <NotRun title={QUESTION_LABEL[q]} why="no evidence was produced; see the agent trace" />
        </Slot>
      )
    return null
  }

  // Bands alternate white and gray in the order they appear. While a run streams every band that
  // will exist is reserved (skeleton), so the alternation never flips under the reader.
  const bands: { key: string; id?: string; label?: string; className?: string; wide?: boolean; node: ReactNode }[] = []

  // 1 + 2: the header, the preliminary read and the bottom line
  bands.push({
    key: 'case',
    id: 'case',
    className: 'page-top run-open',
    node: (
      <>
        {r.status === 'failed' && (
          <div className="run-open__notice">
            <Notice kind="error" title="The run failed.">
              {r.error ?? 'See the agent trace for the last step that ran.'} Partial results are shown below.
            </Notice>
          </div>
        )}
        <Slot state={r.extraction ? 'case' : running ? 'case-skeleton' : 'case-input'}>
          {r.extraction ? (
            <CaseOpening
              extraction={r.extraction}
              names={names}
              story={story}
              year={year}
              readLine={r.memo?.read_line}
              oneSided={r.memo?.preliminary_read?.one_sided_input}
              hasReadCard={!!r.memo?.preliminary_read}
            >
              <Toolbar live={live} r={r} running={running} />
            </CaseOpening>
          ) : (
            <div className="opening">
              <p className="eyebrow">{running ? 'New analysis' : 'Input'}</p>
              <h1 className="t-headline opening__title">{running ? 'Reading the document' : 'Run'}</h1>
              <Toolbar live={live} r={r} running={running} />
              {running ? <SkeletonCard lines={3} label="Reading the document" /> : r.input_excerpt && <p className="t-subtitle opening__summary">{r.input_excerpt}</p>}
            </div>
          )}
        </Slot>
        <PreliminaryReadCard memo={r.memo} names={names} docType={r.extraction?.document_type} contextFactors={contextFactors} />
        {story && r.memo && <CourtReveal story={story} r={r} names={names} />}
        <BottomLine memo={r.memo} expected={memoExpected} names={names} contextFactors={contextFactors} />
      </>
    ),
  })

  // 3: the three questions
  if (showQuestions) {
    bands.push({
      key: 'questions',
      id: 'questions',
      className: 'band--tight evidence-intro',
      node: (
        <div className="band__head band__head--center evidence-intro__head">
          <p className="eyebrow">The evidence</p>
          <h2 className="t-display evidence-intro__title">The three questions.</h2>
          <p className="t-subtitle">
            The questions a judge asks about customers. Every score is on the same 0 to 100 scale, and 75 or more counts as high. Code computed them from Qloo’s
            answers (Qloo is a taste graph: anonymised data on what audiences like across brands, music and places); no model touches these numbers.
          </p>
        </div>
      ),
    })
    for (const q of QUESTIONS) {
      const node = questionFor(q)
      if (node) bands.push({ key: `q-${q}`, wide: true, label: QUESTION_LABEL[q], className: 'question-band', node })
    }
  }

  // 4: what this means
  if (r.memo || running)
    bands.push({
      key: 'meaning',
      id: 'meaning',
      className: 'meaning-band',
      node: (
        <>
          <Slot state={r.memo ? 'memo' : 'memo-skeleton'}>
            {r.memo ? <MemoMeaning memo={r.memo} title={title} names={names} onQuery={nav.goToQuery} /> : <SkeletonCard lines={6} tall label="Writing the memo" />}
          </Slot>
          {live && onFollowup && r.memo && <FollowupBox running={running} onAsk={onFollowup} />}
        </>
      ),
    })

  // 5: what it cannot tell you
  bands.push({ key: 'limits', id: 'limits', node: <MemoLimits memo={r.memo} /> })

  // 6: how we got here
  const n = r.memo?.appendix_queries.length ?? 0
  bands.push({
    key: 'how',
    id: 'how',
    className: 'how-band',
    node: (
      <>
        <BandHead
          eyebrow="More detail"
          title="How we got here."
          sub="What the model read, which Qloo entities it chose and why, every query that was sent, and the step-by-step trace."
        />
        <div className="how__actions no-print">
          <button type="button" className="btn btn--sm" onClick={openTrace}>
            Open the agent trace
          </button>
        </div>
        <Disclosure
          className="how__disclosure"
          open={nav.howOpen}
          onOpenChange={nav.setHowOpen}
          summary={
            <>
              {nav.howOpen ? 'Hide' : 'Show'} the reading, the brands chosen{n ? ` and the ${n} Qloo queries` : ' and the queries'}
            </>
          }
        >
          <div className="how__body">
            <Slot state={r.extraction ? 'parties' : 'parties-skeleton'}>
              {r.extraction ? <CaseParties extraction={r.extraction} routing={r.routing} /> : running ? <SkeletonCard lines={4} label="Reading the document" /> : null}
            </Slot>
            <Slot state={r.resolution ? 'resolution' : 'resolution-skeleton'}>
              {r.resolution ? <ResolutionCard resolution={r.resolution} /> : running ? <SkeletonCard lines={3} label="Finding the brands in Qloo" /> : null}
            </Slot>
            {r.memo && <QueryAppendix queries={r.memo.appendix_queries} open={nav.appendixOpen} onOpenChange={nav.setAppendixOpen} />}
          </div>
        </Disclosure>
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
          Run <code>{r.run_id}</code> · {new Date(r.created_at).toLocaleString()} · Tea Rose produces early evidence for counsel, not a consumer survey and not a
          verdict.
        </p>
      </div>

      <TraceAnnouncer events={events} status={r.status} streaming={streaming} />

      {desktop ? (
        <TraceDock
          events={events}
          status={r.status}
          streaming={streaming}
          connection={connection}
          onReconnect={onReconnect}
          defaultOpen={live && running}
          openRequest={traceRequest}
        />
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
