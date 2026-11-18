import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api, type Point } from '../api'
import type { IvtField } from '../lib/ivt'
import { ivtLayer } from './IvtLayer'

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

type Overlay = L.TileLayer | L.TileLayer.WMS

/** California itself, not the point set: the points cluster north and the state's shape reads better. */
const CALIFORNIA: L.LatLngBoundsLiteral = [[32.5, -124.5], [42.1, -114.1]]
const IVT_FRAME_MS = 700  // how long the time bar holds each frame when it plays

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

/** The radar loop: IEM keeps the national mosaic of each of the last 55 minutes in five-minute steps. */
const RADAR_FRAMES = [50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 0]
const radarFrame = (minutesAgo: number) =>
  L.tileLayer(`https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913${minutesAgo ? `-m${String(minutesAgo).padStart(2, '0')}m` : ''}/{z}/{x}/{y}.png?t={t}`, {
    opacity: 0, attribution: 'IEM NEXRAD', maxNativeZoom: 12, pane: 'wx', t: stamp(),
  } as L.TileLayerOptions)

/** A button on the map that plays the last 50 minutes of radar in a loop and stops it. Every frame is on
 *  the map at once, hidden, so the loop only changes opacity; the newest frame is held a little longer. */
function radarControl(): L.Control {
  const Control = L.Control.extend({
    onAdd(map: L.Map) {
      const button = L.DomUtil.create('button', 'radar-play')
      let frames: L.TileLayer[] = []
      let timer: number | undefined
      const stop = () => {
        window.clearTimeout(timer)
        frames.forEach((f) => f.remove())
        frames = []
        button.textContent = '▶ Radar loop'
      }
      const show = (i: number) => {
        frames.forEach((f, k) => f.setOpacity(k === i ? 0.7 : 0))
        const ago = RADAR_FRAMES[i]
        button.textContent = `■ Radar ${ago ? `−${ago} min` : 'now'}`
        timer = window.setTimeout(() => show((i + 1) % frames.length), ago ? 450 : 1600)
      }
      button.textContent = '▶ Radar loop'
      L.DomEvent.disableClickPropagation(button)
      L.DomEvent.on(button, 'click', () => {
        if (frames.length) return stop()
        frames = RADAR_FRAMES.map((m) => radarFrame(m).addTo(map))
        show(0)
      })
      map.on('unload', stop)
      return button
    },
  })
  return new Control({ position: 'bottomleft' })
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
 *  overlays can be switched on from the top right corner and advance with the app's refresh (`tick`); the
 *  button at the bottom left plays the last 50 minutes of radar. The IVT button lays the field site.py wrote
 *  over the northeast Pacific as moving particles, with a time bar, and widens the map to the page while on.
 *  The map takes the size of its container. */
export function PointMap({ points, selected, onSelect, tick = 0 }: { points: Point[]; selected: string | null; onSelect: (lid: string) => void; tick?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const markers = useRef<Map<string, L.CircleMarker>>(new Map())
  const overlays = useRef<Record<string, Overlay> | null>(null)
  const select = useRef(onSelect)
  select.current = onSelect
  const [ivtOn, setIvtOn] = useState(false)
  const [ivt, setIvt] = useState<IvtField | null>(null)
  const [ivtMissing, setIvtMissing] = useState(false)
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(false)
  const layer = useRef<ReturnType<typeof ivtLayer> | null>(null)

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false, zoomSnap: 0.25 })
    // OpenStreetMap's own tiles, darkened by CSS (.map .leaflet-tile-pane): the dark basemaps now need keys.
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 12 }).addTo(m)
    m.createPane('wx').style.zIndex = '350'  // above the basemap tiles (200), below the markers (400)
    overlays.current = weatherOverlays()
    L.control.layers(undefined, overlays.current, { collapsed: true, position: 'topright' }).addTo(m)
    radarControl().addTo(m)
    map.current = m
    const ro = new ResizeObserver(() => m.invalidateSize())  // the rail sets the height, and it changes with the window
    ro.observe(el.current)
    return () => { ro.disconnect(); m.remove(); map.current = null; overlays.current = null }
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
    if (bounds.length && !layer.current) m.fitBounds(CALIFORNIA, { padding: [8, 8] })
  }, [points])

  // The IVT field is fetched the first time the layer is switched on, and again with the app's refresh.
  useEffect(() => {
    if (!ivtOn) return
    const stop = new AbortController()
    api.ivt(stop.signal)
      .then((f) => { setIvt((old) => { if (old?.issued !== f.issued) setFrame(f.now); return f }); setIvtMissing(false) })
      .catch((e) => { if (e.name !== 'AbortError') setIvtMissing(true) })
    return () => stop.abort()
  }, [ivtOn, tick])

  // On: the map widens to the page, moves to the field's box and gets the layer. Off: back to California.
  useEffect(() => {
    const m = map.current
    if (!m || !ivtOn || !ivt) return
    const shell = el.current?.closest('.shell')
    shell?.classList.add('wide')
    m.invalidateSize()
    m.fitBounds([[ivt.south, ivt.west], [ivt.north, ivt.east]])
    layer.current = ivtLayer(m, ivt, 'wx')
    return () => {
      layer.current?.remove()
      layer.current = null
      setPlaying(false)
      shell?.classList.remove('wide')
      m.invalidateSize()
      m.fitBounds(CALIFORNIA, { padding: [8, 8] })
    }
  }, [ivtOn, ivt])

  useEffect(() => { layer.current?.setFrame(frame) }, [frame, ivt, ivtOn])

  useEffect(() => {
    if (!playing || !ivt) return
    const timer = window.setInterval(() => setFrame((i) => (i + 1) % ivt.times.length), IVT_FRAME_MS)
    return () => window.clearInterval(timer)
  }, [playing, ivt])

  useEffect(() => {
    markers.current.forEach((mk, lid) => {
      const on = lid === selected
      mk.setStyle({ color: on ? css('--obs') : (mk.options.fillColor as string), weight: on ? 2.5 : 1.5, radius: on ? 8 : 6 })
      if (on) mk.bringToFront()
    })
  }, [selected, points])

  const shown = ivtOn && ivt
  return (
    <div className="mapbox">
      <div className="map" ref={el} />
      <button className="radar-play ivt-toggle" onClick={() => setIvtOn((on) => !on)}>{ivtOn ? '■ IVT' : '▶ IVT'}</button>
      {ivtOn && ivtMissing && !ivt && <div className="ivtbar"><span className="ivt-label">No IVT field has been saved yet.</span></div>}
      {shown && (
        <div className="ivtbar">
          <button className="radar-play" onClick={() => setPlaying((p) => !p)}>{playing ? '■' : '▶'}</button>
          <div className="ivt-slider">
            <input type="range" min={0} max={ivt.times.length - 1} value={frame} onChange={(e) => { setPlaying(false); setFrame(+e.target.value) }} />
            <i className="ivt-now" style={{ left: `${(ivt.now / (ivt.times.length - 1)) * 100}%` }} />
          </div>
          <span className="ivt-label">{ivt.labels[frame]}{frame === ivt.now ? ' · now' : frame < ivt.now ? ' · past' : ' · forecast'}</span>
          <span className="ivt-legend">
            {ivt.legend.map((s) => <span key={s.from}><i style={{ background: s.colour }} />{s.label}</span>)}
            <span>{ivt.unit}</span>
          </span>
          <span className="ivt-note">{ivt.issued} · {ivt.floor}</span>
        </div>
      )}
    </div>
  )
}
