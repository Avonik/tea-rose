import { num, possessive, signed } from '../lib/format'
import type { CompareRow, OverlapEvidence, RankedPeer, Resolution, Side } from '../types'
import RankGauge from './RankGauge'

function PeerTable({ title, peers, side, highlight }: { title: string; peers: RankedPeer[]; side: Side; highlight: Set<string> }) {
  const max = Math.max(0.0001, ...peers.map((p) => p.affinity ?? 0))
  return (
    <div className="peer-table">
      <h4 className="peer-table__title">{title}</h4>
      {peers.length === 0 ? (
        <p className="caption faint">No peers returned.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th className="r" scope="col">
                Rank
              </th>
              <th scope="col">Brand</th>
              <th scope="col" className="peer-table__aff">
                Affinity <span className="sr-only">(within this query)</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {peers.slice(0, 10).map((p) => (
              <tr key={p.entity_id + p.rank} data-highlight={highlight.has(p.entity_id) || highlight.has(p.name) || undefined}>
                <td className="r num faint">{p.rank}</td>
                <td>{p.name}</td>
                <td className="peer-table__aff">
                  <span className="bar-cell">
                    <span className={`bar-cell__bar bar-cell__bar--${side}`} style={{ width: `${((p.affinity ?? 0) / max) * 100}%` }} />
                    <span className="num caption">{num(p.affinity)}</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
  return (
    <div className={`compare-list compare-list--${side}`}>
      <h4 className="compare-list__title">{title}</h4>
      <ul>
        {rows.slice(0, 10).map((r, i) => {
          const v = rowValue(r)
          return (
            <li key={String(r.tag_id ?? r.entity_id ?? i)}>
              <span className="compare-list__name">{String(r.name ?? r.tag_id ?? r.entity_id ?? '–')}</span>
              <span className="compare-list__val num caption faint">
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

  return (
    <section className="card evidence" id="overlap" aria-labelledby="overlap-title">
      <div className="card__head">
        <div className="card__title">
          <p className="eyebrow">Channels & class of purchasers · relatedness</p>
          <h3 id="overlap-title">Shared purchasers</h3>
        </div>
        {ev.used_proxy && <span className="badge badge--proxy">Proxy path</span>}
      </div>

      <div className="overlap-hero">
        <div className="stat">
          <span className="stat__value">{ev.symmetric_percentile == null ? '–' : ev.symmetric_percentile.toFixed(2)}</span>
          <span className="stat__label">Symmetric overlap percentile (0 = no overlap, 1 = strongest)</span>
        </div>
        <p className="footnote muted overlap-hero__how">
          Mean of both directions. Each direction ranks one side among its category peers when Qloo is seeded with the
          other side. Ranks, not raw affinity, because affinity is normalized per query.
        </p>
      </div>

      <div className="gauges">
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

      <div className="peer-tables">
        <PeerTable title={`Top ${jUni?.description ?? 'peers'} for ${names.senior} fans`} peers={ev.top_peers_senior_seed} side="senior" highlight={highlight} />
        <PeerTable
          title={`Top ${sUni?.description ?? 'peers'} for ${ev.used_proxy ? 'the proxy’s' : `${names.junior}`} fans`}
          peers={ev.top_peers_junior_seed}
          side="junior"
          highlight={highlight}
        />
      </div>

      {(ev.shared_affinities.length > 0 || ev.distinct_to_senior.length > 0 || ev.distinct_to_junior.length > 0) && (
        <div className="compare">
          <h4 className="compare__title">Audience comparison</h4>
          <p className="caption faint compare__sub">
            From Qloo’s compare endpoint: {tagRows ? 'audience traits that connect or distinguish the two groups' : 'what both audiences like, and what sets each apart'}.
          </p>
          <div className="compare__grid">
            <CompareList title={tagRows ? 'Traits that connect them' : 'Shared by both audiences'} rows={ev.shared_affinities} side="shared" kind="shared" />
            <CompareList title={`Distinct to ${names.senior}`} rows={ev.distinct_to_senior} side="senior" kind="distinct" />
            <CompareList title={`Distinct to ${ev.used_proxy ? 'the proxy' : names.junior}`} rows={ev.distinct_to_junior} side="junior" kind="distinct" />
          </div>
        </div>
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
