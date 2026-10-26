import type { ReactNode } from 'react'
import { IconInfo } from '../components/icons'

export function EvidenceNotes({ notes }: { notes: string[] }) {
  if (!notes.length) return null
  return (
    <ul className="ev-notes">
      {notes.map((n, i) => (
        <li key={i}>
          <IconInfo size={14} />
          <span>{n}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * One analysis in its band: a left column that answers in words and one giant numeral, a right column
 * that shows the chart, and full-width detail below. `id` is the scroll/flash target for field refs.
 */
export function EvidenceSplit({
  id,
  eyebrow,
  title,
  badge,
  numeral,
  numeralLabel,
  reading,
  left,
  right,
  below,
}: {
  id: string
  eyebrow: ReactNode
  title: ReactNode
  badge?: ReactNode
  numeral: ReactNode
  numeralLabel: ReactNode
  reading?: ReactNode
  left?: ReactNode
  right: ReactNode
  below?: ReactNode
}) {
  return (
    <article className="ev" id={id} aria-labelledby={`${id}-title`}>
      <div className="ev__grid">
        <div className="ev__left">
          <div className="ev__kicker">
            <p className="eyebrow">{eyebrow}</p>
            {badge}
          </div>
          <h3 id={`${id}-title`} className="t-headline ev__title">
            {title}
          </h3>
          <div className="ev__figure">
            {numeral}
            <p className="ev__label">{numeralLabel}</p>
            {reading && <p className="ev__reading">{reading}</p>}
          </div>
          {left}
        </div>
        <div className="ev__right">{right}</div>
      </div>
      {below && <div className="ev__below">{below}</div>}
    </article>
  )
}
