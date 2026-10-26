import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useMemo, type MouseEvent } from 'react'
import { IconWarn } from '../components/icons'
import { ConfidenceMeter, Disclosure, LeanChip } from '../components/ui'
import { factorLabel, formatParams, shortId } from '../lib/format'
import { FIXED_LIMITATIONS } from '../content/limitations'
import type { Memo, QlooQuery } from '../types'

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

function RefChip({ r }: { r: string }) {
  const m = /^Q(\d+)$/.exec(r)
  if (m)
    return (
      <a className="ref-chip" href={`#query-${m[1]}`}>
        {r}
      </a>
    )
  return <code className="ref-chip ref-chip--field">{r}</code>
}

function source(q: QlooQuery) {
  if (q.fixture_file) return { label: 'Fixture', title: q.fixture_file }
  if (q.cache_hit) return { label: 'Cache', title: 'Served from the local response cache' }
  return { label: 'Live', title: 'Live Qloo API call' }
}

export function QueryAppendix({ queries }: { queries: QlooQuery[] }) {
  return (
    <Disclosure
      className="appendix"
      summary={
        <span className="appendix__summary">
          <strong>Query appendix</strong>
          <span className="faint num"> · {queries.length} Qloo {queries.length === 1 ? 'query' : 'queries'}; every number above cites one</span>
        </span>
      }
    >
      {queries.length === 0 ? (
        <p className="caption faint">No queries were recorded.</p>
      ) : (
        <div className="table-scroll">
          <table className="table appendix__table">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Endpoint</th>
                <th scope="col">Parameters</th>
                <th scope="col" className="r">
                  Results
                </th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {queries.map((q, i) => {
                const s = source(q)
                return (
                  <tr key={i} id={`query-${i + 1}`} className="appendix__row">
                    <td className="num faint">Q{i + 1}</td>
                    <td>
                      <code>{q.endpoint}</code>
                    </td>
                    <td>
                      <ul className="appendix__params">
                        {formatParams(q.params).map(([k, v]) => (
                          <li key={k}>
                            <span className="faint">{k}=</span>
                            <span title={v}>{v.split(',').map(shortId).join(',')}</span>
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td className="r num">{q.result_count ?? '–'}</td>
                    <td>
                      <span className={`chip chip--outline src src--${s.label.toLowerCase()}`} title={s.title}>
                        {s.label}
                      </span>
                      {q.elapsed_ms != null && <span className="caption faint num appendix__ms"> {q.elapsed_ms} ms</span>}
                      {q.status != null && q.status !== 200 && <span className="caption num appendix__status"> HTTP {q.status}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Disclosure>
  )
}

export default function MemoView({ memo, title }: { memo: Memo; title?: string }) {
  const limits = memo.limitations.length ? memo.limitations : FIXED_LIMITATIONS

  // Citations point into the (collapsed) appendix: open it, then scroll and flash the row.
  function onClick(e: MouseEvent<HTMLElement>) {
    const a = (e.target as HTMLElement).closest('a[href^="#query-"]')
    if (!a) return
    const id = a.getAttribute('href')!.slice(1)
    const row = document.getElementById(id)
    if (!row) return
    e.preventDefault()
    const details = row.closest('details')
    if (details && !details.open) details.open = true
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    requestAnimationFrame(() => {
      row.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' })
      row.classList.remove('is-flash')
      void row.offsetWidth
      row.classList.add('is-flash')
      history.replaceState(null, '', `#${id}`)
    })
  }

  return (
    <article className="memo card" id="memo" aria-labelledby="memo-title" onClick={onClick}>
      <header className="memo__head">
        <p className="eyebrow">Evidence memo{title ? ` · ${title}` : ''}</p>
        <h2 id="memo-title" className="memo__headline">
          {memo.headline}
        </h2>
        {memo.bottom_line && <p className="memo__bottom-line">{memo.bottom_line}</p>}
      </header>

      {memo.findings.length > 0 && (
        <section className="memo__findings" aria-labelledby="findings-title">
          <h3 id="findings-title" className="memo__h">
            Factor findings
          </h3>
          <div className="table-scroll">
            <table className="table findings">
              <thead>
                <tr>
                  <th scope="col">Factor</th>
                  <th scope="col">Lean</th>
                  <th scope="col">Confidence</th>
                  <th scope="col">Finding</th>
                </tr>
              </thead>
              <tbody>
                {memo.findings.map((f) => (
                  <tr key={f.factor}>
                    <th scope="row" className="findings__factor">
                      {factorLabel(f.factor)}
                    </th>
                    <td>
                      <LeanChip lean={f.lean} />
                    </td>
                    <td>
                      <ConfidenceMeter level={f.confidence} />
                    </td>
                    <td className="findings__text">
                      <p>{f.finding}</p>
                      {f.evidence_refs.length > 0 && (
                        <span className="findings__refs">
                          {f.evidence_refs.map((r) => (
                            <RefChip key={r} r={r} />
                          ))}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {memo.sections.map((s) => (
        <section key={s.id} className="memo__section" aria-labelledby={`sec-${s.id}`}>
          <h3 id={`sec-${s.id}`} className="memo__h">
            {s.title}
          </h3>
          <Markdown md={s.markdown} />
        </section>
      ))}

      <aside className="limits" aria-labelledby="limits-title">
        <h3 id="limits-title" className="limits__title">
          <IconWarn size={18} /> What this cannot tell you
        </h3>
        <ul className="limits__list">
          {limits.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      </aside>

      <QueryAppendix queries={memo.appendix_queries} />
    </article>
  )
}
