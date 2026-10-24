import { Disclosure } from '../components/ui'
import { CLAIM_LABEL, humanize } from '../lib/format'
import type { Extraction, Party, RoutingDecision } from '../types'

const ANALYSIS_LABEL: Record<string, string> = {
  overlap: 'Shared purchasers',
  bridging: 'Bridging the gap',
  fame: 'Fame',
  zone: 'Zone of reputation',
}

function PartyBlock({ p }: { p: Party }) {
  return (
    <div className={`party party--${p.side}`}>
      <p className="eyebrow">{p.side === 'senior' ? 'Senior user · claimant' : 'Junior user · respondent'}</p>
      <h3 className="party__name">{p.name}</h3>
      {p.marks.length > 0 && (
        <div className="party__row">
          <span className="party__key">Marks</span>
          <span className="chips">
            {p.marks.map((m) => (
              <span key={m} className={`chip chip--${p.side}`}>
                {m}
              </span>
            ))}
          </span>
        </div>
      )}
      {p.goods.length > 0 && (
        <div className="party__row">
          <span className="party__key">Goods</span>
          <span className="party__val">
            {p.goods.map((g, i) => (
              <q key={i} className="party__quote">
                {g}
              </q>
            ))}
          </span>
        </div>
      )}
      {p.channels.length > 0 && (
        <div className="party__row">
          <span className="party__key">Channels</span>
          <span className="party__val">{p.channels.join(' · ')}</span>
        </div>
      )}
      {p.geography.length > 0 && (
        <div className="party__row">
          <span className="party__key">Geography</span>
          <span className="party__val">{p.geography.join(' · ')}</span>
        </div>
      )}
    </div>
  )
}

export default function CaseHeader({ extraction: x, routing }: { extraction: Extraction; routing: RoutingDecision | null }) {
  const all = ['overlap', 'bridging', 'fame', 'zone']
  return (
    <section className="case-head card" id="case" aria-labelledby="case-title">
      <p className="eyebrow">
        {humanize(x.document_type)}
        {x.court_or_forum && <> · {x.court_or_forum}</>}
      </p>
      <h1 id="case-title" className="case-head__title">
        {x.title}
      </h1>
      <p className="case-head__summary">{x.summary}</p>

      <div className="case-head__claims">
        <span className="party__key">Claims</span>
        <span className="chips">
          {x.claims.map((c) => (
            <span key={c} className="chip chip--accent">
              {CLAIM_LABEL[c] ?? humanize(c)}
            </span>
          ))}
        </span>
      </div>

      <div className="parties">
        <PartyBlock p={x.senior} />
        <span className="parties__v" aria-hidden="true">
          v.
        </span>
        <PartyBlock p={x.junior} />
      </div>

      {routing && (
        <div className="routing">
          <p className="eyebrow">What the agent chose to measure</p>
          <ul className="routing__list">
            {all.map((a) => {
              const on = routing.analyses.includes(a as never)
              return (
                <li key={a} className="routing__item" data-on={on}>
                  <span className="routing__mark" aria-hidden="true">
                    {on ? '✓' : '–'}
                  </span>
                  <span>
                    <strong>{ANALYSIS_LABEL[a]}</strong>
                    <span className="sr-only">{on ? ' (run)' : ' (not run)'}</span>
                    {routing.rationale[a] && <span className="routing__why"> {routing.rationale[a]}</span>}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {x.key_quotes.length > 0 && (
        <Disclosure className="case-head__quotes" summary={<span className="footnote">Passages that drove the extraction ({x.key_quotes.length})</span>}>
          <ul className="quotes">
            {x.key_quotes.map((q, i) => (
              <li key={i}>
                <blockquote>{q}</blockquote>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </section>
  )
}
