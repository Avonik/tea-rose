import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useId, useMemo, useState, type MouseEvent } from 'react'
import { IconChevron, IconWarn } from '../components/icons'
import { ConfidenceMeter, LeanChip, LEAN_LABEL } from '../components/ui'
import { FIXED_LIMITATIONS } from '../content/limitations'
import { factorLabel, formatParams, shortId } from '../lib/format'
import { fade, springQuick } from '../motion/springs'
import type { FactorLean, Memo, QlooQuery } from '../types'
import './memo.css'

marked.setOptions({ gfm: true, breaks: false })

/** Turn "Q12" citations into links to the appendix rows, then render and sanitize. */
function renderMarkdown(md: string): string {
  const linked = md.replace(/(^|[^\w[#-])Q(\d{1,3})\b(?!\])/g, (_m, pre: string, n: string) => `${pre}[Q${n}](#query-${n})`)
  const html = marked.parse(linked, { async: false })
  return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] })
}

function Markdown({ md }: { md: string }) {
  const html = useMemo(() => renderMarkdown(md), [md])
  return <div className="prose" dangerouslySetInnerHTML={{ __html: html }} />
}

// ------------------------------------------------------------------ reference navigation

const PANEL_FOR_PREFIX: Record<string, string> = {
  overlap: 'overlap',
  bridging: 'bridging',
  fame: 'fame',
  zone: 'zone',
}

/** Evidence panel id for a field ref such as "overlap.symmetric_percentile"; null if unknown. */
export function panelForRef(ref: string): string | null {
  const prefix = ref.split('.')[0]
  return PANEL_FOR_PREFIX[prefix] ?? null
}

function flash(el: HTMLElement) {
  el.classList.remove('is-flash')
  void el.offsetWidth
  el.classList.add('is-flash')
  window.setTimeout(() => el.classList.remove('is-flash'), 1300)
}

function scrollFlash(id: string, reduce: boolean, block: ScrollLogicalPosition = 'center') {
  const el = document.getElementById(id)
  if (!el) return false
  requestAnimationFrame(() => {
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block })
    flash(el)
    history.replaceState(null, '', `#${id}`)
  })
  return true
}

function RefChip({ r, onQuery, reduce }: { r: string; onQuery: (n: string) => void; reduce: boolean }) {
  const m = /^Q(\d+)$/.exec(r)
  if (m)
    return (
      <a
        className="ref-chip pressable"
        href={`#query-${m[1]}`}
        onClick={(e) => {
          e.preventDefault()
          onQuery(m[1])
        }}
      >
        {r}
      </a>
    )
  const panel = panelForRef(r)
  if (!panel) return <code className="ref-chip ref-chip--field">{r}</code>
  return (
    <button type="button" className="ref-chip ref-chip--field pressable" title={`Jump to the ${panel} evidence`} onClick={() => scrollFlash(panel, reduce, 'start')}>
      {r}
    </button>
  )
}

// ------------------------------------------------------------------ appendix

function source(q: QlooQuery) {
  if (q.fixture_file) return { label: 'Fixture', title: q.fixture_file }
  if (q.cache_hit) return { label: 'Cache', title: 'Served from the local response cache' }
  return { label: 'Live', title: 'Live Qloo API call' }
}

export function QueryAppendix({
  queries,
  open,
  onOpenChange,
}: {
  queries: QlooQuery[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const reduce = useReducedMotion()
  const bodyId = useId()
  const n = queries.length
  const body = (
    <div className="appendix__inner">
      {n === 0 ? (
        <p className="group__row caption tertiary">No queries were recorded.</p>
      ) : (
        <ol className="appendix__list" aria-label="Logged Qloo queries">
          {queries.map((q, i) => {
            const s = source(q)
            return (
              <li key={i} id={`query-${i + 1}`} className="group__row group__row--top group__sep appendix__row">
                <span className="appendix__n num">Q{i + 1}</span>
                <span className="group__main appendix__main">
                  <code className="appendix__endpoint">{q.endpoint}</code>
                  <ul className="appendix__params">
                    {formatParams(q.params).map(([k, v]) => (
                      <li key={k}>
                        <span className="tertiary">{k}=</span>
                        <span title={v}>{v.split(',').map(shortId).join(',')}</span>
                      </li>
                    ))}
                  </ul>
                </span>
                <span className="appendix__meta">
                  <span className="num appendix__results">
                    {q.result_count ?? '–'} <span className="caption tertiary">results</span>
                  </span>
                  <span className="badge" title={s.title}>
                    {s.label}
                  </span>
                  {q.elapsed_ms != null && <span className="caption tertiary num">{q.elapsed_ms} ms</span>}
                  {q.status != null && q.status !== 200 && <span className="caption num appendix__status">HTTP {q.status}</span>}
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
  return (
    <div className="group appendix" id="appendix" data-open={open || undefined} data-print-open>
      <button type="button" className="group__row appendix__summary" aria-expanded={open} aria-controls={bodyId} onClick={() => onOpenChange(!open)}>
        <span className="group__main">
          <span className="group__title">Query appendix</span>
          <span className="group__sub num">
            {n} Qloo {n === 1 ? 'query' : 'queries'}; every number above cites one
          </span>
        </span>
        <motion.span className="group__chev" animate={{ rotate: open ? 90 : 0 }} transition={reduce ? fade : springQuick} aria-hidden="true">
          <IconChevron size={16} />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={bodyId}
            className="appendix__body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={reduce ? fade : springQuick}
            style={{ overflow: 'hidden' }}
          >
            {body}
          </motion.div>
        )}
      </AnimatePresence>
      {!open && <div className="disclosure__print-only">{body}</div>}
    </div>
  )
}

// ------------------------------------------------------------------ findings

function leanSummary(findings: Memo['findings']): string {
  const counts = new Map<FactorLean, number>()
  for (const f of findings) counts.set(f.lean, (counts.get(f.lean) ?? 0) + 1)
  const order: FactorLean[] = ['favors_senior', 'neutral', 'favors_junior', 'insufficient_data']
  return order
    .filter((l) => counts.has(l))
    .map((l) => `${counts.get(l)} ${LEAN_LABEL[l].toLowerCase()}`)
    .join(' · ')
}

function Findings({ findings, onQuery, reduce }: { findings: Memo['findings']; onQuery: (n: string) => void; reduce: boolean }) {
  return (
    <section className="memo__findings" aria-labelledby="findings-title">
      <h3 id="findings-title" className="memo__h">
        <span className="memo__h-num num" aria-hidden="true">
          §
        </span>
        Factor findings
      </h3>
      <ul className="group findings">
        {findings.map((f) => (
          <li key={f.factor} className="group__row group__row--top finding">
            <div className="finding__head">
              <span className="finding__factor">{factorLabel(f.factor)}</span>
              <span className="finding__tags">
                <LeanChip lean={f.lean} size="sm" />
                <ConfidenceMeter level={f.confidence} />
              </span>
            </div>
            <p className="finding__text">{f.finding}</p>
            {f.evidence_refs.length > 0 && (
              <span className="finding__refs" aria-label="Evidence">
                {f.evidence_refs.map((r) => (
                  <RefChip key={r} r={r} onQuery={onQuery} reduce={reduce} />
                ))}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

// ------------------------------------------------------------------ memo

export default function MemoView({ memo, title }: { memo: Memo; title?: string }) {
  const reduce = useReducedMotion() ?? false
  const [appendixOpen, setAppendixOpen] = useState(false)
  const limits = memo.limitations.length ? memo.limitations : FIXED_LIMITATIONS
  const n = memo.appendix_queries.length

  // Open the appendix, then scroll to and flash the cited row once it has rendered.
  function goToQuery(num: string) {
    const id = `query-${num}`
    if (!appendixOpen) setAppendixOpen(true)
    let tries = 0
    const attempt = () => {
      const el = document.getElementById(id)
      // wait until the row is inside the open (visible) body, not the print-only copy
      if (el && el.offsetParent !== null && scrollFlash(id, reduce)) return
      if (tries++ > 30) return
      requestAnimationFrame(attempt)
    }
    requestAnimationFrame(attempt)
  }

  // Citations inside rendered markdown are plain anchors; intercept them.
  function onClick(e: MouseEvent<HTMLElement>) {
    const a = (e.target as HTMLElement).closest('a[href^="#query-"]')
    if (!a || !(e.currentTarget as HTMLElement).contains(a)) return
    const m = /^#query-(\d+)$/.exec(a.getAttribute('href') ?? '')
    if (!m) return
    e.preventDefault()
    goToQuery(m[1])
  }

  return (
    <article className="memo" id="memo" aria-labelledby="memo-title" onClick={onClick}>
      <header className="memo__head">
        <p className="eyebrow">Evidence memo{title ? ` · ${title}` : ''}</p>
        <h2 id="memo-title" className="memo__headline serif">
          {memo.headline}
        </h2>
        {memo.bottom_line && <p className="memo__bottom-line">{memo.bottom_line}</p>}
        <p className="memo__dateline footnote secondary">
          <span>
            Prepared from <span className="num">{n}</span> Qloo {n === 1 ? 'query' : 'queries'}
          </span>
          {memo.findings.length > 0 && (
            <>
              <span aria-hidden="true"> · </span>
              <span>
                <span className="num">{memo.findings.length}</span> factor{memo.findings.length === 1 ? '' : 's'}: {leanSummary(memo.findings)}
              </span>
            </>
          )}
        </p>
      </header>

      {memo.findings.length > 0 && <Findings findings={memo.findings} onQuery={goToQuery} reduce={reduce} />}

      {memo.sections.map((s, i) => (
        <section key={s.id} className="memo__section" aria-labelledby={`sec-${s.id}`}>
          <h3 id={`sec-${s.id}`} className="memo__h">
            <span className="memo__h-num num" aria-hidden="true">
              {i + 1}
            </span>
            {s.title}
          </h3>
          <Markdown md={s.markdown} />
        </section>
      ))}

      <aside className="group limits" aria-labelledby="limits-title">
        <h3 id="limits-title" className="group__header limits__title">
          <span className="limits__icon" aria-hidden="true">
            <IconWarn size={16} />
          </span>
          What this cannot tell you
        </h3>
        <ol className="limits__list">
          {limits.map((l, i) => (
            <li key={i} className="group__row group__row--top group__sep">
              <span className="limits__n num">{i + 1}</span>
              <span className="group__main">{l}</span>
            </li>
          ))}
        </ol>
      </aside>

      <QueryAppendix queries={memo.appendix_queries} open={appendixOpen} onOpenChange={setAppendixOpen} />
    </article>
  )
}
