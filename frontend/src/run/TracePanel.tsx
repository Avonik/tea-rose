import { motion, useReducedMotion } from 'motion/react'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { IconCheck, IconChevronDown, IconCode, IconDiamond, IconDot, IconError, IconInfo, IconTool, IconWarn } from '../components/icons'
import { Disclosure } from '../components/ui'
import { formatParams, humanize, shortId, timeOf } from '../lib/format'
import type { Connection } from '../lib/useLiveRun'
import { Reveal } from '../motion/Reveal'
import { fade, spring } from '../motion/springs'
import { PIPELINE, type RunStatus, type TraceEvent } from '../types'
import './trace.css'

type NodeState = 'pending' | 'active' | 'done' | 'failed'

export function nodeStates(events: TraceEvent[], status: RunStatus): Record<string, NodeState> {
  const out: Record<string, NodeState> = {}
  for (const n of [...PIPELINE, 'followup']) out[n] = 'pending'
  for (const e of events) {
    if (e.type === 'node_started' || e.type === 'tool_call' || e.type === 'decision') {
      if (out[e.node] !== 'done') out[e.node] = 'active'
    }
    if (e.type === 'node_finished') out[e.node] = 'done'
    if (e.type === 'run_failed') out[e.node] = 'failed'
  }
  // Follow-ups re-run nodes after they were done; once the run is finished nothing is active.
  if (status === 'finished') for (const k of Object.keys(out)) if (out[k] === 'active') out[k] = 'done'
  return out
}

/** Everything the collapsed trace pill, the sheet header and the panel say about progress. */
export function traceProgress(events: TraceEvent[], status: RunStatus) {
  const states = nodeStates(events, status)
  const hasFollowup = events.some((e) => e.node === 'followup')
  const steps = hasFollowup ? [...PIPELINE, 'followup'] : [...PIPELINE]
  const doneCount = PIPELINE.filter((n) => states[n] === 'done').length
  const active = steps.find((n) => states[n] === 'active')
  const toolCalls = events.filter((e) => e.type === 'tool_call').length
  const warnings = events.filter((e) => e.type === 'warning').length
  const calls = `${toolCalls} Qloo call${toolCalls === 1 ? '' : 's'}`
  const stepNo = Math.min(PIPELINE.length, doneCount + (active ? 1 : 0))
  const summary = active
    ? `Step ${Math.max(1, stepNo)} of ${PIPELINE.length} · ${humanize(active)} · ${calls}`
    : status === 'failed'
      ? `Failed after ${doneCount} of ${PIPELINE.length} steps · ${events.length} events`
      : `${events.length} event${events.length === 1 ? '' : 's'} · ${calls}`
  return { states, steps, doneCount, active, toolCalls, warnings, summary, calls }
}

interface Row {
  ev: TraceEvent
  result?: TraceEvent
  showNode?: boolean
}

/** Pair each tool_call with its tool_result (same query_id, or the next result) so a call reads as one row. */
function toRows(events: TraceEvent[]): Row[] {
  const rows: Row[] = []
  const used = new Set<number>()
  events.forEach((ev, i) => {
    if (used.has(ev.seq)) return
    if (ev.type === 'tool_call') {
      const qid = ev.data.query_id
      let res: TraceEvent | undefined
      for (let j = i + 1; j < events.length; j++) {
        const c = events[j]
        if (c.type === 'tool_result' && !used.has(c.seq) && (qid == null || c.data.query_id == null || c.data.query_id === qid)) {
          res = c
          break
        }
        if (c.type === 'tool_call' && qid == null) break
      }
      if (res) used.add(res.seq)
      rows.push({ ev, result: res })
    } else rows.push({ ev })
  })
  rows.forEach((r, i) => (r.showNode = i === 0 || rows[i - 1].ev.node !== r.ev.node))
  return rows
}

function TypeIcon({ type }: { type: TraceEvent['type'] }) {
  switch (type) {
    case 'tool_call':
    case 'tool_result':
      return <IconTool size={13} />
    case 'decision':
      return <IconDiamond size={12} />
    case 'warning':
      return <IconWarn size={13} />
    case 'run_failed':
      return <IconError size={13} />
    case 'node_finished':
    case 'run_finished':
      return <IconCheck size={13} />
    case 'note':
      return <IconInfo size={13} />
    default:
      return <IconDot size={13} />
  }
}

function ToolRow({ ev, result }: Row) {
  const endpoint = String(ev.data.endpoint ?? (ev.data.query as { endpoint?: string } | undefined)?.endpoint ?? ev.data.tool ?? '')
  const params = (ev.data.params ?? (ev.data.query as { params?: Record<string, unknown> } | undefined)?.params ?? ev.data.args ?? {}) as Record<string, unknown>
  const count = result?.data.result_count as number | undefined
  const cache = result?.data.cache_hit === true
  const ms = result?.data.elapsed_ms as number | undefined
  const qid = (ev.data.query_id as string | undefined) ?? null
  return (
    <Disclosure
      className="trace-tool"
      printOpen={false}
      summary={
        <span className="trace-tool__main">
          <span className="trace-row__title">{ev.title}</span>
          <span className="trace-tool__meta">
            {qid && <span className="trace-tool__qid num">{qid}</span>}
            <code className="trace-tool__endpoint">{endpoint}</code>
            {result ? (
              <span className={`trace-tool__result num ${count === 0 ? 'is-empty' : ''}`}>
                {count != null ? `${count} result${count === 1 ? '' : 's'}` : result.title}
                {cache && <span className="badge">cache</span>}
              </span>
            ) : (
              <span className="trace-tool__result">
                <span className="spinner spinner--sm" aria-hidden="true" /> waiting
              </span>
            )}
          </span>
        </span>
      }
    >
      <div className="trace-tool__body">
        {typeof ev.data.tool === 'string' && (
          <div className="caption tertiary">
            Tool <code>{ev.data.tool}</code>
          </div>
        )}
        <dl className="kv trace-tool__kv">
          {formatParams(params).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd className="mono" title={v}>
                {v.split(',').map(shortId).join(', ')}
              </dd>
            </div>
          ))}
        </dl>
        {result && (
          <div className="caption tertiary num">
            {result.title}
            {ms != null && ` · ${ms} ms`}
          </div>
        )}
      </div>
    </Disclosure>
  )
}

/** Dots on a line. Done dots fill, the active one breathes, the line fills to the last finished step. */
export function Stepper({ steps, states, active, doneCount }: { steps: string[]; states: Record<string, NodeState>; active?: string; doneCount: number }) {
  const reduce = useReducedMotion()
  const last = steps.reduce((acc, n, i) => (states[n] === 'done' || states[n] === 'failed' || states[n] === 'active' ? i : acc), -1)
  const fill = steps.length > 1 ? Math.max(0, last) / (steps.length - 1) : 0
  return (
    <div
      className="stepper"
      role="progressbar"
      aria-label="Pipeline progress"
      aria-valuemin={0}
      aria-valuemax={PIPELINE.length}
      aria-valuenow={doneCount}
      aria-valuetext={active ? `${humanize(active)} running, ${doneCount} of ${PIPELINE.length} steps done` : `${doneCount} of ${PIPELINE.length} steps done`}
    >
      <div className="stepper__row">
        <span className="stepper__line" aria-hidden="true">
          <motion.span className="stepper__fill" initial={false} animate={{ scaleX: fill }} transition={reduce ? fade : spring} />
        </span>
        {steps.map((n) => {
          const st = states[n]
          return (
            <span key={n} className="stepper__dot" data-state={st} title={humanize(n)} aria-hidden="true">
              {st === 'active' && !reduce && (
                <motion.span
                  className="stepper__halo"
                  animate={{ opacity: [0.5, 0, 0.5], scale: [1, 1.8, 1] }}
                  transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
                />
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}

export default function TracePanel({
  events,
  status,
  streaming,
  connection,
  onReconnect,
  compact = false,
  hideStepper = false,
  onCollapse,
}: {
  events: TraceEvent[]
  status: RunStatus
  streaming: boolean
  connection?: Connection
  onReconnect?: () => void
  /** Stepper and summary only (used as the sheet header on phones). */
  compact?: boolean
  /** Body without the stepper (the sheet header already shows it). */
  hideStepper?: boolean
  /** Desktop dock: render a collapse control in the header. */
  onCollapse?: () => void
}) {
  const { states, steps, doneCount, active, warnings, summary, calls } = useMemo(() => traceProgress(events, status), [events, status])
  const rows = useMemo(() => toRows(events), [events])
  const listRef = useRef<HTMLOListElement>(null)
  const stick = useRef(true)
  // Only rows that arrive after mount animate in; a replayed or static trace renders still.
  const [baselineSeq] = useState(() => (events.length ? events[events.length - 1].seq : 0))

  // Follow the tail while live, unless the reader has scrolled up.
  useLayoutEffect(() => {
    const el = listRef.current
    if (!el || !streaming || !stick.current) return
    el.scrollTop = el.scrollHeight
  }, [rows.length, streaming])

  if (compact)
    return (
      <div className="trace trace--compact">
        <p className="trace__summary num">
          {streaming && <span className="live-dot" aria-hidden="true" />}
          <span className="trace__summary-title">Agent trace</span>
          <span className="secondary"> · {summary}</span>
          {warnings > 0 && <span className="secondary">{` · ${warnings} warning${warnings === 1 ? '' : 's'}`}</span>}
        </p>
        <Stepper steps={steps} states={states} doneCount={doneCount} active={active} />
      </div>
    )

  return (
    <section className="trace" aria-labelledby="trace-title">
      <div className="trace__head">
        <h2 id="trace-title" className="trace__title">
          Agent trace
        </h2>
        {streaming ? (
          <span className="live-pill">
            <span className="live-dot" aria-hidden="true" /> Live
          </span>
        ) : status === 'failed' ? (
          <span className="chip chip--sm">
            <span className="dot" style={{ background: 'var(--error)' }} aria-hidden="true" />
            Failed
          </span>
        ) : (
          <span className="caption tertiary num">{events.length} events</span>
        )}
        {onCollapse && (
          <button type="button" className="trace__collapse btn btn--icon btn--sm" onClick={onCollapse} aria-label="Collapse the agent trace">
            <IconChevronDown size={16} />
          </button>
        )}
      </div>

      {!hideStepper && (
        <div className="trace__progress">
          <Stepper steps={steps} states={states} active={active} doneCount={doneCount} />
          <p className="trace__active caption num">
            {active ? (
              <>
                <strong>{humanize(active)}</strong>
                <span className="secondary">{` · step ${Math.max(1, Math.min(PIPELINE.length, doneCount + 1))} of ${PIPELINE.length}`}</span>
              </>
            ) : (
              <span className="secondary">
                {doneCount} of {PIPELINE.length} steps done
              </span>
            )}
          </p>
        </div>
      )}

      <p className="trace__counts caption tertiary num">
        {calls}
        {warnings > 0 && ` · ${warnings} warning${warnings === 1 ? '' : 's'}`}
        {active && streaming && ` · ${humanize(active)}…`}
      </p>

      {connection === 'retrying' && (
        <p className="trace__conn caption" role="status">
          <span className="spinner spinner--sm" aria-hidden="true" /> Reconnecting to the live stream…
        </p>
      )}
      {connection === 'lost' && (
        <p className="trace__conn caption" role="alert">
          <IconWarn size={14} /> Lost the live stream.{' '}
          <button type="button" className="linklike" onClick={onReconnect}>
            Reconnect
          </button>
        </p>
      )}

      <ol
        id="trace-list"
        className="trace__list"
        ref={listRef}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
        }}
        aria-live="off"
      >
        {events.length === 0 && (
          <li className="trace__empty caption tertiary">{streaming || status === 'running' || status === 'queued' ? 'Waiting for the first event…' : 'No trace recorded.'}</li>
        )}
        {rows.map(({ ev, result, showNode }) => {
          const fresh = ev.seq > baselineSeq
          const body = (
            <>
              {showNode && (
                <div className="trace-row__node">
                  <span className="trace-row__nodename">
                    {ev.node === 'score' && <IconCode size={11} />}
                    {humanize(ev.node)}
                  </span>
                  <span className="caption tertiary num">{timeOf(ev.ts)}</span>
                </div>
              )}
              <div className="trace-row__body">
                <span className={`trace-row__icon trace-row__icon--${ev.type}`} aria-hidden="true">
                  <TypeIcon type={ev.type} />
                </span>
                {ev.type === 'tool_call' ? (
                  <ToolRow ev={ev} result={result} />
                ) : (
                  <div className="trace-row__text">
                    <span className="sr-only">{humanize(ev.type)}: </span>
                    <span className="trace-row__title">{ev.title}</span>
                    {ev.detail && <span className="trace-row__detail">{ev.detail}</span>}
                  </div>
                )}
              </div>
            </>
          )
          return (
            <li key={ev.seq} className={`trace-row trace-row--${ev.type}`}>
              {fresh ? (
                <Reveal from="below" quick>
                  {body}
                </Reveal>
              ) : (
                body
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

/**
 * Announces step changes only, not every event, so screen readers are not flooded. Rendered once by
 * the run view, outside the trace, so it speaks even while the trace is collapsed.
 */
export function TraceAnnouncer({ events, status, streaming }: { events: TraceEvent[]; status: RunStatus; streaming: boolean }) {
  const { active } = useMemo(() => traceProgress(events, status), [events, status])
  return (
    <div className="sr-only" aria-live="polite" role="status">
      {streaming && active ? `${humanize(active)} running` : status === 'finished' ? 'Run finished' : status === 'failed' ? 'Run failed' : ''}
    </div>
  )
}
