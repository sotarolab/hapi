import L from 'leaflet'
import { lookup, stepOf, type IvtField } from '../lib/ivt'

// How the flow looks, tuned by eye on the Chile nowcast page this is ported from: IVT is not a screen speed.
const PARTICLES = 3000
const FADE = 0.93        // how much of a trail survives each animation frame
const SPEED = 0.00008    // degrees a particle moves per frame for each kg/m/s
const MAX_AGE = 90       // animation frames before a particle starts again somewhere else
const DETAIL = 8         // pixels of the colour field per grid cell

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
/** Web Mercator's north-south coordinate of a latitude, and back: the colour field is painted in the map's
 *  own projection so it lines up when Leaflet stretches it over the box. */
const mercator = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))
const latitude = (y: number) => ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI

/** The IVT field on a Leaflet map: the size of the transport painted in the legend's colours (clear below
 *  the first step), and particles that drift along it. `setFrame` moves both to another time; `remove`
 *  takes everything off the map. The numbers and colours all come from the field site.py wrote. */
export function ivtLayer(map: L.Map, f: IvtField, pane: string) {
  let frame = f.now

  // The colour field: a small canvas, redrawn per frame and stretched over the box as an image.
  const paint = document.createElement('canvas')
  paint.width = (f.nx - 1) * DETAIL
  paint.height = (f.ny - 1) * DETAIL
  const pctx = paint.getContext('2d')!
  const colours = f.legend.map((s) => rgb(s.colour))
  const top = mercator(f.north), bottom = mercator(f.south)
  const rowLat = Array.from({ length: paint.height }, (_, r) => latitude(top + ((bottom - top) * (r + 0.5)) / paint.height))
  const image = L.imageOverlay(paint.toDataURL(), [[f.south, f.west], [f.north, f.east]], { opacity: 0.55, pane, interactive: false }).addTo(map)
  const repaint = () => {
    const img = pctx.createImageData(paint.width, paint.height)
    for (let r = 0; r < paint.height; r++) {
      for (let c = 0; c < paint.width; c++) {
        const lon = f.west + ((f.east - f.west) * (c + 0.5)) / paint.width
        const u = lookup(f, f.u[frame], lon, rowLat[r]), v = lookup(f, f.v[frame], lon, rowLat[r])
        const k = u == null || v == null ? -1 : stepOf(f.legend, Math.hypot(u, v))
        if (k >= 0) img.data.set([...colours[k], 255], (r * paint.width + c) * 4)
      }
    }
    pctx.putImageData(img, 0, 0)
    image.setUrl(paint.toDataURL())
  }

  // The particles: a canvas over the whole map, above its panes and below its controls.
  const box = map.getContainer()
  const canvas = document.createElement('canvas')
  canvas.style.cssText = 'position:absolute;top:0;left:0;z-index:450;pointer-events:none'
  box.appendChild(canvas)
  const ctx = canvas.getContext('2d')!
  const fit = () => { canvas.width = box.clientWidth; canvas.height = box.clientHeight }
  const clear = () => ctx.clearRect(0, 0, canvas.width, canvas.height)
  type Particle = { lon: number; lat: number; age: number }
  const start = (p: Particle) => {
    p.lon = f.west + Math.random() * (f.east - f.west)
    p.lat = f.south + Math.random() * (f.north - f.south)
    p.age = Math.floor(Math.random() * MAX_AGE)
  }
  const particles: Particle[] = Array.from({ length: PARTICLES }, () => { const p = { lon: 0, lat: 0, age: 0 }; start(p); return p })
  let raf = 0
  const draw = () => {
    ctx.globalCompositeOperation = 'destination-in'  // fade what is already drawn
    ctx.fillStyle = `rgba(0,0,0,${FADE})`
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.globalCompositeOperation = 'source-over'
    ctx.lineWidth = 1.1
    ctx.strokeStyle = 'rgba(255,255,255,0.6)'
    ctx.beginPath()
    for (const p of particles) {
      const u = lookup(f, f.u[frame], p.lon, p.lat), v = lookup(f, f.v[frame], p.lon, p.lat)
      if (u == null || v == null || p.age > MAX_AGE) { start(p); continue }
      const from = map.latLngToContainerPoint([p.lat, p.lon])
      p.lon += u * SPEED
      p.lat += v * SPEED
      p.age += 1
      const to = map.latLngToContainerPoint([p.lat, p.lon])
      ctx.moveTo(from.x, from.y)
      ctx.lineTo(to.x, to.y)
    }
    ctx.stroke()
    raf = requestAnimationFrame(draw)
  }
  const resize = () => { fit(); clear() }
  map.on('movestart zoomstart', clear)
  map.on('resize', resize)
  fit()
  repaint()
  raf = requestAnimationFrame(draw)

  return {
    setFrame(i: number) { frame = i; repaint() },
    remove() {
      cancelAnimationFrame(raf)
      map.off('movestart zoomstart', clear)
      map.off('resize', resize)
      canvas.remove()
      image.remove()
    },
  }
}
