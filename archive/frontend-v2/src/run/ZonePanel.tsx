import { Component, lazy, Suspense, useState, type ReactNode } from 'react'
import { num, pct } from '../lib/format'
import { AnimatedNumber } from '../motion/AnimatedNumber'
import type { ZoneEvidence } from '../types'
import { EvidenceNotes, EvidenceSplit } from './EvidenceKit'
import './evidence.css'

const ZoneMap = lazy(() => import('./ZoneMap'))

class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed) return <div className="zone-map zone-map--fallback">The map could not be displayed. The regions are listed alongside.</div>
    return this.props.children
  }
}

function LayerToggle({ side, on, onToggle, label, count, disabled, title }: { side: 'senior' | 'junior'; on: boolean; onToggle: () => void; label: string; count: number; disabled?: boolean; title?: string }) {
  return (
    <button type="button" className="layer-toggle pressable" aria-pressed={on} onClick={onToggle} disabled={disabled} title={title}>
      <span className={`layer-toggle__swatch dot dot--${side}`} aria-hidden="true" />
      <span className="layer-toggle__label">{label}</span>
      <span className="layer-toggle__count num">{count}</span>
    </button>
  )
}

/** Plain words for a Gini concentration index. Descriptive only. */
function readConcentration(g: number | null): string | undefined {
  if (g == null) return undefined
  if (g < 0.3) return 'spread widely: affinity is found across most of the map'
  if (g < 0.55) return 'moderately concentrated: some regions clearly lead'
  return 'concentrated: a few places hold most of the affinity'
}

export default function ZonePanel({ ev, senior, junior, juniorIsProxy }: { ev: ZoneEvidence; senior: string; junior: string; juniorIsProxy: boolean }) {
  const [showSenior, setShowSenior] = useState(true)
  const [showJunior, setShowJunior] = useState(false)
  const hasJunior = ev.junior_points.length > 0
  const juniorLabel = juniorIsProxy ? `${junior} (proxy)` : junior
  const maxShare = Math.max(0.0001, ...ev.top_regions.map((r) => Number(r.share ?? 0)))
  const hasAny = ev.points.length > 0 || hasJunior

  const loading = (
    <div className="zone-map">
      <div className="zone-map__overlay">
        <span className="spinner" aria-hidden="true" /> Loading map
      </div>
    </div>
  )

  return (
    <EvidenceSplit
      id="zone"
      eyebrow="Zone of reputation"
      title="Where is the mark known?"
      numeral={<AnimatedNumber value={ev.concentration_index} className="numeral" />}
      numeralLabel="Concentration · Gini: 0 = spread evenly, 1 = a few places"
      reading={readConcentration(ev.concentration_index)}
      left={
        <>
          <dl className="group">
            <div className="group__row group__row--top">
              <dt className="group__main">
                <span className="group__title">Geographic overlap with the junior side</span>
                <span className="group__sub">Cosine: 1 = the two maps match; 0 = no places in common</span>
              </dt>
              <dd className="ev__stat-value">
                <AnimatedNumber value={ev.geographic_overlap} />
              </dd>
            </div>
          </dl>
          {ev.top_regions.length > 0 && (
            <div className="regions">
              <h4 className="group-label">Top regions for {senior}</h4>
              <ol className="group">
                {ev.top_regions.map((r, i) => {
                  const share = Number(r.share ?? 0)
                  return (
                    <li key={String(r.label ?? i)} className="group__row regions__row">
                      <span className="regions__name">{String(r.label ?? `Region ${i + 1}`)}</span>
                      <span className="bar regions__bar" aria-hidden="true">
                        <span className="bar__fill bar__fill--senior" style={{ width: `${(share / maxShare) * 100}%` }} />
                      </span>
                      <span className="regions__share num caption secondary">{pct(share, 1)}</span>
                    </li>
                  )
                })}
              </ol>
              <p className="group__note caption">Share of total affinity in the returned cells.</p>
            </div>
          )}
          {ev.concentration_index != null && <p className="sr-only">Concentration index {num(ev.concentration_index)}.</p>}
          <EvidenceNotes notes={ev.notes} />
        </>
      }
      right={
        <div className="ev__chart zone">
          <div className="zone__canvas-wrap">
            {!hasAny ? (
              <div className="zone-map zone-map--fallback">Qloo returned no heatmap cells for this brand.</div>
            ) : (
              <MapBoundary>
                <Suspense fallback={loading}>
                  <ZoneMap points={ev.points} juniorPoints={ev.junior_points} showSenior={showSenior} showJunior={showJunior} seniorName={senior} juniorName={juniorLabel} />
                </Suspense>
              </MapBoundary>
            )}
            {hasAny && (
              <div className="zone__controls no-print" role="group" aria-label="Map layers">
                <LayerToggle side="senior" on={showSenior} onToggle={() => setShowSenior((v) => !v)} label={senior} count={ev.points.length} />
                <LayerToggle
                  side="junior"
                  on={showJunior}
                  onToggle={() => setShowJunior((v) => !v)}
                  label={juniorLabel}
                  count={ev.junior_points.length}
                  disabled={!hasJunior}
                  title={hasJunior ? undefined : 'No heatmap for the junior side'}
                />
              </div>
            )}
          </div>
          <div className="heat-legend caption secondary" aria-hidden="true">
            <span>Lower</span>
            {showSenior && <span className="heat-legend__ramp heat-legend__ramp--senior" />}
            {showJunior && <span className="heat-legend__ramp heat-legend__ramp--junior" />}
            {!showSenior && !showJunior && <span className="heat-legend__ramp heat-legend__ramp--off" />}
            <span>Higher relative affinity</span>
          </div>
        </div>
      }
    />
  )
}
