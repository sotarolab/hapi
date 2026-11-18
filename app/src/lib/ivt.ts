/** The IVT field as site.py writes it (site/ivt.json): one frame of eastward (u) and northward (v) transport
 *  per time, each a flat list of ny rows from north to south, nx values from west to east. */
export interface IvtStep { from: number; colour: string; label: string }
export interface IvtField {
  issued: string; source: string; unit: string; floor: string
  north: number; south: number; west: number; east: number; nx: number; ny: number
  times: string[]; labels: string[]; now: number
  u: number[][]; v: number[][]
  legend: IvtStep[]
}
type Grid = Pick<IvtField, 'north' | 'south' | 'west' | 'east' | 'nx' | 'ny'>

/** The value of a frame at a point, blended from the four grid values around it; null outside the box. */
export function lookup(g: Grid, values: number[], lon: number, lat: number): number | null {
  if (lon < g.west || lon > g.east || lat > g.north || lat < g.south) return null
  const x = (lon - g.west) / (g.east - g.west) * (g.nx - 1)
  const y = (g.north - lat) / (g.north - g.south) * (g.ny - 1)
  const i = Math.min(g.nx - 2, Math.floor(x)), j = Math.min(g.ny - 2, Math.floor(y))
  const fx = x - i, fy = y - j, at = (r: number, c: number) => values[r * g.nx + c]
  const top = at(j, i) + fx * (at(j, i + 1) - at(j, i))
  const bottom = at(j + 1, i) + fx * (at(j + 1, i + 1) - at(j + 1, i))
  return top + fy * (bottom - top)
}

/** The index of the legend step a value falls in, or -1 below the first step. */
export function stepOf(legend: IvtStep[], value: number): number {
  let k = -1
  while (k + 1 < legend.length && value >= legend[k + 1].from) k++
  return k
}
