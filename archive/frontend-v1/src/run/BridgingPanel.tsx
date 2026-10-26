import { num, tagName } from '../lib/format'
import type { BridgingEvidence, Resolution } from '../types'
import RankGauge from './RankGauge'

export default function BridgingPanel({ ev, resolution, senior }: { ev: BridgingEvidence; resolution: Resolution | null; senior: string }) {
  const menus = [resolution?.junior_proxy, resolution?.senior_proxy]
  const cat = ev.category_tag_ids.map((t) => tagName(t, menus)).join(' + ') || 'The junior’s category'
  return (
    <section className="card evidence" id="bridging" aria-labelledby="bridging-title">
      <div className="card__head">
        <div className="card__title">
          <p className="eyebrow">Bridging the gap</p>
          <h3 id="bridging-title">Does the senior’s audience already lean toward the junior’s category?</h3>
        </div>
      </div>
      <RankGauge
        eyebrow={`Among ${senior} fans’ taste tags`}
        subject={cat}
        rank={ev.category_rank_among_senior_tags}
        universe={ev.senior_tag_universe}
        universeLabel="taste tags"
        percentile={ev.percentile}
        side="junior"
      />
      <div className="stats bridging__stats">
        <div className="stat">
          <span className="stat__value">{num(ev.category_affinity)}</span>
          <span className="stat__label">Category affinity (within this query only)</span>
        </div>
        <div className="stat">
          <span className="stat__label">Category tags</span>
          <span className="chips">
            {ev.category_tag_ids.map((t) => (
              <code key={t} className="chip chip--outline mono">
                {t}
              </code>
            ))}
          </span>
        </div>
      </div>
      {ev.notes.length > 0 && (
        <ul className="evidence-notes">
          {ev.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
