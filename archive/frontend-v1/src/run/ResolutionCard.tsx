import { IconCheck } from '../components/icons'
import { Disclosure, Meter } from '../components/ui'
import { pct, shortId, tagName, tagOptionId } from '../lib/format'
import type { ProxyResolution, Resolution, ResolvedBrand, Side } from '../types'

function ProxyBlock({ proxy }: { proxy: ProxyResolution }) {
  const chosen = new Set(proxy.chosen_tag_ids)
  return (
    <div className="proxy">
      <p className="proxy__lead footnote">
        Not in Qloo’s graph. The goods phrase <q className="party__quote">{proxy.goods_phrase}</q> was mapped onto Qloo’s
        brand-category taxonomy; the agent could only pick from these nodes.
      </p>
      {proxy.fit_note && <p className="footnote faint">Category fit: {proxy.fit_note}.</p>}
      <ul className="tag-menu" aria-label="Tag options returned by /v2/tags">
        {proxy.tag_options.map((t, i) => {
          const id = tagOptionId(t)
          const on = chosen.has(id)
          return (
            <li key={id || i} className="tag-menu__item" data-chosen={on}>
              <span className="tag-menu__check" aria-hidden="true">
                {on && <IconCheck size={12} />}
              </span>
              <span className="tag-menu__name">{String(t.name ?? tagName(id))}</span>
              <span className="sr-only">{on ? ' (chosen)' : ' (not chosen)'}</span>
              <code className="tag-menu__id">{id}</code>
            </li>
          )
        })}
      </ul>
      <p className="footnote">
        <span className="faint">Why: </span>
        {proxy.rationale}
      </p>
      {proxy.comparator_brand_names.length > 0 && (
        <div className="party__row">
          <span className="party__key">Comparators</span>
          <span className="chips">
            {proxy.comparator_brand_names.map((n) => (
              <span key={n} className={`chip chip--${proxy.side}`}>
                {n}
              </span>
            ))}
          </span>
        </div>
      )}
    </div>
  )
}

function SideBlock({ side, brand, proxy }: { side: Side; brand: ResolvedBrand; proxy: ProxyResolution | null }) {
  const resolved = !!brand.entity_id
  return (
    <div className={`resolve-side resolve-side--${side}`}>
      <div className="resolve-side__head">
        <p className="eyebrow">{side === 'senior' ? 'Senior' : 'Junior'}</p>
        {resolved ? <span className="badge">Qloo entity</span> : proxy ? <span className="badge badge--proxy">Proxy</span> : <span className="badge badge--proxy">Unresolved</span>}
      </div>
      <h3 className="resolve-side__name">{brand.entity_name ?? brand.query}</h3>
      {resolved ? (
        <>
          <p className="caption faint">
            Searched <q>{brand.query}</q> · <code title={brand.entity_id ?? ''}>{shortId(brand.entity_id ?? '')}</code>
          </p>
          {brand.popularity != null && (
            <div className="resolve-side__pop">
              <span className="caption muted">Popularity percentile</span>
              <Meter value={brand.popularity} color={`var(--${side})`} label={`Popularity percentile ${pct(brand.popularity)}`} />
              <span className="caption num">{pct(brand.popularity, 1)}</span>
            </div>
          )}
          {brand.disambiguation_note && <p className="footnote muted">{brand.disambiguation_note}</p>}
          {brand.candidates_considered.length > 0 && (
            <Disclosure summary={<span className="caption">Candidates considered ({brand.candidates_considered.length})</span>}>
              <ul className="plain-list caption">
                {brand.candidates_considered.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </Disclosure>
          )}
        </>
      ) : (
        <>
          {brand.disambiguation_note && <p className="footnote muted">{brand.disambiguation_note}</p>}
          {proxy && <ProxyBlock proxy={proxy} />}
        </>
      )}
    </div>
  )
}

export default function ResolutionCard({ resolution: r }: { resolution: Resolution }) {
  const menus = [r.senior_proxy, r.junior_proxy]
  return (
    <section className="card" id="resolution" aria-labelledby="resolution-title">
      <div className="card__head">
        <div className="card__title">
          <h2 id="resolution-title">Who was measured</h2>
          <p className="muted footnote">How each party was found in Qloo, and the peer sets that make a rank meaningful.</p>
        </div>
      </div>
      <div className="resolve-grid">
        <SideBlock side="senior" brand={r.senior} proxy={r.senior_proxy} />
        <SideBlock side="junior" brand={r.junior} proxy={r.junior_proxy} />
      </div>
      {r.universes.length > 0 && (
        <div className="universes">
          <p className="eyebrow">Comparison universes</p>
          <ul className="universes__list">
            {r.universes.map((u) => (
              <li key={u.side + u.description} className={`universe universe--${u.side}`}>
                <span className="universe__size num">{u.size.toLocaleString('en-US')}</span>
                <span>
                  <strong>{u.description}</strong>
                  <span className="caption faint">
                    {' '}
                    · {u.side === 'senior' ? 'senior' : 'junior'}’s peers · {u.tag_ids.map((t) => tagName(t, menus)).join(', ')}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
