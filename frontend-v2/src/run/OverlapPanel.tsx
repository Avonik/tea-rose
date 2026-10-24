import { num, possessive, readPercentile, signed } from '../lib/format'
import { AnimatedNumber } from '../motion/AnimatedNumber'
import type { CompareRow, OverlapEvidence, RankedPeer, Resolution, Side } from '../types'
import { EvidenceNotes, EvidenceSplit } from './EvidenceKit'
import RankGauge from './RankGauge'
import './evidence.css'

export { EvidenceNotes }

function PeerList({
  title,
  peers,
  side,
  highlight,
  highlightLabel,
}: {
  title: string
  peers: RankedPeer[]
  side: Side
  highlight: Set<string>
  highlightLabel: string
}) {
  const max = Math.max(0.0001, ...peers.map((p) => p.affinity ?? 0))
  return (
    <div className="peer">
      <h4 className="group-label peer__title">{title}</h4>
      {peers.length === 0 ? (
        <p className="group__note">No peers returned.</p>
      ) : (
        <ol className="group peer__list" aria-label={`${title}: rank, brand, affinity within this query`}>
          {peers.slice(0, 10).map((p) => {
            const hit = highlight.has(p.entity_id) || highlight.has(p.name)
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
                    <span className={`bar__fill bar__fill--${side}`} style={{ width: `${((p.affinity ?? 0) / max) * 100}%` }} />
                  </span>
                  <span className="num caption secondary">
                    <span className="sr-only">affinity </span>
                    {num(p.affinity)}
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
      <ul className="group">
        {sorted.map((r, i) => {
          const v = rowValue(r)
          return (
            <li key={String(r.tag_id ?? r.entity_id ?? i)} className="group__row compare-list__row">
              <span className="compare-list__name">{String(r.name ?? r.tag_id ?? r.entity_id ?? '–')}</span>
              <span className="bar compare-list__bar" aria-hidden="true">
                <span className={`bar__fill bar__fill--${side}`} style={{ width: `${v == null ? 0 : (Math.abs(v) / max) * 100}%` }} />
              </span>
              <span className="compare-list__val num caption secondary">
                {v == null ? '' : kind === 'distinct' && r.delta != null ? `Δ ${signed(Math.abs(r.delta))}` : num(v)}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function OverlapPanel({
  ev,
  resolution,
  names,
}: {
  ev: OverlapEvidence
  resolution: Resolution | null
  names: { senior: string; junior: string }
}) {
  const uni = (side: Side) => resolution?.universes.find((u) => u.side === side)
  const jUni = uni('junior')
  const sUni = uni('senior')
  const proxy = resolution?.junior_proxy
  const juniorSubject = ev.used_proxy && proxy ? `${possessive(names.junior)} proxy (${proxy.comparator_brand_names.length || 'category'} comparators, mean rank)` : names.junior
  const highlight = new Set<string>([
    ...(proxy?.comparator_brand_ids ?? []),
    ...(proxy?.comparator_brand_names ?? []),
    ...(resolution?.junior.entity_id ? [resolution.junior.entity_id] : []),
    ...(resolution?.senior.entity_id ? [resolution.senior.entity_id] : []),
  ])
  const tagRows = ev.shared_affinities.some(isTagRow)
  const hasCompare = ev.shared_affinities.length > 0 || ev.distinct_to_senior.length > 0 || ev.distinct_to_junior.length > 0

  return (
    <EvidenceSplit
      id="overlap"
      eyebrow="Shared purchasers · channels & class of purchasers · relatedness"
      badge={ev.used_proxy ? <span className="badge">Proxy path</span> : undefined}
      title="Do the two brands share purchasers?"
      numeral={<AnimatedNumber value={ev.symmetric_percentile} className="numeral" />}
      numeralLabel="Shared-purchaser percentile, both directions averaged"
      reading={ev.symmetric_percentile != null ? readPercentile(ev.symmetric_percentile) : undefined}
      left={
        <>
          <p className="footnote secondary ev__how">
            <strong>How to read it.</strong> Ask Qloo what fans of one brand also like, then find the other brand among its category
            peers. 1.00 means it ranks first, 0.50 means the middle of the pack, near 0 means it barely shows up. Ranks, not raw
            affinity, because Qloo normalizes affinity within each query.
          </p>
          <EvidenceNotes notes={ev.notes} />
        </>
      }
      right={
        <div className="group ev__chart gauges">
          <RankGauge
            eyebrow={`Seeded by ${names.senior}`}
            subject={juniorSubject}
            rank={ev.senior_to_junior_rank}
            universe={ev.senior_to_junior_universe ?? jUni?.size ?? null}
            universeLabel={jUni?.description ?? 'junior-category brands'}
            percentile={ev.senior_to_junior_percentile}
            side="junior"
          />
          <RankGauge
            eyebrow={`Seeded by ${ev.used_proxy ? `${possessive(names.junior)} proxy` : names.junior}`}
            subject={names.senior}
            rank={ev.junior_to_senior_rank}
            universe={ev.junior_to_senior_universe ?? sUni?.size ?? null}
            universeLabel={sUni?.description ?? 'senior-category brands'}
            percentile={ev.junior_to_senior_percentile}
            side="senior"
          />
        </div>
      }
      below={
        <>
          <div className="ev__pair">
            <PeerList
              title={`Top ${jUni?.description ?? 'peers'} for ${names.senior} fans`}
              peers={ev.top_peers_senior_seed}
              side="senior"
              highlight={highlight}
              highlightLabel={ev.used_proxy ? 'comparator' : 'party'}
            />
            <PeerList
              title={`Top ${sUni?.description ?? 'peers'} for ${ev.used_proxy ? 'the proxy’s' : names.junior} fans`}
              peers={ev.top_peers_junior_seed}
              side="junior"
              highlight={highlight}
              highlightLabel="party"
            />
          </div>
          {hasCompare && (
            <div className="compare">
              <div className="compare__head">
                <h4 className="t-title-2">Audience comparison</h4>
                <p className="footnote secondary">
                  From Qloo’s compare endpoint: {tagRows ? 'audience traits that connect or distinguish the two groups' : 'what both audiences like, and what sets each apart'}.
                </p>
              </div>
              <div className="compare__grid">
                <CompareList title={tagRows ? 'Traits that connect them' : 'Shared by both audiences'} rows={ev.shared_affinities} side="shared" kind="shared" />
                <CompareList title={`Distinct to ${names.senior}`} rows={ev.distinct_to_senior} side="senior" kind="distinct" />
                <CompareList title={`Distinct to ${ev.used_proxy ? 'the proxy' : names.junior}`} rows={ev.distinct_to_junior} side="junior" kind="distinct" />
              </div>
            </div>
          )}
        </>
      }
    />
  )
}
