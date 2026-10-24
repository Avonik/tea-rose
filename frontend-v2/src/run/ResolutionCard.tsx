import { IconCheck } from '../components/icons'
import { Disclosure, Meter } from '../components/ui'
import { pct, shortId, tagName, tagOptionId } from '../lib/format'
import type { ProxyResolution, Resolution, ResolvedBrand, Side } from '../types'

function ProxyBlock({ proxy }: { proxy: ProxyResolution }) {
  const chosen = new Set(proxy.chosen_tag_ids)
  return (
    <>
      <div className="group__row group__sep resolve__lead">
        <p className="footnote secondary">
          Not in Qloo’s graph. The goods phrase <q className="serif">{proxy.goods_phrase}</q> went verbatim to <code>/v2/tags</code>; the
          agent could only pick from this menu.
        </p>
      </div>
      <ul className="tag-menu" aria-label="Tag options returned by /v2/tags">
        {proxy.tag_options.map((t, i) => {
          const id = tagOptionId(t)
          const on = chosen.has(id)
          return (
            <li key={id || i} className="group__row group__sep tag-menu__item" data-chosen={on || undefined}>
              <span className="tag-menu__check" aria-hidden="true">
                {on && <IconCheck size={14} />}
              </span>
              <span className="group__main">
                <span className="tag-menu__name">{String(t.name ?? tagName(id))}</span>
                <code className="tag-menu__id">{id}</code>
              </span>
              <span className="sr-only">{on ? ' (chosen)' : ' (not chosen)'}</span>
              {on && <span className="group__value caption">Chosen</span>}
            </li>
          )
        })}
      </ul>
      <div className="group__row group__row--top group__sep">
        <span className="resolve__k">Why</span>
        <span className="group__main footnote">{proxy.rationale}</span>
      </div>
      {proxy.comparator_brand_names.length > 0 && (
        <div className="group__row group__row--top group__sep">
          <span className="resolve__k">Comparators</span>
          <span className="group__main">
            <span className="chips">
              {proxy.comparator_brand_names.map((n) => (
                <span key={n} className="chip chip--sm">
                  <span className={`dot dot--${proxy.side}`} aria-hidden="true" />
                  {n}
                </span>
              ))}
            </span>
          </span>
        </div>
      )}
    </>
  )
}

function SideGroup({ side, brand, proxy }: { side: Side; brand: ResolvedBrand; proxy: ProxyResolution | null }) {
  const resolved = !!brand.entity_id
  return (
    <div className="resolve-side">
      <p className="group-label">{side === 'senior' ? 'Senior' : 'Junior'}</p>
      <div className="group">
        <div className="group__header resolve-side__head">
          <span className={`dot dot--${side}`} aria-hidden="true" />
          <h3 className="t-title-2">{brand.entity_name ?? brand.query}</h3>
          <span className="badge">{resolved ? 'Qloo entity' : proxy ? 'Proxy' : 'Unresolved'}</span>
        </div>
        {resolved ? (
          <>
            <div className="group__row group__sep">
              <span className="resolve__k">Searched</span>
              <span className="group__main footnote">
                <q>{brand.query}</q> · <code title={brand.entity_id ?? ''}>{shortId(brand.entity_id ?? '')}</code>
              </span>
            </div>
            {brand.popularity != null && (
              <div className="group__row group__sep">
                <span className="resolve__k">Popularity</span>
                <span className="group__main resolve__pop">
                  <Meter value={brand.popularity} color={`var(--${side})`} label={`Popularity percentile ${pct(brand.popularity)}`} />
                </span>
                <span className="group__value num">{pct(brand.popularity, 1)}</span>
              </div>
            )}
            {brand.disambiguation_note && (
              <div className="group__row group__sep">
                <p className="footnote secondary">{brand.disambiguation_note}</p>
              </div>
            )}
            {brand.candidates_considered.length > 0 && (
              <div className="group__row group__sep resolve__candidates">
                <Disclosure summary={<>Candidates considered ({brand.candidates_considered.length})</>}>
                  <ul className="footnote resolve__cand-list">
                    {brand.candidates_considered.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </Disclosure>
              </div>
            )}
          </>
        ) : (
          <>
            {brand.disambiguation_note && (
              <div className="group__row group__sep">
                <p className="footnote secondary">{brand.disambiguation_note}</p>
              </div>
            )}
            {proxy && <ProxyBlock proxy={proxy} />}
          </>
        )}
      </div>
    </div>
  )
}

/** Who was measured: how each party was found in Qloo, and the peer sets that make a rank meaningful. */
export default function ResolutionCard({ resolution: r }: { resolution: Resolution }) {
  const menus = [r.senior_proxy, r.junior_proxy]
  return (
    <div className="resolution" aria-labelledby="resolution-title">
      <div className="band__head">
        <p className="eyebrow">Resolution</p>
        <h2 id="resolution-title" className="t-headline">
          Who was measured.
        </h2>
        <p className="t-subtitle">How each party was found in Qloo, and the peer sets that make a rank meaningful.</p>
      </div>
      <div className="resolve-grid">
        <SideGroup side="senior" brand={r.senior} proxy={r.senior_proxy} />
        <SideGroup side="junior" brand={r.junior} proxy={r.junior_proxy} />
      </div>
      {r.universes.length > 0 && (
        <div className="universes">
          <h3 className="group-label">Comparison universes</h3>
          <ul className="group">
            {r.universes.map((u) => (
              <li key={u.side + u.description} className="group__row universe">
                <span className="universe__size num">{u.size.toLocaleString('en-US')}</span>
                <span className="group__main">
                  <span className="group__title">{u.description}</span>
                  <span className="group__sub">
                    <span className={`dot dot--${u.side} universe__dot`} aria-hidden="true" />
                    {u.side === 'senior' ? 'senior' : 'junior'}’s peers · {u.tag_ids.map((t) => tagName(t, menus)).join(', ')}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
