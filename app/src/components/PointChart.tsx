import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { PointData } from '../api'
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

/** Observed daily flow, the HEFS fan (5-95 and 25-75 with its median), each model's fan the same way,
 *  and the NWS official hourly forecast as a dashed line. Hovering reads the lines at the cursor. */
export function PointChart({ point, log, height = 360 }: { point: PointData; log: boolean; height?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const tip = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = el.current
    if (!host) return
    const xs = new Set<number>()
    point.obs.forEach(([d]) => xs.add(noon(d)))
    point.hefs?.dates.forEach((d) => xs.add(noon(d)))
    Object.values(point.models).forEach((m) => m.dates.forEach((d) => xs.add(noon(d))))
    point.official?.times.forEach((t) => xs.add(Date.parse(t) / 1000))
    const x = [...xs].sort((a, b) => a - b)
    const at = new Map(x.map((v, i) => [v, i]))
    const col = () => new Array<number | null>(x.length).fill(null)
    const put = (arr: (number | null)[], t: number, v: number | null | undefined) => {
      const i = at.get(t)
      if (i != null && v != null) arr[i] = log && v < 1 ? null : v
    }
    const obs = col()
    point.obs.forEach(([d, v]) => put(obs, noon(d), v))
    const data: (number | null)[][] = [x, obs]
    const series: uPlot.Series[] = [{}, { label: 'Observed', stroke: css('--obs'), width: 2, spanGaps: true, points: { show: false } }]
    const bands: uPlot.Band[] = []
    const entries: Entry[] = [{ idx: 1, label: 'Observed (CDEC)', colour: css('--obs') }]
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
    if (point.hefs) addFan('HEFS', css('--cool'), point.hefs.dates, [point.hefs.p05, point.hefs.p95, point.hefs.p25, point.hefs.p75, point.hefs.p50])
    Object.entries(point.models).forEach(([name, m], i) =>
      addFan(name, css(MODEL_VARS[i % MODEL_VARS.length]), m.dates, [m.q05, m.q95, m.q25, m.q75, m.q50]))
    if (point.official) {
      const off = col()
      point.official.times.forEach((t, k) => put(off, Date.parse(t) / 1000, point.official!.flow_cfs[k]))
      data.push(off)
      series.push({ label: 'NWS official', stroke: css('--official'), width: 1.5, dash: [5, 4], spanGaps: true, points: { show: false } })
      entries.push({ idx: data.length - 1, label: 'NWS official', colour: css('--official') })
    }
    const u = new uPlot({
      width: host.clientWidth, height,
      tzDate: (t) => uPlot.tzDate(new Date(t * 1e3), 'UTC'),
      legend: { show: false },
      cursor: { y: false, points: { size: 6 } },
      scales: { x: { time: true }, y: { distr: log ? 3 : 1, log: 10 } },
      axes: [
        { stroke: css('--dim'), grid: { stroke: css('--rule'), width: 1 }, ticks: { show: false }, font: '11px ui-monospace, Menlo, monospace' },
        { stroke: css('--dim'), grid: { stroke: css('--rule'), width: 1 }, ticks: { show: false }, size: 56, font: '11px ui-monospace, Menlo, monospace',
          values: (_u, vals) => vals.map((v) => fmtFlow(v)) },
      ],
      series, bands,
      hooks: {
        setCursor: [(u) => {
          const t = tip.current
          const i = u.cursor.idx
          if (!t) return
          if (i == null) { t.style.display = 'none'; return }
          const rows = entries.map((e) => ({ e, v: u.data[e.idx][i] })).filter((r) => r.v != null)
          if (!rows.length) { t.style.display = 'none'; return }
          const when = new Date(u.data[0][i] * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'UTC' })
          t.innerHTML = `<b>${when} UTC</b>` + rows.map((r) => `<span><i style="background:${r.e.colour}"></i>${r.e.label}<em>${fmtFlow(r.v)} cfs</em></span>`).join('')
          t.style.display = 'block'
          const left = u.cursor.left ?? 0
          t.style.left = `${left + (left > host.clientWidth / 2 ? -t.offsetWidth - 14 : 14)}px`
          t.style.top = '8px'
        }],
      },
    }, data as uPlot.AlignedData, host)
    // Open on the last 30 observed days and the whole forecast; the full record stays reachable by zooming out.
    const first = point.hefs?.dates[0] ?? Object.values(point.models)[0]?.dates[0]
    if (first && x.length) u.setScale('x', { min: Math.max(x[0], noon(first) - 30 * 86400), max: x[x.length - 1] })
    const ro = new ResizeObserver(() => u.setSize({ width: host.clientWidth, height }))
    ro.observe(host)
    return () => { ro.disconnect(); u.destroy() }
  }, [point, log, height])

  return <div className="chart"><div ref={el} /><div className="tip" ref={tip} /></div>
}
