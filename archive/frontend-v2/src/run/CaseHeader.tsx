import type { ReactNode } from 'react'
import { IconCheck } from '../components/icons'
import { Disclosure } from '../components/ui'
import { CLAIM_LABEL, humanize } from '../lib/format'
import type { Extraction, Party, RoutingDecision } from '../types'

const ANALYSIS_LABEL: Record<string, string> = {
  overlap: 'Shared purchasers',
  bridging: 'Bridging the gap',
  fame: 'Fame',
  zone: 'Zone of reputation',
}

/** The opening block: document type and forum, the case title, the toolbar, the summary, the claims. */
export function CaseOpening({ extraction: x, children }: { extraction: Extraction; children?: ReactNode }) {
  return (
    <header className="opening" aria-labelledby="case-title">
      <p className="eyebrow">
        {humanize(x.document_type)}
        {x.court_or_forum && <> · {x.court_or_forum}</>}
      </p>
      <h1 id="case-title" className="t-headline opening__title">
        {x.title}
      </h1>
      {children}
      <p className="t-subtitle opening__summary">{x.summary}</p>
      {x.claims.length > 0 && (
        <div className="opening__claims">
          <span className="caption secondary">Claims</span>
          <span className="chips">
            {x.claims.map((c) => (
              <span key={c} className="chip">
                {CLAIM_LABEL[c] ?? humanize(c)}
              </span>
            ))}
          </span>
        </div>
      )}
    </header>
  )
}

function PartyGroup({ p }: { p: Party }) {
  return (
    <div className={`party party--${p.side}`}>
      <p className="group-label">{p.side === 'senior' ? 'Senior user · claimant' : 'Junior user · respondent'}</p>
      <div className="group">
        <div className="group__header party__head">
          <span className={`dot dot--${p.side}`} aria-hidden="true" />
          <h3 className="t-title-2">{p.name}</h3>
        </div>
        <dl className="party__rows">
          {p.marks.length > 0 && (
            <div className="group__row group__row--top group__sep party__row">
              <dt>Marks</dt>
              <dd>
                <span className="chips">
                  {p.marks.map((m) => (
                    <span key={m} className="chip chip--sm">
                      <span className={`dot dot--${p.side}`} aria-hidden="true" />
                      {m}
                    </span>
                  ))}
                </span>
              </dd>
            </div>
          )}
          {p.goods.length > 0 && (
            <div className="group__row group__row--top group__sep party__row">
              <dt>Goods</dt>
              <dd className="party__goods">
                {p.goods.map((g, i) => (
                  <q key={i} className="serif">
                    {g}
                  </q>
                ))}
              </dd>
            </div>
          )}
          {p.channels.length > 0 && (
            <div className="group__row group__row--top group__sep party__row">
              <dt>Channels</dt>
              <dd>{p.channels.join(' · ')}</dd>
            </div>
          )}
          {p.geography.length > 0 && (
            <div className="group__row group__row--top group__sep party__row">
              <dt>Geography</dt>
              <dd>{p.geography.join(' · ')}</dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  )
}

/** Parties side by side, what the agent chose to measure, and the passages that drove the extraction. */
export function CaseParties({ extraction: x, routing }: { extraction: Extraction; routing: RoutingDecision | null }) {
  const all = ['overlap', 'bridging', 'fame', 'zone']
  return (
    <div className="case-parties">
      <div className="band__head">
        <p className="eyebrow">Parties</p>
        <h2 className="t-headline">Who is on each side.</h2>
      </div>
      <div className="parties">
        <PartyGroup p={x.senior} />
        <span className="parties__v serif" aria-hidden="true">
          v.
        </span>
        <PartyGroup p={x.junior} />
      </div>

      {routing && (
        <div className="routing">
          <h3 className="group-label">What the agent chose to measure</h3>
          <ul className="group routing__list">
            {all.map((a) => {
              const on = routing.analyses.includes(a as never)
              return (
                <li key={a} className="group__row group__row--top" data-on={on || undefined}>
                  <span className="routing__mark" aria-hidden="true">
                    {on ? <IconCheck size={13} /> : <span className="routing__dash" />}
                  </span>
                  <span className="group__main">
                    <span className="group__title">{ANALYSIS_LABEL[a]}</span>
                    {routing.rationale[a] && <span className="group__sub">{routing.rationale[a]}</span>}
                  </span>
                  <span className="group__value caption">{on ? 'Measured' : 'Not measured'}</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {x.key_quotes.length > 0 && (
        <Disclosure className="quotes-disclosure" summary={<>Passages that drove the extraction ({x.key_quotes.length})</>}>
          <ul className="group quotes">
            {x.key_quotes.map((q, i) => (
              <li key={i} className="group__row">
                <blockquote className="serif">{q}</blockquote>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  )
}

export default CaseOpening
