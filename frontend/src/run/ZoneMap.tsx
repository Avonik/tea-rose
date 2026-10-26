import type { FeatureCollection, Point } from 'geojson'
import { AttributionControl, Map as MlMap, NavigationControl, Popup, setWorkerUrl, type GeoJSONSource, type LngLatBoundsLike, type MapLayerMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState } from 'react'
import type { HeatmapPoint } from '../types'

// MapLibre v6 resolves its worker relative to its own module; point it at the emitted asset.
setWorkerUrl(workerUrl)

const STYLE = 'https://tiles.openfreemap.org/styles/positron'

type Ramp = [string, string, string, string]
// Sequential single-hue ramps from the --senior indigo / --junior orange hues, transparent at zero (GL styles need literals).
const SENIOR: Ramp = ['rgba(94,92,230,0)', 'rgba(94,92,230,0.38)', 'rgba(72,70,204,0.72)', 'rgba(46,44,150,0.92)']
const JUNIOR: Ramp = ['rgba(255,159,10,0)', 'rgba(255,159,10,0.4)', 'rgba(232,124,0,0.74)', 'rgba(168,82,0,0.9)']

function toGeoJSON(points: HeatmapPoint[]): FeatureCollection<Point> {
  const max = Math.max(0.0001, ...points.map((p) => p.affinity ?? 0))
  return {
    type: 'FeatureCollection',
    features: points
      .filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude))
      .map((p) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [p.longitude, p.latitude] },
        properties: { w: (p.affinity ?? 0) / max, affinity: p.affinity ?? null, label: p.label ?? null },
      })),
  }
}

/** Contiguous United States: the view when there is nothing to fit, and the box most points fall in. */
const US: [[number, number], [number, number]] = [
  [-125, 24],
  [-66, 50],
]

const inUS = (p: HeatmapPoint) =>
  p.longitude >= US[0][0] && p.longitude <= US[1][0] && p.latitude >= US[0][1] && p.latitude <= US[1][1]

/** The q-quantile of a sorted list. */
function quantile(sorted: number[], q: number) {
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))
  return sorted[i]
}

/**
 * The bounds to fit for a set of heatmap cells. Qloo returns a few cells in Alaska, Hawaii, Guam or
 * abroad; fitting all of them spans half the globe and centres the map on the Atlantic. So: keep the
 * contiguous-US cells when they are the clear majority, trim the outer half percent on each axis, and fall
 * back to the US view when there is nothing to fit.
 */
function heatBounds(all: HeatmapPoint[]): LngLatBoundsLike {
  const valid = all.filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude))
  if (!valid.length) return US
  const us = valid.filter(inUS)
  const pts = us.length >= valid.length * 0.6 ? us : valid
  const lons = pts.map((p) => p.longitude).sort((a, b) => a - b)
  const lats = pts.map((p) => p.latitude).sort((a, b) => a - b)
  const trim = pts.length >= 50 ? 0.005 : 0
  let [w, e] = [quantile(lons, trim), quantile(lons, 1 - trim)]
  let [south, north] = [quantile(lats, trim), quantile(lats, 1 - trim)]
  // A single city still gets a readable regional view.
  if (e - w < 4) [w, e] = [(w + e) / 2 - 2, (w + e) / 2 + 2]
  if (north - south < 3) [south, north] = [(south + north) / 2 - 1.5, (south + north) / 2 + 1.5]
  return [
    [w, south],
    [e, north],
  ]
}

/** Breathing room around the data; extra at the top, where the layer toggles float over the map. */
function fitPadding(map: MlMap) {
  const c = map.getContainer()
  const p = Math.round(Math.max(20, Math.min(48, Math.min(c.clientWidth, c.clientHeight) * 0.07)))
  // On narrow maps the toggles wrap to two rows and the attribution spans two lines.
  const narrow = c.clientWidth < 480
  return { top: p + (narrow ? 76 : 40), bottom: p + (narrow ? 40 : 0), left: p, right: p }
}

function addSide(map: MlMap, id: 'senior' | 'junior', points: HeatmapPoint[], ramp: Ramp, visible: boolean) {
  map.addSource(id, { type: 'geojson', data: toGeoJSON(points) })
  map.addLayer({
    id: `${id}-heat`,
    type: 'heatmap',
    source: id,
    maxzoom: 9,
    layout: { visibility: visible ? 'visible' : 'none' },
    paint: {
      'heatmap-weight': ['interpolate', ['linear'], ['get', 'w'], 0, 0, 1, 1],
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 2, 1.4, 7, 2.6],
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 2, 22, 4, 34, 8, 72],
      'heatmap-opacity': 0.85,
      'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, ramp[0], 0.25, ramp[1], 0.6, ramp[2], 1, ramp[3]],
    },
  })
  map.addLayer({
    id: `${id}-points`,
    type: 'circle',
    source: id,
    layout: { visibility: visible ? 'visible' : 'none' },
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 2.5, 6, 6],
      'circle-color': ramp[2],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
      'circle-opacity': ['interpolate', ['linear'], ['zoom'], 2, 0.55, 5, 1],
    },
  })
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

export default function ZoneMap({
  points,
  juniorPoints,
  showSenior,
  showJunior,
  seniorName,
  juniorName,
}: {
  points: HeatmapPoint[]
  juniorPoints: HeatmapPoint[]
  showSenior: boolean
  showJunior: boolean
  seniorName: string
  juniorName: string
}) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const userMoved = useRef(false)
  const fitted = useRef<{ points: HeatmapPoint[]; juniorPoints: HeatmapPoint[] } | null>(null)
  const vis = useRef({ showSenior, showJunior })
  vis.current = { showSenior, showJunior }

  useEffect(() => {
    if (!el.current) return
    let map: MlMap
    try {
      map = new MlMap({
        container: el.current,
        style: STYLE,
        bounds: US,
        fitBoundsOptions: { padding: 24 },
        // 1, not 2: on a phone-width map the whole US only fits below zoom 2.
        minZoom: 1,
        maxZoom: 10,
        attributionControl: false,
        cooperativeGestures: true,
        dragRotate: false,
        pitchWithRotate: false,
        canvasContextAttributes: { preserveDrawingBuffer: true },
      })
    } catch {
      setFailed('This browser cannot draw the map (WebGL is unavailable). The regions are listed alongside.')
      return
    }
    mapRef.current = map
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new AttributionControl({ compact: true }), 'bottom-right')
    map.touchZoomRotate.disableRotation()

    map.on('load', () => {
      addSide(map, 'junior', juniorPoints, JUNIOR, vis.current.showJunior)
      addSide(map, 'senior', points, SENIOR, vis.current.showSenior)
      map.fitBounds(heatBounds([...points, ...juniorPoints]), { padding: fitPadding(map), maxZoom: 5, duration: 0 })
      fitted.current = { points, juniorPoints }
      const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10, className: 'map-pop' })
      for (const side of ['senior', 'junior'] as const) {
        const layer = `${side}-points`
        map.on('mouseenter', layer, (e: MapLayerMouseEvent) => {
          map.getCanvas().style.cursor = 'default'
          const f = e.features?.[0]
          if (!f) return
          const { label, w } = f.properties as { label?: string; w?: number }
          const who = side === 'senior' ? seniorName : juniorName
          popup
            .setLngLat((f.geometry as Point).coordinates as [number, number])
            .setHTML(`<strong>${escapeHtml(label ?? 'Cell')}</strong><br><span>${escapeHtml(who)} · ${w == null ? "–" : `${Math.round(Number(w) * 100)}% of its strongest spot`}</span>`)
            .addTo(map)
        })
        map.on('mouseleave', layer, () => {
          map.getCanvas().style.cursor = ''
          popup.remove()
        })
      }
      // Re-fit when the container changes size (layout settling, rotation), until the reader moves the map.
      map.on('movestart', (e) => {
        if ((e as { originalEvent?: unknown }).originalEvent) userMoved.current = true
      })
      const ro = new ResizeObserver(() => {
        if (userMoved.current || !fitted.current) return
        map.resize()
        map.fitBounds(heatBounds([...fitted.current.points, ...fitted.current.juniorPoints]), { padding: fitPadding(map), maxZoom: 5, duration: 0 })
      })
      ro.observe(map.getContainer())
      map.once('remove', () => ro.disconnect())
      setReady(true)
    })
    map.on('error', (e) => {
      // Tile/style failures: keep the overlay text honest but do not crash.
      if (!map.isStyleLoaded()) setFailed(`The basemap could not be loaded${e.error?.message ? ` (${e.error.message})` : ''}. The regions are listed alongside.`)
    })
    return () => {
      map.remove()
      mapRef.current = null
    }
    // The map is created once; new data is pushed in by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // New heatmap data: swap the sources and re-fit to the new bounds.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const last = fitted.current
    if (last && last.points === points && last.juniorPoints === juniorPoints) return
    ;(map.getSource('senior') as GeoJSONSource | undefined)?.setData(toGeoJSON(points))
    ;(map.getSource('junior') as GeoJSONSource | undefined)?.setData(toGeoJSON(juniorPoints))
    map.fitBounds(heatBounds([...points, ...juniorPoints]), { padding: fitPadding(map), maxZoom: 5, duration: 0 })
    fitted.current = { points, juniorPoints }
    userMoved.current = false
  }, [points, juniorPoints, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const set = (id: string, on: boolean) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none')
    set('senior-heat', showSenior)
    set('senior-points', showSenior)
    set('junior-heat', showJunior)
    set('junior-points', showJunior)
  }, [showSenior, showJunior, ready])

  return (
    <div className="zone-map">
      <div ref={el} className="zone-map__canvas" role="region" aria-label="Heatmap of where the mark has affinity in the United States. Use the region list for a text version." />
      {!ready && !failed && (
        <div className="zone-map__overlay">
          <span className="spinner" aria-hidden="true" /> Loading map
        </div>
      )}
      {failed && <div className="zone-map__overlay zone-map__overlay--error">{failed}</div>}
    </div>
  )
}
