import { ordinal, pct } from '../lib/format'
import type { Side } from '../types'

/**
 * A rank shown as a position on its universe. The track runs from the weakest rank (left) to rank
 * #1 (right), so further right always means "closer to the seed's audience". The marker carries the
 * side color; the text carries the number.
 */
export default function RankGauge({
  eyebrow,
  subject,
  rank,
  universe,
  universeLabel,
  percentile,
  side,
  missingNote,
}: {
  eyebrow: string
  subject: string
  rank: number | null
  universe: number | null
  universeLabel: string
  percentile?: number | null
  side: Side
  missingNote?: string
}) {
  const p = percentile ?? (rank != null && universe ? 1 - (rank - 1) / universe : null)
  const pos = p == null ? null : Math.max(0, Math.min(1, p))
  return (
    <figure className={`gauge gauge--${side}`}>
      <figcaption className="gauge__caption">
        <span className="eyebrow">{eyebrow}</span>
        {rank != null && universe ? (
          <span className="gauge__sentence">
            {subject} ranks <strong className="num">{ordinal(rank)}</strong> of{' '}
            <span className="num">{universe.toLocaleString('en-US')}</span> {universeLabel}
          </span>
        ) : (
          <span className="gauge__sentence">{missingNote ?? `${subject} was not found in the returned ${universeLabel}.`}</span>
        )}
      </figcaption>
      <div className="gauge__body">
        <div className="gauge__track" aria-hidden="true">
          <span className="gauge__tick" style={{ left: '25%' }} />
          <span className="gauge__tick gauge__tick--mid" style={{ left: '50%' }} />
          <span className="gauge__tick" style={{ left: '75%' }} />
          {pos != null && (
            <>
              <span className="gauge__fill" style={{ width: `${pos * 100}%` }} />
              <span className="gauge__marker" style={{ left: `${pos * 100}%` }} />
            </>
          )}
        </div>
        <div className="gauge__value">
          <span className="gauge__pct num">{p == null ? '–' : p.toFixed(2)}</span>
          <span className="caption faint">percentile</span>
        </div>
      </div>
      <div className="gauge__scale caption faint" aria-hidden="true">
        <span>{universe ? `${ordinal(universe)} (weakest)` : 'weakest'}</span>
        <span>median</span>
        <span>#1 (closest)</span>
      </div>
      {p != null && <span className="sr-only">Percentile {pct(p)}.</span>}
    </figure>
  )
}
