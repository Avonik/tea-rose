import type { FeatureCollection, Point } from 'geojson'
import { AttributionControl, LngLatBounds, Map as MlMap, NavigationControl, Popup, setWorkerUrl, type MapLayerMouseEvent } from 'maplibre-gl'
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
  const vis = useRef({ showSenior, showJunior })
  vis.current = { showSenior, showJunior }

  useEffect(() => {
    if (!el.current) return
    let map: MlMap
    try {
      map = new MlMap({
        container: el.current,
        style: STYLE,
        center: [-96.5, 38.6],
        zoom: 3,
        minZoom: 2,
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
      const all = [...points, ...juniorPoints]
      if (all.length) {
        const b = new LngLatBounds()
        all.forEach((p) => b.extend([p.longitude, p.latitude]))
        map.fitBounds(b, { padding: 36, maxZoom: 5, duration: 0 })
      }
      const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10, className: 'map-pop' })
      for (const side of ['senior', 'junior'] as const) {
        const layer = `${side}-points`
        map.on('mouseenter', layer, (e: MapLayerMouseEvent) => {
          map.getCanvas().style.cursor = 'default'
          const f = e.features?.[0]
          if (!f) return
          const { label, affinity } = f.properties as { label?: string; affinity?: number }
          const who = side === 'senior' ? seniorName : juniorName
          popup
            .setLngLat((f.geometry as Point).coordinates as [number, number])
            .setHTML(`<strong>${escapeHtml(label ?? 'Cell')}</strong><br><span>${escapeHtml(who)} · affinity ${affinity == null ? '–' : Number(affinity).toFixed(2)}</span>`)
            .addTo(map)
        })
        map.on('mouseleave', layer, () => {
          map.getCanvas().style.cursor = ''
          popup.remove()
        })
      }
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
    // Points are fixed for a mounted map; the panel remounts the map if the evidence object changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
