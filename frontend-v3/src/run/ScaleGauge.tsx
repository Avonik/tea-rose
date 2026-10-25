import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { fade, springSlow } from '../motion/springs'

/** Where "high" starts on every 0 to 100 axis on the site. */
export const HIGH_MARK = 0.75

export type Tone = 'senior' | 'junior' | 'neutral'

export interface SubMeasure {
  key: string
  label: ReactNode
  /** 0..1 position on the axis; null = not measured. */
  value: number | null
  /** The value in words: "52nd percentile", "61% of the map". */
  display: string
  /** One sentence: what this sub-measure means. */
  note?: ReactNode
  tone?: Tone
  /** Rank beyond the scanned depth: the bar shows the affinity ratio instead and is drawn hollow. */
  censored?: boolean
}

function Track({ value, tone, thin, censored, label }: { value: number | null; tone: Tone; thin?: boolean; censored?: boolean; label: string }) {
  const reduce = useReducedMotion()
  const pos = value == null ? null : Math.max(0, Math.min(1, value))
  const t = reduce ? fade : springSlow
  return (
    <div className={`scale__track ${thin ? 'scale__track--thin' : ''}`} data-tone={tone} data-censored={censored || undefined} role="img" aria-label={label}>
      <span className="scale__high" style={{ left: `${HIGH_MARK * 100}%` }} aria-hidden="true" />
      {pos != null && (
        <>
          <motion.span className="scale__fill" initial={{ scaleX: 0 }} animate={{ scaleX: pos }} transition={t} />
          {!thin && <motion.span className="scale__marker" initial={{ left: '0%' }} animate={{ left: `${pos * 100}%` }} transition={t} />}
        </>
      )}
    </div>
  )
}

/**
 * The one visual grammar for every score: a 0 to 100 axis with end labels in plain words, a tick
 * where "high" starts (75), the value as an ordinal percentile or whole percentage, and one sentence
 * saying what it means. Optional sub-measures sit underneath as thin labelled bars on the same axis.
 */
export default function ScaleGauge({
  id,
  title,
  value,
  display,
  low,
  high,
  meaning,
  tone = 'neutral',
  censored,
  subs,
}: {
  id?: string
  title: ReactNode
  value: number | null
  display: string
  low: string
  high: string
  meaning: ReactNode
  tone?: Tone
  censored?: boolean
  subs?: SubMeasure[]
}) {
  const aria = `${typeof title === 'string' ? title : 'Score'}: ${display}, on a scale from ${low} to ${high}; 75 and above counts as high.`
  return (
    <figure className="scale" id={id}>
      <figcaption className="scale__head">
        <span className="scale__title">{title}</span>
        <span className="scale__value num">{display}</span>
      </figcaption>
      <Track value={value} tone={tone} censored={censored} label={aria} />
      <div className="scale__ends caption tertiary" aria-hidden="true">
        <span>{low}</span>
        <span className="scale__high-label" style={{ left: `${HIGH_MARK * 100}%` }}>
          high
        </span>
        <span>{high}</span>
      </div>
      <p className="scale__meaning">{meaning}</p>
      {subs && subs.length > 0 && (
        <ul className="scale__subs">
          {subs.map((s) => (
            <li key={s.key} className="scale__sub">
              <div className="scale__sub-head">
                <span className="scale__sub-label">
                  {s.tone && s.tone !== 'neutral' && <span className={`dot dot--${s.tone}`} aria-hidden="true" />}
                  {s.label}
                </span>
                <span className="scale__sub-value num">{s.display}</span>
              </div>
              <Track value={s.value} tone={s.tone ?? tone} thin censored={s.censored} label={`${typeof s.label === 'string' ? s.label : 'Part'}: ${s.display}`} />
              {s.note && <p className="scale__sub-note footnote secondary">{s.note}</p>}
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}
