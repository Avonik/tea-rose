import { createContext, useContext, type ReactNode } from 'react'
import { IconInfo } from '../components/icons'
import { fitLabel, ordinalPercentile, wholePct } from '../lib/format'
import type { ProxyResolution } from '../types'

export function EvidenceNotes({ notes }: { notes: string[] }) {
  if (!notes.length) return null
  return (
    <ul className="ev-notes">
      {notes.map((n, i) => (
        <li key={i}>
          <IconInfo size={14} />
          <span>{plainNote(n)}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * "Measured through stand-ins: KONG, Chuckit! · Nearest category, no exact match". Leads every
 * block that was measured through comparator brands, so nobody misses it.
 */
export function StandIns({ proxy, name }: { proxy: ProxyResolution | null | undefined; name: string }) {
  if (!proxy) return null
  const brands = proxy.comparator_brand_names
  const fit = fitLabel(proxy.fit, proxy.fit_note)
  return (
    <p className="stand-ins">
      <span className={`dot dot--${proxy.side}`} aria-hidden="true" />
      <span>
        <strong>Measured through stand-ins{brands.length ? ':' : ''}</strong> {brands.length ? brands.join(', ') : `brands in the category of “${proxy.goods_phrase}”`}
        <span className="secondary">
          {' '}
          (Qloo does not know {name}
          {fit ? `; ${fit.charAt(0).toLowerCase()}${fit.slice(1)}` : ''})
        </span>
      </span>
    </p>
  )
}

/** True inside a question measured for context only: run for completeness, not raised by the pleading. */
export const ContextOnly = createContext(false)

/**
 * One of the three questions in its band: the question as the title, a plain lead sentence, the
 * stand-in line where it applies, the gauges, an optional chart beside them, detail below.
 */
export function QuestionBlock({
  id,
  n,
  title,
  lead,
  standIns,
  gauges,
  aside,
  detail,
}: {
  id: string
  n: number
  title: ReactNode
  lead: ReactNode
  standIns?: ReactNode
  gauges: ReactNode
  aside?: ReactNode
  detail?: ReactNode
}) {
  const context = useContext(ContextOnly)
  return (
    <article className="qb ev" id={id} aria-labelledby={`${id}-title`}>
      <header className="qb__head">
        <p className="eyebrow">Question {n} of 3</p>
        <h3 id={`${id}-title`} className="t-headline qb__title">
          {title}
        </h3>
        <p className="t-subtitle qb__lead">{lead}</p>
        {context && <p className="stand-ins">Measured for context; the pleading did not raise it.</p>}
        {standIns}
      </header>
      <div className={`qb__grid ${aside ? 'qb__grid--split' : ''}`}>
        <div className="group qb__gauges">{gauges}</div>
        {aside && <div className="qb__aside">{aside}</div>}
      </div>
      {detail && <div className="qb__detail">{detail}</div>}
    </article>
  )
}

/**
 * Backend notes are written for the memo and sometimes carry a raw score ("p=0.70", "affinity
 * 0.66"). On the page every number is an ordinal or a whole percentage, so rewrite them in place.
 */
export function plainNote(text: string): string {
  return text
    .replace(/\(?\bp\s*=\s*(0?\.\d+|1(?:\.0+)?)\)?/g, (_m, v: string) => `(${ordinalPercentile(Number(v))})`)
    .replace(/(^|[^\d.])(0?\.\d+|1\.0+)(?![\d.%])/g, (_m, pre: string, v: string) => `${pre}${wholePct(Number(v))}`)
}
