import type { ReactNode } from 'react'
import { IconCheck } from '../components/icons'
import { Disclosure } from '../components/ui'
import type { CaseStory } from '../content/cases'
import { CLAIM_LABEL, humanize } from '../lib/format'
import type { Extraction, Party, RoutingDecision } from '../types'

const ANALYSIS_LABEL: Record<string, string> = {
  overlap: 'Do the same people buy both?',
  bridging: 'Would the older brand move into this category?',
  fame: 'Is it known by everyone?',
  zone: 'Where is it known?',
}

function outcomeText(outcome: CaseStory['outcome'], names: { senior: string; junior: string }) {
  switch (outcome) {
    case 'older brand won':
      return `${names.senior} won`
    case 'newcomer won':
      return `${names.junior} won`
    case 'mixed':
      return 'Mixed result'
    case 'settled':
      return 'Settled'
  }
}

/**
 * Section 1, the header: title, year and court, the two brands as chips, and for the showcase
 * cases one split line: what the court decided and what the taste data shows. Live runs have no
 * court line; they show the document's own summary instead.
 */
export function CaseOpening({
  extraction: x,
  names,
  story,
  year,
  children,
}: {
  extraction: Extraction
  names: { senior: string; junior: string }
  story?: CaseStory
  year?: number | null
  children?: ReactNode
}) {
  const kicker = [year ? String(year) : null, x.court_or_forum].filter(Boolean).join(' · ') || humanize(x.document_type)
  return (
    <header className="opening" aria-labelledby="case-title">
      <p className="eyebrow">{kicker}</p>
      <h1 id="case-title" className="t-headline opening__title">
        {story?.short ?? x.title}
      </h1>
      <p className="opening__brands">
        <span className="chip">
          <span className="dot dot--senior" aria-hidden="true" />
          {names.senior}
        </span>
        <span className="opening__v serif" aria-hidden="true">
          v.
        </span>
        <span className="sr-only">versus</span>
        <span className="chip">
          <span className="dot dot--junior" aria-hidden="true" />
          {names.junior}
        </span>
        {story && <span className="chip chip--quiet opening__outcome">Outcome: {outcomeText(story.outcome, names)}</span>}
      </p>
      {children}
      {story ? (
        <dl className="opening__split">
          <div className="opening__split-half">
            <dt className="eyebrow">The court decided</dt>
            <dd>{story.court}</dd>
          </div>
          <div className="opening__split-half">
            <dt className="eyebrow">The taste data shows</dt>
            <dd>{story.data}</dd>
          </div>
        </dl>
      ) : (
        <p className="t-subtitle opening__summary">{x.summary}</p>
      )}
    </header>
  )
}

function PartyGroup({ p }: { p: Party }) {
  return (
    <div className={`party party--${p.side}`}>
      <p className="group-label">{p.side === 'senior' ? 'The older brand · claimant' : 'The newcomer · respondent'}</p>
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

/** What the model read from the document: the parties, the claims, what it chose to measure, the passages. */
export function CaseParties({ extraction: x, routing }: { extraction: Extraction; routing: RoutingDecision | null }) {
  const all = ['overlap', 'bridging', 'fame', 'zone']
  return (
    <div className="case-parties">
      <div className="how__head">
        <h3 className="t-title">What the model read from the document</h3>
        {x.summary && <p className="secondary how__p">{x.summary}</p>}
        {x.claims.length > 0 && (
          <p className="opening__claims">
            <span className="caption secondary">Claims</span>
            <span className="chips">
              {x.claims.map((c) => (
                <span key={c} className="chip chip--sm">
                  {CLAIM_LABEL[c] ?? humanize(c)}
                </span>
              ))}
            </span>
          </p>
        )}
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
          <h4 className="group-label">What the model chose to measure</h4>
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
        <Disclosure className="quotes-disclosure" summary={<>Passages that drove the reading ({x.key_quotes.length})</>}>
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
