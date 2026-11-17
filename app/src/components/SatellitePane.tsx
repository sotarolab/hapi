import { useState } from 'react'
import type { Point } from '../api'
import { stamp } from './PointMap'

/** NOAA STAR's GOES-West loops and the NWS radar loops: animated GIFs their owners refresh every few
 *  minutes. Every point of the site falls in the satellite's Pacific Southwest sector. */
const BANDS = [
  { id: 'GEOCOLOR', label: 'GeoColor', note: 'true colour by day, infrared with city lights by night' },
  { id: '08', label: 'Water vapor', note: 'upper-level water vapor: the moist plume of an atmospheric river is the bright band reaching in from the Pacific' },
  { id: '13', label: 'Infrared', note: 'clean infrared, cloud top temperature: the coldest and deepest cloud is the brightest' },
  { id: 'AirMass', label: 'Air mass', note: 'the jet runs along the edge between red, dry stratospheric air and green, moist air' },
  { id: 'RADAR', label: 'Radar', note: 'where rain is falling now' },
] as const
type Band = (typeof BANDS)[number]['id']

/** The NWS radars that cover the points; the nearest one serves the loop. */
const RADARS: { id: string; name: string; lat: number; lon: number }[] = [
  { id: 'KBHX', name: 'Eureka', lat: 40.5, lon: -124.29 }, { id: 'KBBX', name: 'Beale', lat: 39.5, lon: -121.63 },
  { id: 'KDAX', name: 'Sacramento', lat: 38.5, lon: -121.68 }, { id: 'KMUX', name: 'San Francisco', lat: 37.16, lon: -121.9 },
  { id: 'KHNX', name: 'Hanford', lat: 36.31, lon: -119.63 }, { id: 'KVTX', name: 'Sulphur Mountain', lat: 34.41, lon: -119.18 },
]

export function nearestRadar(lat: number, lon: number) {
  const d = (r: { lat: number; lon: number }) => (r.lat - lat) ** 2 + ((r.lon - lon) * Math.cos((lat * Math.PI) / 180)) ** 2
  return RADARS.reduce((best, r) => (d(r) < d(best) ? r : best), RADARS[0])
}

const STAR = 'https://cdn.star.nesdis.noaa.gov/GOES18/ABI'
const RIDGE = 'https://radar.weather.gov/ridge/standard'

/** The Satellite tab: one loop at a time for the selected point, chosen from the GOES bands and the nearest
 *  radar. The app's refresh re-renders the pane, and the five-minute stamp in the URL fetches the newest loop. */
export function SkyPane({ point }: { point: Point }) {
  const [band, setBand] = useState<Band>('GEOCOLOR')
  const [wide, setWide] = useState(false)
  const radar = nearestRadar(point.lat, point.lon)
  const isRadar = band === 'RADAR'
  const src = isRadar
    ? `${RIDGE}/${wide ? 'CONUS' : radar.id}_loop.gif`
    : wide ? `${STAR}/CONUS/${band}/GOES18-CONUS-${band}-625x375.gif` : `${STAR}/SECTOR/psw/${band}/GOES18-PSW-${band}-600x600.gif`
  const info = BANDS.find((b) => b.id === band)!
  return (
    <section className="panel">
      <div className="panel-h">
        <h2>Satellite and radar, {point.name}</h2>
        <span className="row">
          <div className="seg">{BANDS.map((b) => <button key={b.id} className={b.id === band ? 'on' : ''} onClick={() => setBand(b.id)}>{b.label}</button>)}</div>
          <div className="seg">
            <button className={wide ? '' : 'on'} onClick={() => setWide(false)}>{isRadar ? `${radar.name} (${radar.id})` : 'Pacific Southwest'}</button>
            <button className={wide ? 'on' : ''} onClick={() => setWide(true)}>{isRadar ? 'CONUS' : 'West and Pacific'}</button>
          </div>
        </span>
      </div>
      <p className="note" style={{ marginTop: 0 }}>{isRadar ? 'NWS radar' : 'GOES-18'} · {info.note}. Updated every few minutes.</p>
      <div className="sat"><img src={`${src}?t=${stamp()}`} alt={`${isRadar ? `${radar.name} radar` : `GOES-18 ${info.label}`} loop`} /></div>
    </section>
  )
}
