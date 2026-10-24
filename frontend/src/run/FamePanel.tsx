import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Disclosure, Meter } from '../components/ui'
import { AGE_LABEL, num, pct, signed } from '../lib/format'
import { AGE_BUCKETS, GENDERS, type FameEvidence } from '../types'

interface Datum {
  key: string
  label: string
  value: number
}

/** Bar with a 4px rounded data-end and a square baseline end, for positive and negative values. */
function DivergingBar(props: unknown) {
  const { x = 0, y = 0, width = 0, height = 0, value } = props as { x?: number; y?: number; width?: number; height?: number; value?: number | [number, number] }
  const v = Array.isArray(value) ? value[1] - value[0] : (value ?? 0)
  const top = Math.min(y, y + height)
  const h = Math.abs(height)
  if (h < 0.5 || width <= 0) return null
  const r = Math.min(4, h, width / 2)
  const positive = v >= 0
  const x2 = x + width
  const bottom = top + h
  const d = positive
    ? `M${x},${bottom} V${top + r} Q${x},${top} ${x + r},${top} H${x2 - r} Q${x2},${top} ${x2},${top + r} V${bottom} Z`
    : `M${x},${top} V${bottom - r} Q${x},${bottom} ${x + r},${bottom} H${x2 - r} Q${x2},${bottom} ${x2},${bottom - r} V${top} Z`
  return <path d={d} style={{ fill: positive ? 'var(--senior)' : 'var(--neg)' }} />
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Datum }[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip__label">{d.label}</div>
      <div className="chart-tip__value num">{signed(d.value)}</div>
      <div className="caption faint">{d.value > 0 ? 'over-indexes' : d.value < 0 ? 'under-indexes' : 'at baseline'}</div>
    </div>
  )
}

function DivergingChart({ data, height, label }: { data: Datum[]; height: number; label: string }) {
  const lim = Math.max(0.5, ...data.map((d) => Math.abs(d.value)))
  const dom = lim > 0.5 ? 1 : 0.5
  return (
    <div className="chart" role="img" aria-label={`${label}: ${data.map((d) => `${d.label} ${signed(d.value)}`).join(', ')}`}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -18 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: 'var(--text-2)', fontSize: 12 }} interval={0} />
          <YAxis
            domain={[-dom, dom]}
            ticks={dom === 1 ? [-1, -0.5, 0, 0.5, 1] : [-0.5, -0.25, 0, 0.25, 0.5]}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--text-3)', fontSize: 11 }}
            tickFormatter={(v: number) => (v === 0 ? '0' : signed(v, dom === 1 ? 1 : 2))}
          />
          <ReferenceLine y={0} stroke="var(--zero)" strokeWidth={1.5} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} isAnimationActive={false} />
          <Bar dataKey="value" maxBarSize={24} shape={DivergingBar} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function FamePanel({ ev, senior }: { ev: FameEvidence; senior: string }) {
  const age: Datum[] = AGE_BUCKETS.map((b) => ({ key: b, label: AGE_LABEL[b], value: ev.demographics.age[b] ?? 0 }))
  const gender: Datum[] = GENDERS.map((g) => ({ key: g, label: g === 'male' ? 'Men' : 'Women', value: ev.demographics.gender[g] ?? 0 }))
  const positive = [...age, ...gender].filter((d) => d.value > 0).length
  const hasData = [...age, ...gender].some((d) => d.value !== 0)

  return (
    <section className="card evidence" id="fame" aria-labelledby="fame-title">
      <div className="card__head">
        <div className="card__title">
          <p className="eyebrow">Fame · dilution threshold</p>
          <h3 id="fame-title">How broadly is {senior} liked?</h3>
        </div>
        <span className="chip chip--outline num">
          {positive} of 8 groups over-index
        </span>
      </div>

      <div className="fame-stats stats">
        <div className="stat">
          <span className="stat__value">{num(ev.breadth_score)}</span>
          <span className="stat__label">Breadth across age and gender groups</span>
          <span className="stat__hint">1.00 = liked by every group; low = a niche audience</span>
          {ev.breadth_score != null && <Meter value={ev.breadth_score} color="var(--senior)" label={`Breadth ${num(ev.breadth_score)}`} />}
        </div>
        <div className="stat">
          <span className="stat__value">{pct(ev.popularity_percentile, ev.popularity_percentile != null && ev.popularity_percentile > 0.99 ? 1 : 0)}</span>
          <span className="stat__label">Popularity percentile</span>
          <span className="stat__hint">More popular than this share of brands in Qloo</span>
          {ev.popularity_percentile != null && <Meter value={ev.popularity_percentile} color="var(--senior)" label={`Popularity ${pct(ev.popularity_percentile)}`} />}
        </div>
        <div className="stat">
          <span className="stat__value">{pct(ev.heatmap_coverage)}</span>
          <span className="stat__label">National heatmap cells above median</span>
          <span className="stat__hint">How much of the US map shows above-median affinity</span>
          {ev.heatmap_coverage != null && <Meter value={ev.heatmap_coverage} color="var(--senior)" label={`Coverage ${pct(ev.heatmap_coverage)}`} />}
        </div>
      </div>

      <p className="fame-skew">
        <span className="faint">Skew: </span>
        {ev.skew_description}
      </p>

      {hasData ? (
        <>
          <div className="fame-charts">
            <div className="fame-chart fame-chart--age">
              <h4 className="fame-chart__title">By age</h4>
              <DivergingChart data={age} height={210} label="Affinity by age group" />
            </div>
            <div className="fame-chart fame-chart--gender">
              <h4 className="fame-chart__title">By gender</h4>
              <DivergingChart data={gender} height={210} label="Affinity by gender" />
            </div>
          </div>
          <div className="legend caption">
            <span className="legend__item">
              <span className="legend__swatch" style={{ background: 'var(--senior)' }} /> Over-indexes vs. the general population
            </span>
            <span className="legend__item">
              <span className="legend__swatch" style={{ background: 'var(--neg)' }} /> Under-indexes
            </span>
            <span className="legend__item faint">Values run −1 to +1; zero is the population baseline</span>
          </div>
          <Disclosure summary={<span className="caption">Show values as a table</span>}>
            <div className="table-scroll">
              <table className="table fame-table">
                <thead>
                  <tr>
                    {[...age, ...gender].map((d) => (
                      <th key={d.key} scope="col" className="r">
                        {d.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    {[...age, ...gender].map((d) => (
                      <td key={d.key} className="r num">
                        {signed(d.value)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </Disclosure>
        </>
      ) : (
        <p className="footnote faint">Qloo returned no demographic signal for this brand.</p>
      )}

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
