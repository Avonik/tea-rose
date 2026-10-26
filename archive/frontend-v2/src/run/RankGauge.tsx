import { motion, useReducedMotion } from 'motion/react'
import { AnimatedNumber } from '../motion/AnimatedNumber'
import { fade, springSlow } from '../motion/springs'
import { ordinal, readPercentile } from '../lib/format'
import type { Side } from '../types'

/**
 * A rank shown as a position on its universe. The track runs from the weakest rank (left) to rank
 * #1 (right), so further right always means "closer to the seed's audience". The marker springs to
 * its position from wherever it was; the side colour is on the fill and marker only, never on text.
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
  const reduce = useReducedMotion()
  const p = percentile ?? (rank != null && universe ? 1 - (rank - 1) / universe : null)
  const pos = p == null ? null : Math.max(0, Math.min(1, p))
  const t = reduce ? fade : springSlow
  const aria =
    rank != null && universe
      ? `${subject} ranks ${ordinal(rank)} of ${universe} ${universeLabel}; percentile ${p?.toFixed(2)}. ${readPercentile(p)}.`
      : `${subject} was not found in the returned ${universeLabel}.`
  return (
    <figure className={`gauge gauge--${side}`}>
      <figcaption className="gauge__caption">
        <span className="gauge__eyebrow caption secondary">
          <span className={`dot dot--${side}`} aria-hidden="true" />
          {eyebrow}
        </span>
        {rank != null && universe ? (
          <span className="gauge__sentence">
            {subject} ranks <strong className="num">{ordinal(rank)}</strong> of <span className="num">{universe.toLocaleString('en-US')}</span>{' '}
            {universeLabel}
          </span>
        ) : (
          <span className="gauge__sentence">{missingNote ?? `${subject} was not found in the returned ${universeLabel}.`}</span>
        )}
      </figcaption>
      <div className="gauge__body">
        <div className="gauge__track" role="img" aria-label={aria}>
          <span className="gauge__tick" style={{ left: '25%' }} />
          <span className="gauge__tick gauge__tick--mid" style={{ left: '50%' }} />
          <span className="gauge__tick" style={{ left: '75%' }} />
          {pos != null && (
            <>
              <motion.span className="gauge__fill" initial={{ scaleX: 0 }} animate={{ scaleX: pos }} transition={t} />
              <motion.span className="gauge__marker" initial={{ left: '0%' }} animate={{ left: `${pos * 100}%` }} transition={t} />
            </>
          )}
        </div>
        <div className="gauge__value">
          <AnimatedNumber value={p} className="gauge__pct" />
          <span className="caption tertiary">percentile</span>
        </div>
      </div>
      <div className="gauge__scale caption tertiary" aria-hidden="true">
        <span>{universe ? `${ordinal(universe)} (weakest)` : 'weakest'}</span>
        <span>median</span>
        <span>#1 (closest)</span>
      </div>
      {p != null && (
        <p className="gauge__read footnote secondary">
          {rank != null && universe ? (
            <>
              <span className="num">{Math.max(0, universe - rank).toLocaleString('en-US')}</span> of the{' '}
              <span className="num">{universe.toLocaleString('en-US')}</span> {universeLabel} rank lower:{' '}
            </>
          ) : null}
          {readPercentile(p)}.
        </p>
      )}
    </figure>
  )
}
