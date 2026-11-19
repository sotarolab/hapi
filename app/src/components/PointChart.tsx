import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { Alert, PointData } from '../api'
import { readout, type ReadoutEntry } from '../lib/readout'
import { fmtFlow } from '../lib/skill'
import { wheelZoom, zoomCursor } from '../lib/zoom'

export const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
/** Models take these hues in the order they appear; HEFS is always the blue. */
export const MODEL_VARS = ['--ml', '--warn', '--danger', '--cool']
export const rgba = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}
const noon = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10), 12) / 1000
/** Where site.py's time goes on the axis: a day at its noon, an hour (a longer string) at that hour. */
const when = (s: string) => (s.length > 10 ? Date.parse(s) / 1000 : noon(s))

const HOUR = 1800, DAY = 43200  // how far, in seconds, a click may be from an hourly value and from a daily one

const hourLabel = (t: string) => new Date(t).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'UTC' })
/** The newest hourly value of the live series, with its hour. */
export function latest(live: { times: string[]; cfs: (number | null)[] }): { when: string; cfs: number } | null {
  for (let i = live.cfs.length - 1; i >= 0; i--) if (live.cfs[i] != null) return { when: `${hourLabel(live.times[i])} UTC`, cfs: live.cfs[i]! }
  return null
}
/** The time a readout prints: a chart here spans weeks, so the day comes with the hour. */
export const whenUTC = (t: number) => `${hourLabel(new Date(t * 1000).toISOString())} UTC`
/** Where a flow sits among the NWS flood categories: "above minor", "below action". */
export function category(cfs: number | null, alerts: Alert[]): string | null {
  const known = alerts.filter((a) => a.cfs != null)
  if (cfs == null || !known.length) return null
  const reached = known.filter((a) => cfs >= a.cfs!).at(-1)
  return reached ? `above ${reached.label.toLowerCase()}` : `below ${known[0].label.toLowerCase()}`
}
const alertColour = (a: Alert) => css(a.label === 'Action' || a.label === 'Minor' ? '--warn' : '--danger')

/** The point's chart in one of two views. Flow: observed daily flow with the week's hourly values, the HEFS
 *  fan (5-95 and 25-75 with its median), each model's fan the same way and the NWS official forecast as a
 *  dashed line. Stage (gauges): the NWS observed and official stage in feet with the flood categories as
 *  dashed levels, the way the NWS hydrograph shows them. The chart has its own time axis: it opens at `since`
 *  (epoch seconds; the whole record without it) and runs to the end of the forecasts. A click pins a box with
 *  the lines' values at that time; a dragged range or the wheel zooms, a double-click returns. */
export function PointChart({ point, log, view = 'flow', height = 300, since, pastLead }: { point: PointData; log: boolean; view?: 'flow' | 'stage'; height?: number; since?: number; pastLead?: number }) {
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = el.current
    if (!host) return
    const stage = view === 'stage'
    const logY = log && !stage
    const past = point.past?.fans.filter((f) => f.lead === pastLead) ?? []
    const pastLabel = point.past?.leads.find((l) => l.hours === pastLead)?.label ?? ''
    const hour = (t: string) => Date.parse(t) / 1000
    const xs = new Set<number>()
    if (!stage) {
      point.obs.forEach(([d]) => xs.add(noon(d)))
      point.hefs?.dates.forEach((d) => xs.add(noon(d)))
      Object.values(point.models).forEach((m) => m.dates.forEach((d) => xs.add(when(d))))
      past.forEach((f) => f.times.forEach((t) => xs.add(when(t))))
    }
    point.official?.times.forEach((t) => xs.add(hour(t)))
    point.live?.times.forEach((t) => xs.add(hour(t)))
    const x = [...xs].sort((a, b) => a - b)
    const at = new Map(x.map((v, i) => [v, i]))
    const col = () => new Array<number | null>(x.length).fill(null)
    const put = (arr: (number | null)[], t: number, v: number | null | undefined) => {
      const i = at.get(t)
      if (i != null && v != null) arr[i] = logY && v < 1 ? null : v
    }
    const data: (number | null)[][] = [x]
    const series: uPlot.Series[] = [{}]
    const bands: uPlot.Band[] = []
    const unit = stage ? 'ft' : 'cfs'
    const fmt = (v: number | null | undefined) => (stage ? (v == null ? '–' : v.toFixed(v < 10 ? 2 : 1)) : fmtFlow(v))
    const entries: ReadoutEntry[] = []
    const read = (series: number, label: string, colour: string, reach: number) => entries.push({ series, label, colour, reach, format: (v) => `${fmt(v)} ${unit}` })
    const line = (label: string, colour: string, values: (number | null)[], opts: Partial<uPlot.Series> = {}, reach = HOUR) => {
      data.push(values)
      series.push({ label, stroke: colour, width: 2, spanGaps: true, points: { show: false }, ...opts })
      read(data.length - 1, label, colour, reach)
    }
    const edge: uPlot.Series = { stroke: 'transparent', width: 0, spanGaps: true, points: { show: false } }
    const addFan = (label: string, colour: string, dates: string[], qs: number[][]) => {
      const arrs = qs.map(() => col())   // p05, p95, p25, p75, p50
      dates.forEach((d, k) => qs.forEach((q, j) => put(arrs[j], when(d), q[k])))
      const base = data.length
      data.push(...arrs)
      series.push({ ...edge, label: `${label} 5%` }, { ...edge, label: `${label} 95%` }, { ...edge, label: `${label} 25%` },
        { ...edge, label: `${label} 75%` }, { label: `${label} median`, stroke: colour, width: 2, spanGaps: true, points: { show: false } })
      bands.push({ series: [base + 1, base], fill: rgba(colour, 0.14) }, { series: [base + 3, base + 2], fill: rgba(colour, 0.22) })
      read(base + 4, `${label} median`, colour, dates[0]?.length > 10 ? HOUR : DAY)
    }
    const dashed: Partial<uPlot.Series> = { width: 1.5, dash: [5, 4] }
    if (stage) {
      const obs = col()
      point.live?.times.forEach((t, k) => put(obs, hour(t), point.live!.stage_ft?.[k]))
      line('Observed stage', css('--obs'), obs)
      if (point.official) {
        const off = col()
        point.official.times.forEach((t, k) => put(off, hour(t), point.official!.stage_ft[k]))
        line('NWS official', css('--official'), off, dashed)
      }
    } else {
      const obs = col()
      point.obs.forEach(([d, v]) => put(obs, noon(d), v))
      line('Observed (CDEC)', css('--obs'), obs, {}, DAY)
      if (point.live) {
        const hourly = col()
        point.live.times.forEach((t, k) => put(hourly, hour(t), point.live!.cfs[k]))
        // At a gauge the hourly series is the record, drawn as dots; at a reservoir it is a smoothed line under the daily one.
        const dots = point.kind === 'gauge' ? { points: { show: true, size: 4, stroke: css('--obs'), fill: css('--obs') } } : {}
        line('Observed, hourly', rgba(css('--obs'), 0.7), hourly, { width: 1, ...dots })
      }
      const names = Object.keys(point.models)
      past.forEach((f) => addFan(`${f.product}, ${pastLabel}`, css(f.product === 'HEFS' ? '--cool' : MODEL_VARS[Math.max(0, names.indexOf(f.product)) % MODEL_VARS.length]),
        f.times, [f.q05, f.q95, f.q25, f.q75, f.q50]))
      if (point.hefs) addFan('HEFS', css('--cool'), point.hefs.dates, [point.hefs.p05, point.hefs.p95, point.hefs.p25, point.hefs.p75, point.hefs.p50])
      Object.entries(point.models).forEach(([name, m], i) =>
        addFan(name, css(MODEL_VARS[i % MODEL_VARS.length]), m.dates, [m.q05, m.q95, m.q25, m.q75, m.q50]))
      if (point.official) {
        const off = col()
        point.official.times.forEach((t, k) => put(off, hour(t), point.official!.flow_cfs[k]))
        line('NWS official', css('--official'), off, dashed)
      }
    }
    // The flood categories are stages, so they are drawn in the stage view only.
    const levels = stage ? point.alerts ?? [] : []
    const u = new uPlot({
      width: host.clientWidth, height,
      tzDate: (t) => uPlot.tzDate(new Date(t * 1e3), 'UTC'),
      legend: { show: false },
      cursor: zoomCursor,
      plugins: [wheelZoom(), readout({ when: whenUTC, entries: () => entries, hover: false })],
      scales: {
        x: { time: true },
        // The categories stay in view even when the river is far below them.
        y: { distr: logY ? 3 : 1, log: 10, ...(levels.length ? { range: (_u: uPlot, min: number | null, max: number | null) =>
          uPlot.rangeNum(min ?? 0, Math.max(max ?? 0, ...levels.map((a) => a.ft)), 0.1, true) } : {}) },
      },
      axes: [
        { stroke: css('--dim'), grid: { stroke: css('--rule'), width: 1 }, ticks: { show: false }, font: '11px ui-monospace, Menlo, monospace' },
        { stroke: css('--dim'), grid: { stroke: css('--rule'), width: 1 }, ticks: { show: false }, size: 56, font: '11px ui-monospace, Menlo, monospace',
          values: (_u, vals) => vals.map((v) => (stage ? String(v) : fmtFlow(v))) },
      ],
      series, bands,
      hooks: {
        draw: [(u) => {
          const { left, top, width, height: h } = u.bbox
          u.ctx.save()
          u.ctx.setLineDash([4, 4])
          u.ctx.lineWidth = 1
          u.ctx.font = `${10 * devicePixelRatio}px ui-monospace, Menlo, monospace`
          u.ctx.textAlign = 'right'
          u.ctx.textBaseline = 'bottom'
          for (const a of levels) {
            const y = u.valToPos(a.ft, 'y', true)
            if (y < top || y > top + h) continue
            u.ctx.strokeStyle = u.ctx.fillStyle = alertColour(a)
            u.ctx.beginPath(); u.ctx.moveTo(left, y); u.ctx.lineTo(left + width, y); u.ctx.stroke()
            u.ctx.fillText(`${a.label} ${a.ft} ft`, left + width - 4 * devicePixelRatio, y - 2 * devicePixelRatio)
          }
          const now = Date.now() / 1000  // the present hour, as on the weather panels
          if (now >= (u.scales.x.min ?? Infinity) && now <= (u.scales.x.max ?? -Infinity)) {
            const x = u.valToPos(now, 'x', true)
            u.ctx.strokeStyle = css('--hot')
            u.ctx.beginPath(); u.ctx.moveTo(x, top); u.ctx.lineTo(x, top + h); u.ctx.stroke()
          }
          u.ctx.restore()
        }],
      },
    }, data as uPlot.AlignedData, host)
    if (since != null && x.length && since < x[x.length - 1]) u.setScale('x', { min: Math.max(x[0], since), max: x[x.length - 1] })
    const ro = new ResizeObserver(() => u.setSize({ width: host.clientWidth, height }))
    ro.observe(host)
    return () => { ro.disconnect(); u.destroy() }
  }, [point, log, view, height, since, pastLead])

  return <div className="chart" ref={el} />
}
