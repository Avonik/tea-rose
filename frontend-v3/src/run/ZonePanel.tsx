import { Component, lazy, Suspense, useState, type ReactNode } from 'react'
import { wholePct } from '../lib/format'
import type { ProxyResolution, ZoneEvidence } from '../types'
import { EvidenceNotes, QuestionBlock, StandIns } from './EvidenceKit'
import ScaleGauge from './ScaleGauge'
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
function readSpread(g: number): string {
  if (g < 0.3) return 'known across most of the country'
  if (g < 0.55) return 'known widely, with a few regions clearly ahead'
  return 'known mostly in a few places'
}

/** Region share as a whole percentage; a real but tiny share reads "under 1%", never "0%". */
const shareText = (x: number) => (x > 0 && x < 0.005 ? 'under 1%' : wholePct(x))

/** Qloo labels some cells only by their centre ("37.5, -86.7"); say it as a place on the map. */
function regionName(label: unknown, i: number): string {
  const s = label == null ? '' : String(label)
  const m = s.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/)
  if (!m) return s || `Region ${i + 1}`
  const lat = Number(m[1])
  const lon = Number(m[2])
  return `Near ${Math.abs(lat).toFixed(1)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(1)}° ${lon >= 0 ? 'E' : 'W'}`
}

const of100 = (x: number | null | undefined) => (x == null ? 'not measured' : `${Math.round(Math.max(0, Math.min(1, x)) * 100)} of 100`)

/** Question 3: where is the older brand actually known? */
export default function ZonePanel({
  ev,
  senior,
  junior,
  juniorProxy,
}: {
  ev: ZoneEvidence
  senior: string
  junior: string
  juniorProxy?: ProxyResolution | null
}) {
  const [showSenior, setShowSenior] = useState(true)
  const [showJunior, setShowJunior] = useState(false)
  const hasJunior = ev.junior_points.length > 0
  const juniorLabel = juniorProxy ? `${junior} (stand-ins)` : junior
  const maxShare = Math.max(0.0001, ...ev.top_regions.map((r) => Number(r.share ?? 0)))
  const hasAny = ev.points.length > 0 || hasJunior
  const g = ev.concentration_index
  const spread = g == null ? null : Math.max(0, Math.min(1, 1 - g))
  const top = ev.top_regions[0]

  const meaning =
    g == null ? (
      <>Not measured: Qloo returned too few map cells.</>
    ) : (
      <>
        {senior} is {readSpread(g)}
        {top?.label && Number(top.share ?? 0) >= 0.01
          ? `; the strongest region, ${regionName(top.label, 0)}, holds ${wholePct(Number(top.share ?? 0))} of its liking on the map`
          : ''}
        .
      </>
    )

  const loading = (
    <div className="zone-map">
      <div className="zone-map__overlay">
        <span className="spinner" aria-hidden="true" /> Loading map
      </div>
    </div>
  )

  return (
    <QuestionBlock
      id="zone"
      n={3}
      title={<>Where is {senior} actually known?</>}
      lead={
        <>
          Where fans of {senior} are on the map. In a dispute over an unregistered name, the older user’s rights reach only as far as its reputation does (the
          zone of reputation).
        </>
      }
      standIns={hasJunior ? <StandIns proxy={juniorProxy} name={junior} /> : undefined}
      gauges={
        <>
          <ScaleGauge
            id="zone-gauge"
            title="Known where"
            value={spread}
            display={of100(spread)}
            low="one region"
            high="nationwide"
            meaning={meaning}
            tone="senior"
            subs={
              ev.geographic_overlap != null
                ? [
                    {
                      key: 'overlap',
                      label: `Same places as ${junior}`,
                      value: ev.geographic_overlap,
                      display: of100(ev.geographic_overlap),
                      tone: 'junior',
                      note: <>How closely the two maps match: 0 means no places in common, 100 means the same places.</>,
                    },
                  ]
                : undefined
            }
          />
          {ev.top_regions.length > 0 && (
            <div className="regions">
              <h4 className="group-label">Strongest regions for {senior}</h4>
              <ol className="regions__list">
                {ev.top_regions.map((r, i) => {
                  const share = Number(r.share ?? 0)
                  return (
                    <li key={String(r.label ?? i)} className="group__row regions__row">
                      <span className="regions__name">{regionName(r.label, i)}</span>
                      <span className="bar regions__bar" aria-hidden="true">
                        <span className="bar__fill bar__fill--senior" style={{ width: `${(share / maxShare) * 100}%` }} />
                      </span>
                      <span className="regions__share num caption secondary">{shareText(share)}</span>
                    </li>
                  )
                })}
              </ol>
              <p className="group__note caption">Share of all liking for {senior} on the map.</p>
            </div>
          )}
        </>
      }
      aside={
        <div className="ev__chart zone">
          <div className="zone__canvas-wrap">
            {!hasAny ? (
              <div className="zone-map zone-map--fallback">Qloo returned no map cells for this brand.</div>
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
                  title={hasJunior ? undefined : `No map for ${junior}`}
                />
              </div>
            )}
          </div>
          <div className="heat-legend caption secondary" aria-hidden="true">
            <span>Fewer fans</span>
            {showSenior && <span className="heat-legend__ramp heat-legend__ramp--senior" />}
            {showJunior && <span className="heat-legend__ramp heat-legend__ramp--junior" />}
            {!showSenior && !showJunior && <span className="heat-legend__ramp heat-legend__ramp--off" />}
            <span>More fans</span>
          </div>
          <p className="caption tertiary zone__legend-note">Relative to the rest of the map, not a head count.</p>
        </div>
      }
      detail={ev.notes.length > 0 ? <EvidenceNotes notes={ev.notes} /> : undefined}
    />
  )
}
