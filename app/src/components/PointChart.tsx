import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { Alert, PointData } from '../api'
import { fmtFlow } from '../lib/skill'

export const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
/** Models take these hues in the order they appear; HEFS is always the blue. */
export const MODEL_VARS = ['--ml', '--warn', '--danger', '--cool']
export const rgba = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}
const noon = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10), 12) / 1000

interface Entry { idx: number; label: string; colour: string }

const hourLabel = (t: string) => new Date(t).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'UTC' })
/** The newest hourly value of the live series, with its hour. */
export function latest(live: { times: string[]; cfs: (number | null)[] }): { when: string; cfs: number } | null {
  for (let i = live.cfs.length - 1; i >= 0; i--) if (live.cfs[i] != null) return { when: `${hourLabel(live.times[i])} UTC`, cfs: live.cfs[i]! }
  return null
}
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
 *  dashed levels, the way the NWS hydrograph shows them. Hovering reads the lines at the cursor. */
export interface Shared {
  /** The time window every panel of the stack shows, in epoch seconds. */
  xMin: number
  xMax: number
  /** Panels with the same key move their cursors together. */
  syncKey: string
  /** Whether this panel draws the time labels; only the bottom one of a stack does. */
  axis: boolean
}
/** What a panel of the stack adds to a uPlot: no drag zoom (it would break the alignment), a synced cursor,
 *  and time labels only where asked. */
export const sharedCursor = (s?: Shared) => ({ y: false, points: { size: 6 }, drag: { x: false, y: false }, ...(s ? { sync: { key: s.syncKey } } : {}) })
export const timeAxis = (base: uPlot.Axis, s?: Shared): uPlot.Axis => (s && !s.axis ? { ...base, size: 6, values: (_u, vals) => vals.map(() => '') } : base)

export function PointChart({ point, log, view = 'flow', height = 300, shared }: { point: PointData; log: boolean; view?: 'flow' | 'stage'; height?: number; shared?: Shared }) {
  const el = useRef<HTMLDivElement>(null)
  const tip = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = el.current
    if (!host) return
    const stage = view === 'stage'
    const logY = log && !stage
    const hour = (t: string) => Date.parse(t) / 1000
    const xs = new Set<number>()
    if (!stage) {
      point.obs.forEach(([d]) => xs.add(noon(d)))
      point.hefs?.dates.forEach((d) => xs.add(noon(d)))
      Object.values(point.models).forEach((m) => m.dates.forEach((d) => xs.add(noon(d))))
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
    const entries: Entry[] = []
    const line = (label: string, colour: string, values: (number | null)[], opts: Partial<uPlot.Series> = {}) => {
      data.push(values)
      series.push({ label, stroke: colour, width: 2, spanGaps: true, points: { show: false }, ...opts })
      entries.push({ idx: data.length - 1, label, colour })
    }
    const edge: uPlot.Series = { stroke: 'transparent', width: 0, spanGaps: true, points: { show: false } }
    const addFan = (label: string, colour: string, dates: string[], qs: number[][]) => {
      const arrs = qs.map(() => col())   // p05, p95, p25, p75, p50
      dates.forEach((d, k) => qs.forEach((q, j) => put(arrs[j], noon(d), q[k])))
      const base = data.length
      data.push(...arrs)
      series.push({ ...edge, label: `${label} 5%` }, { ...edge, label: `${label} 95%` }, { ...edge, label: `${label} 25%` },
        { ...edge, label: `${label} 75%` }, { label: `${label} median`, stroke: colour, width: 2, spanGaps: true, points: { show: false } })
      bands.push({ series: [base + 1, base], fill: rgba(colour, 0.14) }, { series: [base + 3, base + 2], fill: rgba(colour, 0.22) })
      entries.push({ idx: base + 4, label: `${label} median`, colour })
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
      line('Observed (CDEC)', css('--obs'), obs)
      if (point.live) {
        const hourly = col()
        point.live.times.forEach((t, k) => put(hourly, hour(t), point.live!.cfs[k]))
        line('Observed, hourly', rgba(css('--obs'), 0.7), hourly, { width: 1 })  // thinner and dimmer: the daily record leads
      }
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
    const unit = stage ? 'ft' : 'cfs'
    const fmt = (v: number | null | undefined) => (stage ? (v == null ? '–' : v.toFixed(v < 10 ? 2 : 1)) : fmtFlow(v))
    const u = new uPlot({
      width: host.clientWidth, height,
      tzDate: (t) => uPlot.tzDate(new Date(t * 1e3), 'UTC'),
      legend: { show: false },
      cursor: sharedCursor(shared),
      scales: {
        x: { time: true },
        // The categories stay in view even when the river is far below them.
        y: { distr: logY ? 3 : 1, log: 10, ...(levels.length ? { range: (_u: uPlot, min: number | null, max: number | null) =>
          uPlot.rangeNum(min ?? 0, Math.max(max ?? 0, ...levels.map((a) => a.ft)), 0.1, true) } : {}) },
      },
      axes: [
        timeAxis({ stroke: css('--dim'), grid: { stroke: css('--rule'), width: 1 }, ticks: { show: false }, font: '11px ui-monospace, Menlo, monospace' }, shared),
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
          const now = Date.now() / 1000  // the present hour, as on the weather panels of the stack
          if (shared && now >= (u.scales.x.min ?? Infinity) && now <= (u.scales.x.max ?? -Infinity)) {
            const x = u.valToPos(now, 'x', true)
            u.ctx.strokeStyle = css('--hot')
            u.ctx.beginPath(); u.ctx.moveTo(x, top); u.ctx.lineTo(x, top + h); u.ctx.stroke()
          }
          u.ctx.restore()
        }],
        setCursor: [(u) => {
          const t = tip.current
          const i = u.cursor.idx
          if (!t) return
          if (i == null) { t.style.display = 'none'; return }
          const rows = entries.map((e) => ({ e, v: u.data[e.idx][i] })).filter((r) => r.v != null)
          if (!rows.length) { t.style.display = 'none'; return }
          const when = new Date(u.data[0][i] * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'UTC' })
          t.innerHTML = `<b>${when} UTC</b>` + rows.map((r) => `<span><i style="background:${r.e.colour}"></i>${r.e.label}<em>${fmt(r.v)} ${unit}</em></span>`).join('')
          t.style.display = 'block'
          const left = u.cursor.left ?? 0
          t.style.left = `${left + (left > host.clientWidth / 2 ? -t.offsetWidth - 14 : 14)}px`
          t.style.top = '8px'
        }],
      },
    }, data as uPlot.AlignedData, host)
    // In a stack every panel shows the same window; alone, flow opens on the last 30 observed days and the forecast.
    const first = point.hefs?.dates[0] ?? Object.values(point.models)[0]?.dates[0]
    if (shared) u.setScale('x', { min: shared.xMin, max: shared.xMax })
    else if (!stage && first && x.length) u.setScale('x', { min: Math.max(x[0], noon(first) - 30 * 86400), max: x[x.length - 1] })
    const ro = new ResizeObserver(() => u.setSize({ width: host.clientWidth, height }))
    ro.observe(host)
    return () => { ro.disconnect(); u.destroy() }
  }, [point, log, view, height, shared?.xMin, shared?.xMax, shared?.syncKey, shared?.axis])

  return <div className="chart"><div ref={el} /><div className="tip" ref={tip} /></div>
}
