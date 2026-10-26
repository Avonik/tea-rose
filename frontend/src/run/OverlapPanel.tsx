import type { ReactNode } from 'react'
import { Disclosure } from '../components/ui'
import { ordinalPercentile, possessive, rankPercentile, standing, standInLabel, wholePct } from '../lib/format'
import type { BridgingEvidence, CompareRow, OverlapEvidence, RankedPeer, Resolution, Side } from '../types'
import { BridgingGauge } from './BridgingPanel'
import { EvidenceNotes, QuestionBlock, StandIns } from './EvidenceKit'
import ScaleGauge, { HIGH_MARK, type SubMeasure } from './ScaleGauge'
import './evidence.css'

export { EvidenceNotes }

const SMALL_CATEGORY = 20

const lowerFirst = (t: string) => t.charAt(0).toLowerCase() + t.slice(1)

/** What an overlap percentile means, in the words a reader would use. */
function readOverlap(p: number): string {
  if (p >= HIGH_MARK) return 'the two brands draw from the same crowd'
  if (p > 0.35) return 'the data neither shows nor rules out shared customers'
  return 'the two crowds barely meet'
}

function PeerList({ title, peers, side, highlight, highlightLabel }: { title: string; peers: RankedPeer[]; side: Side; highlight: Set<string>; highlightLabel: string }) {
  const max = Math.max(0.0001, ...peers.map((p) => p.affinity ?? 0))
  return (
    <div className="peer">
      <h4 className="group-label peer__title">{title}</h4>
      {peers.length === 0 ? (
        <p className="group__note">No brands returned.</p>
      ) : (
        <ol className="group peer__list" aria-label={`${title}: rank, brand, affinity as a share of the strongest`}>
          {peers.slice(0, 10).map((p) => {
            const hit = highlight.has(p.entity_id) || highlight.has(p.name)
            const share = (p.affinity ?? 0) / max
            return (
              <li key={p.entity_id + p.rank} className="group__row peer__row" data-hit={hit || undefined}>
                <span className="peer__rank num">{p.rank}</span>
                <span className="peer__name">
                  {p.name}
                  {hit && (
                    <span className="badge">
                      <span className={`dot dot--${side === 'senior' ? 'junior' : 'senior'}`} aria-hidden="true" />
                      {highlightLabel}
                    </span>
                  )}
                </span>
                <span className="peer__aff">
                  <span className="bar" aria-hidden="true">
                    <span className={`bar__fill bar__fill--${side}`} style={{ width: `${share * 100}%` }} />
                  </span>
                  <span className="num caption secondary">
                    <span className="sr-only">affinity </span>
                    {wholePct(share)}
                  </span>
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

const isTagRow = (r: CompareRow) => r.tag_id != null || (r.entity_id == null && r.score != null)

function rowValue(r: CompareRow): number | null {
  if (r.score != null) return r.score
  if (r.delta != null) return r.delta
  if (r.a_affinity != null && r.b_affinity != null) return Math.min(r.a_affinity, r.b_affinity)
  return null
}

function CompareList({ title, rows, side, kind }: { title: string; rows: CompareRow[]; side: Side | 'shared'; kind: 'shared' | 'distinct' }) {
  if (!rows.length) return null
  const sorted = (kind === 'distinct' ? [...rows].sort((a, b) => Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0)) : rows).slice(0, 10)
  const max = Math.max(0.0001, ...sorted.map((r) => Math.abs(rowValue(r) ?? 0)))
  return (
    <div className="compare-list">
      <h4 className="group-label compare-list__title">
        {side !== 'shared' && <span className={`dot dot--${side}`} aria-hidden="true" />}
        {title}
      </h4>
      <ol className="group" aria-label={`${title}, strongest first`}>
        {sorted.map((r, i) => {
          const v = rowValue(r)
          return (
            <li key={String(r.tag_id ?? r.entity_id ?? i)} className="group__row compare-list__row">
              <span className="compare-list__name">{String(r.name ?? r.tag_id ?? r.entity_id ?? '–')}</span>
              <span className="bar compare-list__bar" aria-hidden="true">
                <span className={`bar__fill bar__fill--${side}`} style={{ width: `${v == null ? 0 : (Math.abs(v) / max) * 100}%` }} />
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

interface Direction {
  /** Fans of `seed` were asked; `target` was looked for among the brands in `category`. */
  seed: string
  /** "Pet-food stand-ins for Bad Spaniels" when the seed side was measured through stand-ins. */
  seedStandIns?: string
  /** The same label for the target side. */
  targetStandIns?: string
  target: string
  targetIsStandIn: boolean
  category: string
  rank: number | null
  universe: number | null
  percentile: number | null
  censored: boolean
  depth: number | null
  ratio: number | null
  tone: Side
}

function directionMeasure(key: string, d: Direction): SubMeasure {
  const subject = d.targetIsStandIn ? `the stand-ins for ${d.target}` : d.target
  const verb = d.targetIsStandIn ? 'sit' : 'sits'
  const liked = d.targetStandIns ? `the ${lowerFirst(d.targetStandIns)}` : d.target
  const label = d.seedStandIns ? `${d.seedStandIns}: their fans like ${liked}` : `${possessive(d.seed)} fans like ${liked}`
  const small = d.universe != null && d.universe < SMALL_CATEGORY ? ` A small category (${d.universe} brands), so the rank is coarse.` : ''
  if (d.censored || (d.percentile == null && d.rank == null)) {
    const depth = d.depth ?? 150
    const beyond = `beyond the ${depth} strongest`
    if (d.ratio != null)
      return {
        key,
        label,
        tone: d.tone,
        censored: true,
        value: d.ratio,
        display: `${wholePct(d.ratio)} of the category’s strongest`,
        note: (
          <>
            Among {d.category}, {subject} {d.targetIsStandIn ? 'rank' : 'ranks'} {beyond} for {possessive(d.seed)} fans; measured directly, the affinity is{' '}
            {wholePct(d.ratio)} of the category’s strongest.{small}
          </>
        ),
      }
    return {
      key,
      label,
      tone: d.tone,
      censored: true,
      value: null,
      display: beyond,
      note: (
        <>
          Among {d.category}, {subject} did not appear among the {depth} strongest for {possessive(d.seed)} fans.
        </>
      ),
    }
  }
  const p = d.percentile ?? rankPercentile(d.rank, d.universe)
  return {
    key,
    label,
    tone: d.tone,
    value: p,
    display: ordinalPercentile(p),
    note: (
      <>
        Among {d.category}, {subject} {verb} {standing(p)} by affinity to {possessive(d.seed)} fans
        {d.rank != null && d.universe ? ` (${d.targetIsStandIn ? 'mean rank' : 'rank'} ${Math.round(d.rank)} of ${d.universe.toLocaleString('en-US')})` : ''}.{small}
      </>
    ),
  }
}

/** Question 1: do the same people buy both? Fans overlap in both directions, plus bridging. */
export default function OverlapPanel({
  ev,
  bridging,
  resolution,
  names,
}: {
  ev: OverlapEvidence | null
  bridging?: BridgingEvidence | null
  resolution: Resolution | null
  names: { senior: string; junior: string }
}) {
  const uni = (side: Side) => resolution?.universes.find((u) => u.side === side)
  const jUni = uni('junior')
  const sUni = uni('senior')
  const proxy = resolution?.junior_proxy && (ev?.used_proxy ?? true) ? resolution.junior_proxy : null
  const seniorProxy = resolution?.senior_proxy ?? null

  let gauges: ReactNode = null
  let lead: ReactNode = `Qloo did not return an overlap measure for ${names.senior} and ${names.junior}.`
  let detail: ReactNode = null

  if (ev) {
    const sj = directionMeasure('s2j', {
      seed: names.senior,
      seedStandIns: seniorProxy ? standInLabel(seniorProxy, names.senior) : undefined,
      targetStandIns: proxy ? standInLabel(proxy, names.junior) : undefined,
      target: names.junior,
      targetIsStandIn: !!proxy,
      category: jUni?.description ?? `brands in ${possessive(names.junior)} category`,
      rank: ev.senior_to_junior_rank,
      universe: ev.senior_to_junior_universe ?? jUni?.size ?? null,
      percentile: ev.senior_to_junior_percentile ?? null,
      censored: !!ev.senior_to_junior_censored,
      depth: ev.senior_to_junior_depth_scanned ?? null,
      ratio: ev.senior_to_junior_affinity_ratio ?? null,
      tone: 'junior',
    })
    const js = directionMeasure('j2s', {
      seed: names.junior,
      seedStandIns: proxy ? standInLabel(proxy, names.junior) : undefined,
      targetStandIns: seniorProxy ? standInLabel(seniorProxy, names.senior) : undefined,
      target: names.senior,
      targetIsStandIn: !!seniorProxy,
      category: sUni?.description ?? `brands in ${possessive(names.senior)} category`,
      rank: ev.junior_to_senior_rank,
      universe: ev.junior_to_senior_universe ?? sUni?.size ?? null,
      percentile: ev.junior_to_senior_percentile ?? null,
      censored: !!ev.junior_to_senior_censored,
      depth: ev.junior_to_senior_depth_scanned ?? null,
      ratio: ev.junior_to_senior_affinity_ratio ?? null,
      tone: 'senior',
    })

    const p = ev.symmetric_percentile
    const ratio = ev.symmetric_affinity_ratio ?? null
    let value: number | null = p
    let display = ordinalPercentile(p)
    let meaning: ReactNode
    if (p != null) {
      const one = [sj, js].filter((s) => s.censored).length === 1 ? ' Only one direction has a rank, so the average is that direction alone.' : ''
      meaning = (
        <>
          Taking both directions together, each brand sits {standing(p)} of the other’s category: {readOverlap(p)}.{one}
        </>
      )
      lead = (
        <>
          Asked what fans of each brand also like, Qloo places the other brand at the {ordinalPercentile(p)} of its category on average: {readOverlap(p)}.
        </>
      )
    } else if (ratio != null) {
      value = ratio
      display = `${wholePct(ratio)} of the strongest`
      meaning = (
        <>
          Neither brand ranks among the strongest of the other’s category; measured directly, their affinity is {wholePct(ratio)} of the category’s strongest on
          average.
        </>
      )
      lead = <>Neither brand shows up among the strongest brands of the other’s category, so there is no rank, only a direct affinity reading.</>
    } else {
      meaning = <>Neither direction could be measured.</>
      lead = <>Qloo returned too little to place either brand in the other’s category.</>
    }

    gauges = (
      <ScaleGauge
        id="overlap-gauge"
        title="Fans overlap, both ways"
        value={value}
        display={display}
        low="separate crowds"
        high="same crowd"
        meaning={meaning}
        censored={p == null && ratio != null}
        subs={[sj, js]}
      />
    )

    const highlight = new Set<string>([
      ...(proxy?.comparator_brand_ids ?? []),
      ...(proxy?.comparator_brand_names ?? []),
      ...(resolution?.junior.entity_id ? [resolution.junior.entity_id] : []),
      ...(resolution?.senior.entity_id ? [resolution.senior.entity_id] : []),
    ])
    const tagRows = ev.shared_affinities.some(isTagRow)
    const hasCompare = ev.shared_affinities.length > 0 || ev.distinct_to_senior.length > 0 || ev.distinct_to_junior.length > 0
    detail = (
      <Disclosure summary="Show who else their fans like" className="qb__more">
        <div className="qb__more-body">
          <EvidenceNotes notes={ev.notes} />
          <div className="ev__pair">
            <PeerList
              title={`Top ${jUni?.description ?? 'brands'} for ${possessive(names.senior)} fans`}
              peers={ev.top_peers_senior_seed}
              side="senior"
              highlight={highlight}
              highlightLabel={proxy ? 'stand-in' : names.junior}
            />
            <PeerList
              title={`Top ${sUni?.description ?? 'brands'} for ${proxy ? `fans of the ${lowerFirst(standInLabel(proxy, names.junior))}` : `${possessive(names.junior)} fans`}`}
              peers={ev.top_peers_junior_seed}
              side="junior"
              highlight={highlight}
              highlightLabel={names.senior}
            />
          </div>
          <p className="caption tertiary">Bars and percentages show each brand’s affinity as a share of the strongest brand in its list.</p>
          {hasCompare && (
            <div className="compare">
              <div className="compare__head">
                <h4 className="t-title-2">What sets the two audiences apart</h4>
                <p className="footnote secondary">
                  From Qloo’s compare endpoint: {tagRows ? 'audience traits that connect or distinguish the two groups' : 'what both audiences like, and what sets each apart'},
                  strongest first.
                </p>
              </div>
              <div className="compare__grid">
                <CompareList title={tagRows ? 'Traits that connect them' : 'Liked by both audiences'} rows={ev.shared_affinities} side="shared" kind="shared" />
                <CompareList title={`Only ${names.senior}`} rows={ev.distinct_to_senior} side="senior" kind="distinct" />
                <CompareList title={`Only ${proxy ? `the ${lowerFirst(standInLabel(proxy, names.junior))}` : names.junior}`} rows={ev.distinct_to_junior} side="junior" kind="distinct" />
              </div>
            </div>
          )}
        </div>
      </Disclosure>
    )
  }

  return (
    <QuestionBlock
      id="overlap"
      n={1}
      title="Do the same people buy both?"
      lead={
        <>
          {lead} Courts weigh this under relatedness of goods (would buyers expect both products from one company) and channels and purchasers (do the two reach
          the same customers).
        </>
      }
      standIns={
        <>
          <StandIns proxy={proxy} name={names.junior} />
          <StandIns proxy={seniorProxy} name={names.senior} />
        </>
      }
      gauges={
        <>
          {gauges}
          {bridging && <BridgingGauge ev={bridging} resolution={resolution} senior={names.senior} />}
        </>
      }
      detail={detail}
    />
  )
}
