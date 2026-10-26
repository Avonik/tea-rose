import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useId, useRef, useState, type RefObject } from 'react'
import { Disclosure } from '../components/ui'
import { AGE_LABEL, ordinalPercentile, signedWhole, wholePct } from '../lib/format'

import { fade, spring } from '../motion/springs'
import { AGE_BUCKETS, GENDERS, type FameEvidence, type ProxyResolution } from '../types'
import { EvidenceNotes, QuestionBlock, StandIns } from './EvidenceKit'
import ScaleGauge, { HIGH_MARK } from './ScaleGauge'
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
  const desc = data.map((d) => `${d.label} ${signedWhole(d.value)}`).join(', ')
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
              <title>{`${d.label}: ${signedWhole(d.value)} (${positive ? 'likes it more than average' : 'likes it less than average'})`}</title>
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
              {signedWhole(d.value)}
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
          <div className="chart-tip__value num">{signedWhole(hovered.value)}</div>
          <div className="caption secondary">{hovered.value > 0 ? 'likes it more than average' : hovered.value < 0 ? 'likes it less than average' : 'at baseline'}</div>
        </div>
      )}
    </div>
  )
}

/** What a 0..1 fame score means, in plain words. */
function readFame(s: number): string {
  if (s >= HIGH_MARK) return 'known well beyond its own crowd'
  if (s >= 0.5) return 'widely liked, but short of what counts as high'
  return 'liked mainly by its own crowd'
}

const of100 = (x: number | null | undefined) => (x == null ? 'not measured' : `${Math.round(Math.max(0, Math.min(1, x)) * 100)} of 100`)

/** Question 2: is the older brand known by everyone, or only by its own crowd? */
export default function FamePanel({ ev, senior, proxy }: { ev: FameEvidence; senior: string; proxy?: ProxyResolution | null }) {
  const age: Datum[] = AGE_BUCKETS.map((b) => ({ key: b, label: AGE_LABEL[b], value: ev.demographics.age[b] ?? 0 }))
  const gender: Datum[] = GENDERS.map((g) => ({ key: g, label: g === 'male' ? 'Men' : 'Women', value: ev.demographics.gender[g] ?? 0 }))
  const all = [...age, ...gender]
  const positive = all.filter((d) => d.value > 0).length
  const hasData = all.some((d) => d.value !== 0)

  // fame_score = mean(breadth, popularity, national reach) (docs/ARCHITECTURE.md); runs stored before
  // the field existed get the same mean here, and only fall back to breadth alone when a part is missing.
  const partsAll = [ev.breadth_score, ev.popularity_percentile, ev.heatmap_coverage]
  const computed = partsAll.every((v) => v != null) ? (partsAll as number[]).reduce((x, y) => x + y, 0) / 3 : null
  const s = ev.fame_score ?? computed ?? ev.breadth_score
  const fallback = ev.fame_score == null && computed == null && ev.breadth_score != null
  const parts =
    ev.breadth_age != null && ev.breadth_gender != null ? ` Across ages ${of100(ev.breadth_age)}, across genders ${of100(ev.breadth_gender)}.` : ''

  const meaning =
    s == null ? (
      <>Not measured: Qloo returned too little for this brand.</>
    ) : (
      <>
        {senior} scores {of100(s)}: {readFame(s)}.
        {fallback ? ' Only the breadth part could be measured, so this is breadth alone.' : ''}
      </>
    )

  return (
    <QuestionBlock
      id="fame"
      n={2}
      title={<>Is {senior} known by everyone, or only by its own crowd?</>}
      lead={
        <>
          How evenly {senior} is liked across ages and genders, how popular it is, and how much of the country likes it. Fame is the threshold for a dilution claim
          (that a famous mark is weakened by someone else’s use, even without any confusion).
        </>
      }
      standIns={<StandIns proxy={proxy} name={senior} />}
      gauges={
        <ScaleGauge
          id="fame-gauge"
          title="Known by everyone"
          value={s}
          display={of100(s)}
          low="one crowd"
          high="everyone"
          meaning={meaning}
          tone="senior"
          subs={[
            {
              key: 'breadth',
              label: 'Breadth',
              value: ev.breadth_score,
              display: of100(ev.breadth_score),
              note: <>How evenly it is liked across six age groups and both genders; {ev.skew_description.charAt(0).toLowerCase() + ev.skew_description.slice(1)}.{parts}</>,
            },
            {
              key: 'pop',
              label: 'Popularity',
              value: ev.popularity_percentile,
              display: ordinalPercentile(ev.popularity_percentile),
              note: <>More popular than {wholePct(ev.popularity_percentile)} of the brands Qloo knows.</>,
            },
            {
              key: 'reach',
              label: 'National reach',
              value: ev.heatmap_coverage,
              display: ev.heatmap_coverage == null ? 'not measured' : `${wholePct(ev.heatmap_coverage)} of the map`,
              note: <>Share of the US map where liking for {senior} is above its own middle.</>,
            },
          ]}
        />
      }
      aside={
        hasData ? (
          <div className="group fame-charts-group">
            <p className="fame-charts-group__title">
              Who likes it more, and who less, than the average consumer
              <span className="badge num">{positive} of 8 groups above average</span>
            </p>
            <div className="fame-charts">
              <figure className="fame-chart fame-chart--age">
                <figcaption className="caption secondary">By age</figcaption>
                <DivergingBars data={age} label="Liking by age group, −100 to +100" />
              </figure>
              <figure className="fame-chart fame-chart--gender">
                <figcaption className="caption secondary">By gender</figcaption>
                <DivergingBars data={gender} label="Liking by gender, −100 to +100" />
              </figure>
            </div>
            <div className="legend caption secondary">
              <span className="legend__item">
                <span className="legend__swatch" style={{ background: 'var(--senior)' }} /> Likes it more than average
              </span>
              <span className="legend__item">
                <span className="legend__swatch" style={{ background: 'var(--neg)' }} /> Likes it less than average
              </span>
              <span className="legend__item tertiary">From −100 to +100; zero is the average consumer</span>
            </div>
            <Disclosure summary="Show values as a table" className="fame-table-disclosure">
              <div className="table-scroll">
                <table className="table fame-table">
                  <caption className="sr-only">Liking by demographic group, −100 to +100</caption>
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
                          {signedWhole(d.value)}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </Disclosure>
          </div>
        ) : (
          <p className="footnote tertiary">Qloo returned no age or gender signal for this brand.</p>
        )
      }
      detail={ev.notes.length > 0 ? <EvidenceNotes notes={ev.notes} /> : undefined}
    />
  )
}
