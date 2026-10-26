import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useId, useRef, useState, type RefObject } from 'react'
import { Disclosure, Meter } from '../components/ui'
import { AGE_LABEL, num, pct, signed } from '../lib/format'
import { AnimatedNumber } from '../motion/AnimatedNumber'
import { fade, spring } from '../motion/springs'
import { AGE_BUCKETS, GENDERS, type FameEvidence } from '../types'
import { EvidenceNotes, EvidenceSplit } from './EvidenceKit'
import './evidence.css'

interface Datum {
  key: string
  label: string
  value: number
}

const H = 200
const PAD_TOP = 22
const PAD_BOTTOM = 22
const BAR_MAX = 24

/** Width of an element in CSS px, tracked with a ResizeObserver so the chart draws in real pixels. */
function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => setW(entries[0]?.contentRect.width ?? el.clientWidth))
    ro.observe(el)
    setW(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

/** Rounded on the data end (4px), square at the zero line. */
function barPath(x: number, w: number, zeroY: number, valueY: number): string {
  const r = Math.min(4, Math.abs(zeroY - valueY), w / 2)
  const x2 = x + w
  if (valueY <= zeroY) {
    return `M${x},${zeroY} V${valueY + r} Q${x},${valueY} ${x + r},${valueY} H${x2 - r} Q${x2},${valueY} ${x2},${valueY + r} V${zeroY} Z`
  }
  return `M${x},${zeroY} V${valueY - r} Q${x},${valueY} ${x + r},${valueY} H${x2 - r} Q${x2},${valueY} ${x2},${valueY - r} V${zeroY} Z`
}

/**
 * Diverging bars around a zero line, drawn in SVG. Bars grow from the baseline with a spring;
 * values sit on the data end, labels under the plot. Under reduced motion they appear at once.
 */
export function DivergingBars({ data, label }: { data: Datum[]; label: string }) {
  const reduce = useReducedMotion()
  const [hover, setHover] = useState<number | null>(null)
  const tipId = useId()
  const [wrapRef, measured] = useWidth<HTMLDivElement>()
  const width = Math.max(measured, data.length * 32)
  const W = width / data.length
  const lim = Math.max(0.5, ...data.map((d) => Math.abs(d.value)))
  const dom = lim > 0.5 ? 1 : 0.5
  const plotH = H - PAD_TOP - PAD_BOTTOM
  const zeroY = PAD_TOP + plotH / 2
  const yOf = (v: number) => zeroY - (v / dom) * (plotH / 2)
  const ticks = dom === 1 ? [-1, -0.5, 0.5, 1] : [-0.5, -0.25, 0.25, 0.5]
  const barW = Math.min(BAR_MAX, W * 0.6)
  const desc = data.map((d) => `${d.label} ${signed(d.value)}`).join(', ')
  const hovered = hover == null ? null : data[hover]

  return (
    <div className="dbars" ref={wrapRef}>
      <svg
        className="dbars__svg"
        width={width}
        height={H}
        viewBox={`0 0 ${width} ${H}`}
        role="img"
        aria-label={`${label}: ${desc}`}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <line key={t} x1={0} x2={width} y1={yOf(t)} y2={yOf(t)} className="dbars__grid" />
        ))}
        <line x1={0} x2={width} y1={zeroY} y2={zeroY} className="dbars__zero" />
        {data.map((d, i) => {
          const x = i * W + (W - barW) / 2
          const vy = yOf(d.value)
          const positive = d.value >= 0
          const empty = Math.abs(d.value) < 0.001
          return (
            <g key={d.key} onPointerEnter={() => setHover(i)}>
              <title>{`${d.label}: ${signed(d.value)} (${positive ? 'over-indexes' : 'under-indexes'})`}</title>
              <rect x={i * W} y={0} width={W} height={H} className="dbars__slot" data-hover={hover === i || undefined} />
              {!empty && (
                <motion.path
                  d={barPath(x, barW, zeroY, vy)}
                  className={positive ? 'dbars__bar dbars__bar--pos' : 'dbars__bar dbars__bar--neg'}
                  style={{ originY: `${zeroY}px`, originX: `${x + barW / 2}px` }}
                  initial={{ scaleY: 0 }}
                  animate={{ scaleY: 1 }}
                  transition={reduce ? fade : { ...spring, delay: i * 0.03 }}
                />
              )}
            </g>
          )
        })}
      </svg>
      {/* HTML overlays keep text crisp and unstretched */}
      <div className="dbars__values" aria-hidden="true">
        {data.map((d, i) => {
          const top = ((yOf(d.value) + (d.value >= 0 ? -6 : 6)) / H) * 100
          const left = ((i + 0.5) / data.length) * 100
          return (
            <span key={d.key} className="dbars__value num" style={{ top: `${top}%`, left: `${left}%`, transform: d.value >= 0 ? 'translate(-50%, -100%)' : 'translate(-50%, 0)' }}>
              {signed(d.value)}
            </span>
          )
        })}
      </div>
      <div className="dbars__labels" aria-hidden="true">
        {data.map((d) => (
          <span key={d.key}>{d.label}</span>
        ))}
      </div>
      {hovered && (
        <div className="chart-tip" id={tipId} role="tooltip" style={{ left: `${((hover! + 0.5) / data.length) * 100}%` }}>
          <div className="chart-tip__label">{hovered.label}</div>
          <div className="chart-tip__value num">{signed(hovered.value)}</div>
          <div className="caption secondary">{hovered.value > 0 ? 'over-indexes' : hovered.value < 0 ? 'under-indexes' : 'at baseline'}</div>
        </div>
      )}
    </div>
  )
}

export default function FamePanel({ ev, senior }: { ev: FameEvidence; senior: string }) {
  const age: Datum[] = AGE_BUCKETS.map((b) => ({ key: b, label: AGE_LABEL[b], value: ev.demographics.age[b] ?? 0 }))
  const gender: Datum[] = GENDERS.map((g) => ({ key: g, label: g === 'male' ? 'Men' : 'Women', value: ev.demographics.gender[g] ?? 0 }))
  const all = [...age, ...gender]
  const positive = all.filter((d) => d.value > 0).length
  const hasData = all.some((d) => d.value !== 0)
  const popDigits = ev.popularity_percentile != null && ev.popularity_percentile > 0.99 ? 1 : 0

  const stats = [
    {
      key: 'pop',
      label: 'Popularity percentile',
      hint: 'More popular than this share of brands in Qloo',
      value: ev.popularity_percentile,
      format: (v: number) => pct(v, popDigits),
      meter: ev.popularity_percentile != null ? `Popularity ${pct(ev.popularity_percentile)}` : null,
    },
    {
      key: 'cov',
      label: 'National heatmap cells above median',
      hint: 'How much of the US map shows above-median affinity',
      value: ev.heatmap_coverage,
      format: (v: number) => pct(v),
      meter: ev.heatmap_coverage != null ? `Coverage ${pct(ev.heatmap_coverage)}` : null,
    },
  ]

  return (
    <EvidenceSplit
      id="fame"
      eyebrow="Fame · dilution threshold"
      badge={
        <span className="badge num">
          {positive} of 8 groups over-index
        </span>
      }
      title={<>How broadly is {senior} liked?</>}
      numeral={<AnimatedNumber value={ev.breadth_score} className="numeral" />}
      numeralLabel="Breadth across age and gender groups"
      reading="1.00 = liked by every group; low = a niche audience"
      left={
        <>
          {ev.breadth_score != null && (
            <div className="ev__meter">
              <Meter value={ev.breadth_score} color="var(--senior)" label={`Breadth ${num(ev.breadth_score)}`} />
            </div>
          )}
          <p className="ev__skew">
            <span className="secondary">Skew: </span>
            {ev.skew_description}
          </p>
          <EvidenceNotes notes={ev.notes} />
        </>
      }
      right={
        <div className="ev__chart stack">
          <dl className="group">
            {stats.map((s, i) => (
              <div key={s.key} className={`group__row group__row--top fame-stat ${i > 0 ? 'group__sep' : ''}`}>
                <dt className="group__main">
                  <span className="group__title">{s.label}</span>
                  <span className="group__sub">{s.hint}</span>
                  {s.value != null && s.meter && (
                    <span className="fame-stat__meter">
                      <Meter value={s.value} color="var(--senior)" label={s.meter} />
                    </span>
                  )}
                </dt>
                <dd className="ev__stat-value">
                  <AnimatedNumber value={s.value} format={s.format} />
                </dd>
              </div>
            ))}
          </dl>

          {hasData ? (
            <div className="group fame-charts-group">
              <div className="fame-charts">
                <figure className="fame-chart fame-chart--age">
                  <figcaption className="caption secondary">By age</figcaption>
                  <DivergingBars data={age} label="Affinity by age group" />
                </figure>
                <figure className="fame-chart fame-chart--gender">
                  <figcaption className="caption secondary">By gender</figcaption>
                  <DivergingBars data={gender} label="Affinity by gender" />
                </figure>
              </div>
              <div className="legend caption secondary">
                <span className="legend__item">
                  <span className="legend__swatch" style={{ background: 'var(--senior)' }} /> Over-indexes vs. the general population
                </span>
                <span className="legend__item">
                  <span className="legend__swatch" style={{ background: 'var(--neg)' }} /> Under-indexes
                </span>
                <span className="legend__item tertiary">Values run −1 to +1; zero is the population baseline</span>
              </div>
              <Disclosure summary="Show values as a table" className="fame-table-disclosure">
                <div className="table-scroll">
                  <table className="table fame-table">
                    <caption className="sr-only">Affinity by demographic group, −1 to +1</caption>
                    <thead>
                      <tr>
                        {all.map((d) => (
                          <th key={d.key} scope="col" className="r">
                            {d.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        {all.map((d) => (
                          <td key={d.key} className="r num">
                            {signed(d.value)}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </Disclosure>
            </div>
          ) : (
            <p className="footnote tertiary">Qloo returned no demographic signal for this brand.</p>
          )}
        </div>
      }
    />
  )
}
