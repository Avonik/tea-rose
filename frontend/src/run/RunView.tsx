import { Link } from 'react-router-dom'
import { IconBack, IconPrint } from '../components/icons'
import { Notice, SkeletonCard } from '../components/ui'
import { sideNames } from '../lib/format'
import type { Connection } from '../lib/useLiveRun'
import type { Analysis, AnalysisResult, TraceEvent } from '../types'
import BridgingPanel from './BridgingPanel'
import CaseHeader from './CaseHeader'
import FamePanel from './FamePanel'
import FollowupBox from './FollowupBox'
import MemoView from './MemoView'
import OverlapPanel from './OverlapPanel'
import ResolutionCard from './ResolutionCard'
import TracePanel from './TracePanel'
import ZonePanel from './ZonePanel'
import './run.css'

const EVIDENCE_LABEL: Record<Analysis, string> = {
  overlap: 'Shared purchasers',
  bridging: 'Bridging the gap',
  fame: 'Fame',
  zone: 'Zone of reputation',
}

function Pending({ label }: { label: string }) {
  return (
    <div className="pending" aria-busy="true">
      <p className="caption faint pending__label">
        <span className="spinner" aria-hidden="true" /> {label}
      </p>
      <SkeletonCard lines={3} />
    </div>
  )
}

function NotRun({ analysis, why }: { analysis: Analysis; why?: string }) {
  return (
    <div className="not-run">
      <strong>{EVIDENCE_LABEL[analysis]}</strong>
      <span className="faint"> · not measured{why ? `: ${why}` : ''}</span>
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
  const order: Analysis[] = ['overlap', 'bridging', 'fame', 'zone']
  const title = r.extraction ? `${names.senior} v. ${names.junior}` : undefined

  function evidenceFor(a: Analysis) {
    if (ev?.[a]) {
      switch (a) {
        case 'overlap':
          return <OverlapPanel key={a} ev={ev.overlap!} resolution={r.resolution} names={names} />
        case 'bridging':
          return <BridgingPanel key={a} ev={ev.bridging!} resolution={r.resolution} senior={names.senior} />
        case 'fame':
          return <FamePanel key={a} ev={ev.fame!} senior={names.senior} />
        case 'zone':
          return <ZonePanel key={a} ev={ev.zone!} senior={names.senior} junior={names.junior} juniorIsProxy={!!r.resolution?.junior_proxy} />
      }
    }
    if (routed && !routed.includes(a)) return <NotRun key={a} analysis={a} why={r.routing?.rationale[a]} />
    if (running && (!routed || routed.includes(a))) return <Pending key={a} label={`${EVIDENCE_LABEL[a]}: waiting for scores`} />
    if (routed?.includes(a)) return <NotRun key={a} analysis={a} why="no evidence was produced; see the trace" />
    return null
  }

  const sections = [
    { id: 'case', label: 'Case', show: !!r.extraction },
    { id: 'resolution', label: 'Parties in Qloo', show: !!r.resolution },
    { id: 'evidence', label: 'Evidence', show: !!ev },
    { id: 'memo', label: 'Memo', show: !!r.memo },
  ].filter((s) => s.show)

  return (
    <div className="run page-enter">
      <div className="run__bar container-wide no-print">
        <Link to={live ? '/analyze' : '/'} className="btn btn--quiet btn--sm run__back">
          <IconBack size={15} /> {live ? 'New analysis' : 'All cases'}
        </Link>
        <div className="run__status">
          {running ? (
            <span className="chip chip--accent">
              <span className="spinner" aria-hidden="true" /> Running
            </span>
          ) : r.status === 'failed' ? (
            <span className="chip chip--warn">Failed</span>
          ) : (
            <span className="chip chip--ok">Finished</span>
          )}
          <span className="chip chip--outline" title={r.mode === 'fixture' ? 'Served from recorded fixtures or cache' : 'Live Qloo API'}>
            {r.showcase_slug ? 'Pre-computed' : r.mode === 'fixture' ? 'Fixture data' : 'Live Qloo'}
          </span>
        </div>
        <button type="button" className="btn btn--sm" onClick={() => window.print()} disabled={!r.memo}>
          <IconPrint size={15} /> Print memo
        </button>
      </div>

      <div className="run__grid container-wide">
        <aside className="run__trace no-print" aria-label="Agent trace">
          <TracePanel events={events} status={r.status} streaming={streaming} connection={connection} onReconnect={onReconnect} />
        </aside>

        <div className="run__main">
          {sections.length > 1 && (
            <nav className="toc no-print" aria-label="On this page">
              {sections.map((s) => (
                <a key={s.id} href={`#${s.id}`}>
                  {s.label}
                </a>
              ))}
            </nav>
          )}

          {r.status === 'failed' && (
            <Notice kind="error">
              <strong>The run failed.</strong> {r.error ?? 'See the trace for the last step that ran.'} Partial results are shown
              below.
            </Notice>
          )}

          {r.extraction ? <CaseHeader extraction={r.extraction} routing={r.routing} /> : running ? <Pending label="Reading the document" /> : null}

          {!r.extraction && !running && r.input_excerpt && (
            <section className="card">
              <p className="eyebrow">Input</p>
              <p className="footnote muted">{r.input_excerpt}</p>
            </section>
          )}

          {r.resolution ? <ResolutionCard resolution={r.resolution} /> : running && r.extraction ? <Pending label="Resolving brands in Qloo" /> : null}

          {(r.resolution || ev) && (
            <section className="evidence-board" id="evidence" aria-labelledby="evidence-title">
              <div className="evidence-board__head">
                <h2 id="evidence-title">Evidence</h2>
                <p className="muted footnote">Computed by code from the queries in the appendix. No model touches these numbers.</p>
              </div>
              {order.map(evidenceFor)}
            </section>
          )}

          {r.memo ? <MemoView memo={r.memo} title={title} /> : running && ev ? <Pending label="Writing the memo" /> : null}

          {live && onFollowup && r.memo && <FollowupBox running={running} onAsk={onFollowup} />}

          <p className="run__foot caption faint">
            Run <code>{r.run_id}</code> · {new Date(r.created_at).toLocaleString()} · Tea Rose produces triage evidence, not a
            consumer survey.
          </p>
        </div>
      </div>
    </div>
  )
}
