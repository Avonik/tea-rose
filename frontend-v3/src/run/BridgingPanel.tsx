import type { ReactNode } from 'react'
import { humanize, ordinalPercentile, possessive, standing, tagName } from '../lib/format'
import type { BridgingEvidence, Resolution } from '../types'
import ScaleGauge from './ScaleGauge'
import './evidence.css'

/**
 * Bridging the gap, the fourth row under question 1: does the older brand's audience already lean
 * toward the newcomer's category? Same axis as every other score: "no pull" to "strong pull".
 */
export function BridgingGauge({ ev, resolution, senior }: { ev: BridgingEvidence; resolution: Resolution | null; senior: string }) {
  const menus = [resolution?.junior_proxy, resolution?.senior_proxy]
  const cat = ev.category_tag_ids.map((t) => tagName(t, menus)).join(' + ') || 'the newcomer’s category'
  const p = ev.percentile
  const levels = ev.ancestor_levels ?? 0
  const matched = ev.matched_tag_name ?? (ev.matched_tag_id ? humanize(ev.matched_tag_id.split(':').pop() ?? '') : null)
  const rank = ev.category_rank_among_senior_tags
  const n = ev.senior_tag_universe
  const rankText = rank != null && n ? ` (rank ${rank} of ${n})` : ''

  let meaning: ReactNode
  if (p == null) meaning = <>Not measured.</>
  else if (levels > 0 && matched)
    meaning = (
      <>
        {cat} itself is not among the categories {possessive(senior)} fans like, but its parent category {matched} is{rankText}, so the score is halved for
        each level up ({levels === 1 ? 'one level' : `${levels} levels`}): {standing(p)}.
      </>
    )
  else if (rank == null && p === 0) meaning = <>Neither {cat} nor any parent category appears among the categories {possessive(senior)} fans like.</>
  else
    meaning = (
      <>
        Among the categories {possessive(senior)} fans like, {cat} sits {standing(p)}
        {rankText}.
      </>
    )

  return (
    <ScaleGauge
      id="bridging"
      title={`Would ${senior} move into ${cat.toLowerCase()}?`}
      value={p}
      display={ordinalPercentile(p)}
      low="no pull"
      high="strong pull"
      meaning={meaning}
      tone="junior"
    />
  )
}

export default BridgingGauge
