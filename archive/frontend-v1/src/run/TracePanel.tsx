import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { IconCheck, IconChevron, IconDiamond, IconDot, IconError, IconInfo, IconTool, IconWarn } from '../components/icons'
import { formatParams, humanize, shortId, timeOf } from '../lib/format'
import type { Connection } from '../lib/useLiveRun'
import { PIPELINE, type RunStatus, type TraceEvent } from '../types'

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
      return <IconTool size={14} />
    case 'decision':
      return <IconDiamond size={13} />
    case 'warning':
      return <IconWarn size={14} />
    case 'run_failed':
      return <IconError size={14} />
    case 'node_finished':
    case 'run_finished':
      return <IconCheck size={14} />
    case 'note':
      return <IconInfo size={14} />
    default:
      return <IconDot size={14} />
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
    <details className="trace-tool disclosure">
      <summary>
        <IconChevron className="disclosure__chev" size={12} />
        <span className="trace-tool__main">
          <span className="trace-row__title">{ev.title}</span>
          <span className="trace-tool__meta">
            {qid && <span className="trace-tool__qid">{qid}</span>}
            <code className="trace-tool__endpoint">{endpoint}</code>
            {result ? (
              <span className={`trace-tool__result ${count === 0 ? 'is-empty' : ''}`}>
                {count != null ? `${count} result${count === 1 ? '' : 's'}` : result.title}
                {cache && ' · cache'}
              </span>
            ) : (
              <span className="trace-tool__result is-pending">
                <span className="spinner" aria-hidden="true" /> waiting
              </span>
            )}
          </span>
        </span>
      </summary>
      <div className="trace-tool__body">
        {typeof ev.data.tool === 'string' && (
          <div className="caption faint">
            Tool <code>{ev.data.tool}</code>
          </div>
        )}
        <dl className="params">
          {formatParams(params).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd title={v}>{v.split(',').map(shortId).join(', ')}</dd>
            </div>
          ))}
        </dl>
        {result && (
          <div className="caption faint num">
            {result.title}
            {ms != null && ` · ${ms} ms`}
          </div>
        )}
      </div>
    </details>
  )
}

export default function TracePanel({
  events,
  status,
  streaming,
  connection,
  onReconnect,
}: {
  events: TraceEvent[]
  status: RunStatus
  streaming: boolean
  connection?: Connection
  onReconnect?: () => void
}) {
  const states = useMemo(() => nodeStates(events, status), [events, status])
  const rows = useMemo(() => toRows(events), [events])
  const hasFollowup = events.some((e) => e.node === 'followup')
  const steps = hasFollowup ? [...PIPELINE, 'followup'] : [...PIPELINE]
  const doneCount = PIPELINE.filter((n) => states[n] === 'done').length
  const active = steps.find((n) => states[n] === 'active')
  const listRef = useRef<HTMLOListElement>(null)
  const stick = useRef(true)
  // On narrow screens the list collapses unless live; the reader's own choice wins.
  const [userCollapsed, setUserCollapsed] = useState<boolean | null>(null)
  const collapsed = userCollapsed ?? !streaming
  // Only rows that arrive after mount animate in; a replayed or static trace renders still.
  const [baselineSeq] = useState(() => (events.length ? events[events.length - 1].seq : 0))
  const toolCalls = events.filter((e) => e.type === 'tool_call').length
  const warnings = events.filter((e) => e.type === 'warning').length

  // Follow the tail while live, unless the reader has scrolled up.
  useLayoutEffect(() => {
    const el = listRef.current
    if (!el || !streaming || !stick.current) return
    el.scrollTop = el.scrollHeight
  }, [rows.length, streaming])


  return (
    <section className="trace" aria-labelledby="trace-title" data-collapsed={collapsed}>
      <div className="trace__head">
        <div className="trace__heading">
          <h2 id="trace-title" className="trace__title">
            Agent trace
          </h2>
          {streaming ? (
            <span className="live-dot" aria-label="Live">
              Live
            </span>
          ) : status === 'failed' ? (
            <span className="chip chip--warn">Failed</span>
          ) : null}
        </div>
        <button
          type="button"
          className="btn btn--quiet btn--sm trace__toggle"
          aria-expanded={!collapsed}
          aria-controls="trace-list"
          onClick={() => setUserCollapsed(!collapsed)}
        >
          {collapsed ? 'Show' : 'Hide'} {events.length} events
        </button>
      </div>

      <div
        className="steps"
        role="progressbar"
        aria-label="Pipeline progress"
        aria-valuemin={0}
        aria-valuemax={PIPELINE.length}
        aria-valuenow={doneCount}
        aria-valuetext={active ? `${humanize(active)} running, ${doneCount} of ${PIPELINE.length} steps done` : `${doneCount} of ${PIPELINE.length} steps done`}
      >
        {steps.map((n) => (
          <div key={n} className="steps__item" data-state={states[n]} data-node={n}>
            <span className="steps__bar" />
            <span className="steps__label">{humanize(n)}</span>
          </div>
        ))}
      </div>
      <p className="trace__summary caption faint num">
        {toolCalls} Qloo call{toolCalls === 1 ? '' : 's'}
        {warnings > 0 && ` · ${warnings} warning${warnings === 1 ? '' : 's'}`}
        {active && streaming && ` · ${humanize(active)}…`}
      </p>

      {connection === 'retrying' && (
        <p className="trace__conn caption" role="status">
          <span className="spinner" aria-hidden="true" /> Reconnecting to the live stream…
        </p>
      )}
      {connection === 'lost' && (
        <p className="trace__conn caption" role="alert">
          Lost the live stream.{' '}
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
          <li className="trace__empty caption faint">{streaming || status === 'running' || status === 'queued' ? 'Waiting for the first event…' : 'No trace recorded.'}</li>
        )}
        {rows.map(({ ev, result, showNode }) => {
          const fresh = ev.seq > baselineSeq
          return (
            <li key={ev.seq} className={`trace-row trace-row--${ev.type}`} data-fresh={fresh || undefined}>
              {showNode && (
                <div className="trace-row__node">
                  <span className={`node-badge node-badge--${ev.node}`}>{humanize(ev.node)}</span>
                  <span className="faint caption num">{timeOf(ev.ts)}</span>
                </div>
              )}
              <div className="trace-row__body">
                <span className="trace-row__icon" aria-hidden="true">
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
            </li>
          )
        })}
      </ol>
      {/* Announce step changes only, not every event, so screen readers are not flooded. */}
      <div className="sr-only" aria-live="polite">
        {streaming && active ? `${humanize(active)} running` : status === 'finished' ? 'Run finished' : ''}
      </div>
    </section>
  )
}
