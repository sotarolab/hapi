import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Point } from '../api'

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/** Every point on one map: reservoirs in blue, flood gauges in orange, the selected one ringed in white.
 *  A click selects; the view is fitted once to the whole set and then left alone. */
export function PointMap({ points, selected, onSelect, height = 460 }: { points: Point[]; selected: string | null; onSelect: (lid: string) => void; height?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const markers = useRef<Map<string, L.CircleMarker>>(new Map())
  const select = useRef(onSelect)
  select.current = onSelect

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false })
    // OpenStreetMap's own tiles, darkened by CSS (.map .leaflet-tile-pane): the dark basemaps now need keys.
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 12 }).addTo(m)
    map.current = m
    return () => { m.remove(); map.current = null }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m) return
    markers.current.forEach((mk) => mk.remove())
    markers.current.clear()
    const bounds: L.LatLngTuple[] = []
    for (const p of points) {
      const colour = css(p.kind === 'reservoir' ? '--cool' : '--hot')
      const mk = L.circleMarker([p.lat, p.lon], { radius: 6, color: colour, weight: 1.5, fillColor: colour, fillOpacity: p.scored ? 0.85 : 0.35 })
        .bindTooltip(`${p.name} · ${p.lid}`, { direction: 'top', offset: [0, -6] })
        .on('click', () => select.current(p.lid))
        .addTo(m)
      markers.current.set(p.lid, mk)
      bounds.push([p.lat, p.lon])
    }
    if (bounds.length) m.fitBounds(bounds, { padding: [24, 24] })
  }, [points])

  useEffect(() => {
    markers.current.forEach((mk, lid) => {
      const on = lid === selected
      mk.setStyle({ color: on ? css('--obs') : (mk.options.fillColor as string), weight: on ? 2.5 : 1.5, radius: on ? 8 : 6 })
      if (on) mk.bringToFront()
    })
  }, [selected, points])

  return <div className="map" ref={el} style={{ height }} />
}
