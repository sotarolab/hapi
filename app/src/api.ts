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
  flood_stages_ft?: [number, number, number] | null
  note?: string | null
}
export interface Fan { issued: string; dates: string[]; p05: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] }
export interface ModelFan { issued: string; dates: string[]; q05: number[]; q25: number[]; q50: number[]; q75: number[]; q95: number[] }
export interface Official { issued: string | null; times: string[]; stage_ft: (number | null)[]; flow_cfs: (number | null)[] }
export interface PointData extends Point {
  obs: [string, number][]
  hefs: Fan | null
  models: Record<string, ModelFan>
  official: Official | null
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
export const api = {
  index: (signal: AbortSignal) => getJson<Index>('index.json', signal),
  point: (lid: string, signal: AbortSignal) => getJson<PointData>(`points/${lid}.json`, signal),
}
