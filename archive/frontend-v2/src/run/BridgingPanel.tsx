import { num, readPercentile, tagName } from '../lib/format'
import { AnimatedNumber } from '../motion/AnimatedNumber'
import type { BridgingEvidence, Resolution } from '../types'
import { EvidenceNotes, EvidenceSplit } from './EvidenceKit'
import RankGauge from './RankGauge'
import './evidence.css'

export default function BridgingPanel({ ev, resolution, senior }: { ev: BridgingEvidence; resolution: Resolution | null; senior: string }) {
  const menus = [resolution?.junior_proxy, resolution?.senior_proxy]
  const cat = ev.category_tag_ids.map((t) => tagName(t, menus)).join(' + ') || 'The junior’s category'
  return (
    <EvidenceSplit
      id="bridging"
      eyebrow="Bridging the gap"
      title="Does the senior’s audience already lean toward the junior’s category?"
      numeral={<AnimatedNumber value={ev.percentile} className="numeral" />}
      numeralLabel={
        <>
          Where {cat} sits among {senior} fans’ taste tags, as a percentile
        </>
      }
      reading={ev.percentile != null ? readPercentile(ev.percentile) : undefined}
      left={<EvidenceNotes notes={ev.notes} />}
      right={
        <div className="ev__chart stack">
          <div className="group gauges">
            <RankGauge
              eyebrow={`Among ${senior} fans’ taste tags`}
              subject={cat}
              rank={ev.category_rank_among_senior_tags}
              universe={ev.senior_tag_universe}
              universeLabel="taste tags"
              percentile={ev.percentile}
              side="junior"
            />
          </div>
          <dl className="group">
            <div className="group__row group__row--top">
              <dt className="group__main">
                <span className="group__title">Category affinity</span>
                <span className="group__sub">Within this query only; not comparable across queries</span>
              </dt>
              <dd className="ev__stat-value">
                <AnimatedNumber value={ev.category_affinity} />
                <span className="sr-only"> ({num(ev.category_affinity)})</span>
              </dd>
            </div>
            <div className="group__row group__sep ev__row-stack">
              <dt className="group__title">Category tags</dt>
              <dd className="chips">
                {ev.category_tag_ids.map((t) => (
                  <code key={t} className="chip chip--mono">
                    {t}
                  </code>
                ))}
              </dd>
            </div>
          </dl>
        </div>
      }
    />
  )
}
