import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Point } from '../api'

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

type Overlay = L.TileLayer | L.TileLayer.WMS

/** Radar and GOES imagery are published every five minutes, so a five-minute stamp in the URL is what makes
 *  a redraw fetch the new frame, and lets the cache serve the old one in between. */
export const stamp = () => Math.floor(Date.now() / 300_000)

/** The weather overlays, off by default: radar from IEM's cached NEXRAD tiles, satellite from its GOES
 *  composites over WMS. They sit in their own pane so the filter that darkens the basemap leaves them alone. */
function weatherOverlays(): Record<string, Overlay> {
  const iem = 'https://mesonet.agron.iastate.edu'
  const radar = L.tileLayer(`${iem}/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png?t={t}`, {
    opacity: 0.6, attribution: 'IEM NEXRAD', maxNativeZoom: 12, pane: 'wx', t: stamp(),
  } as L.TileLayerOptions)
  const goes = (service: string, layers: string) =>
    L.tileLayer.wms(`${iem}/cgi-bin/wms/goes/${service}.cgi`, {
      layers, format: 'image/png', transparent: true, uppercase: true, opacity: 0.55, attribution: 'IEM GOES', pane: 'wx', t: stamp(),
    } as L.WMSOptions)
  return { 'Radar': radar, 'Satellite visible': goes('conus_vis', 'conus_vis_1km'), 'Satellite infrared': goes('conus_ir', 'conus_ir_4km') }
}

/** Move an overlay on to the current five-minute frame; a WMS layer redraws itself when its params change,
 *  a tile layer needs the option bumped and a redraw. */
function refresh(layer: Overlay) {
  const t = stamp()
  if (layer instanceof L.TileLayer.WMS) layer.setParams({ t } as unknown as L.WMSParams)
  else { (layer.options as { t?: number }).t = t; layer.redraw() }
}

/** Every point on one map: reservoirs in blue, flood gauges in orange, the selected one ringed in white.
 *  A click selects; the view is fitted once to the whole set and then left alone. Radar and satellite
 *  overlays can be switched on from the top right corner and advance with the app's refresh (`tick`). */
export function PointMap({ points, selected, onSelect, tick = 0, height = 460 }: { points: Point[]; selected: string | null; onSelect: (lid: string) => void; tick?: number; height?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const markers = useRef<Map<string, L.CircleMarker>>(new Map())
  const overlays = useRef<Record<string, Overlay> | null>(null)
  const select = useRef(onSelect)
  select.current = onSelect

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false })
    // OpenStreetMap's own tiles, darkened by CSS (.map .leaflet-tile-pane): the dark basemaps now need keys.
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 12 }).addTo(m)
    m.createPane('wx').style.zIndex = '350'  // above the basemap tiles (200), below the markers (400)
    overlays.current = weatherOverlays()
    L.control.layers(undefined, overlays.current, { collapsed: false, position: 'topright' }).addTo(m)
    map.current = m
    return () => { m.remove(); map.current = null; overlays.current = null }
  }, [])

  useEffect(() => { Object.values(overlays.current ?? {}).forEach(refresh) }, [tick])

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
