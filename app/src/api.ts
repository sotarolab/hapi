/** The site data: built by site.py every archive run and committed to the data branch. */
export const DATA_BASE: string =
  import.meta.env.VITE_DATA_BASE ?? 'https://raw.githubusercontent.com/sotarolab/hapi/data/data/site'

export interface Point {
  lid: string
  kind: 'reservoir' | 'gauge'
  name: string
  lat: number
  lon: number
  cdec?: string | null
  usgs?: string
  scored: boolean
  note?: string | null
}
export interface Fan { issued: string; dates: string[]; p05: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] }
/** `dates` holds days for a daily product and hours (ISO, UTC) for an hourly one; `first` is what site.py calls the first value. */
export interface ModelFan { issued: string; dates: string[]; first?: string; q05: number[]; q25: number[]; q50: number[]; q75: number[]; q95: number[] }
/** The week's hourly observed flow live.py fetched; stage only at the gauges. */
export interface Live { source: string; times: string[]; cfs: (number | null)[]; stage_ft: (number | null)[] | null }
/** An NWS flood category of a gauge; cfs is null where the rating curve does not reach the stage. */
export interface Alert { label: string; ft: number; cfs: number | null }
export interface Official { issued: string | null; times: string[]; stage_ft: (number | null)[]; flow_cfs: (number | null)[] }
/** The weather panel as site.py wrote it, ready to draw: every label, unit and colour (a CSS token name) is data. */
export interface WeatherTile { label: string; value: string; note: string; flag: 'warn' | 'danger' | null }
export interface WeatherSeries { label: string; colour: string; values: (number | null)[] }
export interface WeatherChart {
  id: string
  label: string
  unit: string
  digits: number
  series: WeatherSeries[]
  /** Hourly amounts drawn as bars hanging from the top, on their own scale. */
  bars?: WeatherSeries
  /** A reference level drawn across the chart. */
  line?: { value: number; label: string }
}
export interface Weather { issued: string; times: string[]; tiles: WeatherTile[]; charts: WeatherChart[]; note: string }
/** What one product said about the hours already past, at one lead: at each hour, the newest forecast made at
 *  least `lead` hours before it (site.py, past_forecasts). */
export interface PastFan { product: string; lead: number; times: string[]; q05: number[]; q25: number[]; q50: number[]; q75: number[]; q95: number[] }
export interface Past { leads: { hours: number; label: string }[]; fans: PastFan[] }
export interface PointData extends Point {
  obs: [string, number][]
  hefs: Fan | null
  models: Record<string, ModelFan>
  official: Official | null
  /** Absent in files built before weather.py existed, null when nothing is archived for the point. */
  weather?: Weather | null
  live?: Live | null
  alerts?: Alert[]
  /** Gauges only; absent in files built before site.py wrote it. */
  past?: Past | null
}
export interface Cell {
  product: string
  lead?: number
  lid?: string
  n: number
  crps: number
  crps_persistence: number
  crps_climatology: number
  cov90: number
  thin: boolean
}
export interface Index {
  built: string
  record_start: string | null
  archive_days: number
  leads: number[]
  min_pairs: number
  points: Point[]
  scores: { by_lead: Cell[]; by_point: Cell[] }
}

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const r = await fetch(`${DATA_BASE}/${path}`, { signal, cache: 'no-cache' })
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return (await r.json()) as T
}
import type { IvtField } from './lib/ivt'

export const api = {
  /** The IVT field for the map; absent until ivt_field.py has saved a forecast cycle. */
  ivt: (signal: AbortSignal) => getJson<IvtField>('ivt.json', signal),
  index: (signal: AbortSignal) => getJson<Index>('index.json', signal),
  point: (lid: string, signal: AbortSignal) => getJson<PointData>(`points/${lid}.json`, signal),
}
