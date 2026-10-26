import { Component, lazy, Suspense, useState, type ReactNode } from 'react'
import { num, pct } from '../lib/format'
import type { ZoneEvidence } from '../types'

const ZoneMap = lazy(() => import('./ZoneMap'))

class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed)
      return <div className="zone-map zone-map--fallback">The map could not be displayed. The regions are listed alongside.</div>
    return this.props.children
  }
}

export default function ZonePanel({ ev, senior, junior, juniorIsProxy }: { ev: ZoneEvidence; senior: string; junior: string; juniorIsProxy: boolean }) {
  const [showSenior, setShowSenior] = useState(true)
  const [showJunior, setShowJunior] = useState(false)
  const hasJunior = ev.junior_points.length > 0
  const juniorLabel = juniorIsProxy ? `${junior} (proxy)` : junior
  const maxShare = Math.max(0.0001, ...ev.top_regions.map((r) => Number(r.share ?? 0)))

  return (
    <section className="card evidence" id="zone" aria-labelledby="zone-title">
      <div className="card__head">
        <div className="card__title">
          <p className="eyebrow">Zone of reputation</p>
          <h3 id="zone-title">Where is the mark known?</h3>
        </div>
      </div>

      <div className="zone">
        <div className="zone__map">
          {ev.points.length === 0 && !hasJunior ? (
            <div className="zone-map zone-map--fallback">Qloo returned no heatmap cells for this brand.</div>
          ) : (
            <MapBoundary>
              <Suspense
                fallback={
                  <div className="zone-map">
                    <div className="zone-map__overlay">
                      <span className="spinner" aria-hidden="true" /> Loading map
                    </div>
                  </div>
                }
              >
                <ZoneMap
                  points={ev.points}
                  juniorPoints={ev.junior_points}
                  showSenior={showSenior}
                  showJunior={showJunior}
                  seniorName={senior}
                  juniorName={juniorLabel}
                />
              </Suspense>
            </MapBoundary>
          )}
          <div className="zone__controls no-print" role="group" aria-label="Map layers">
            <button type="button" className="layer-toggle layer-toggle--senior" aria-pressed={showSenior} onClick={() => setShowSenior((v) => !v)}>
              <span className="layer-toggle__swatch" aria-hidden="true" />
              {senior}
              <span className="faint num">· {ev.points.length}</span>
            </button>
            <button
              type="button"
              className="layer-toggle layer-toggle--junior"
              aria-pressed={showJunior}
              onClick={() => setShowJunior((v) => !v)}
              disabled={!hasJunior}
              title={hasJunior ? undefined : 'No heatmap for the junior side'}
            >
              <span className="layer-toggle__swatch" aria-hidden="true" />
              {juniorLabel}
              <span className="faint num">· {ev.junior_points.length}</span>
            </button>
          </div>
          <div className="heat-legend caption faint" aria-hidden="true">
            <span>Lower</span>
            {showSenior && <span className="heat-legend__ramp heat-legend__ramp--senior" />}
            {showJunior && <span className="heat-legend__ramp heat-legend__ramp--junior" />}
            <span>Higher relative affinity</span>
          </div>
        </div>

        <div className="zone__side">
          <div className="stats zone__stats">
            <div className="stat">
              <span className="stat__value">{num(ev.concentration_index)}</span>
              <span className="stat__label">Concentration (Gini; 0 = even, 1 = few places)</span>
            </div>
            <div className="stat">
              <span className="stat__value">{ev.geographic_overlap == null ? '–' : num(ev.geographic_overlap)}</span>
              <span className="stat__label">Geographic overlap with the junior side (cosine)</span>
              <span className="stat__hint">1 = the two maps match; 0 = no places in common</span>
            </div>
          </div>
          {ev.top_regions.length > 0 && (
            <div className="regions">
              <h4 className="regions__title">Top regions for {senior}</h4>
              <ol className="regions__list">
                {ev.top_regions.map((r, i) => {
                  const share = Number(r.share ?? 0)
                  return (
                    <li key={String(r.label ?? i)}>
                      <span className="regions__name">{String(r.label ?? `Region ${i + 1}`)}</span>
                      <span className="regions__bar" aria-hidden="true">
                        <span style={{ width: `${(share / maxShare) * 100}%` }} />
                      </span>
                      <span className="regions__share num caption">{pct(share, 1)}</span>
                    </li>
                  )
                })}
              </ol>
              <p className="caption faint">Share of total affinity in the returned cells.</p>
            </div>
          )}
        </div>
      </div>

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
