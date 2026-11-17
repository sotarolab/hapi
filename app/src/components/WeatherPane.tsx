import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { Weather, WeatherChart } from '../api'
import { readout } from '../lib/readout'
import { wheelZoom, zoomCursor } from '../lib/zoom'
import { css, rgba, whenUTC } from './PointChart'

/** The weather site.py wrote for the point, in two pieces: its tiles, which join the point's tile strip, and
 *  one plot per entry of `charts`, each a panel of the forecast stack. Nothing here knows about weather:
 *  every label, unit, colour and number comes from the data. */
export function WeatherTiles({ weather }: { weather: Weather }) {
  return <>{weather.tiles.map((t) => <div key={t.label} className={`tile${t.flag ? ` flag--${t.flag}` : ''}`}><span className="eyebrow">{t.label}</span><b className="num">{t.value}</b><p className="note">{t.note}</p></div>)}</>
}

/** The legend of one weather chart, as the data names it. */
export function WeatherLegend({ chart }: { chart: WeatherChart }) {
  return (
    <div className="legend">
      {chart.series.map((s) => <span key={s.label}><i style={{ background: `var(${s.colour})` }} />{s.label}</span>)}
      {chart.bars && <span><i className="band" style={{ background: `var(${chart.bars.colour})` }} />{chart.bars.label}</span>}
      {chart.line && <span><i style={{ background: 'var(--warn)' }} />{chart.line.label}</span>}
    </div>
  )
}

/** One chart of the panel: a line per series, the optional hourly bars hanging from the top, the optional
 *  reference level and the present hour as dashed lines, on its own time axis over every hour it has. A click
 *  pins a box with every series' value at that time; a dragged range or the wheel zooms, a double-click returns. */
export function WeatherPlot({ times, chart, height = 230 }: { times: string[]; chart: WeatherChart; height?: number }) {
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = el.current
    if (!host) return
    const fmt = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: chart.digits, maximumFractionDigits: chart.digits })
    const all = chart.bars ? [...chart.series, chart.bars] : chart.series
    const data = [times.map((t) => Date.parse(`${t}Z`) / 1000), ...all.map((s) => s.values)]
    const series: uPlot.Series[] = [{}, ...chart.series.map((s) => ({ label: s.label, stroke: css(s.colour), width: 2, spanGaps: true, points: { show: false } }))]
    // An hour's amount belongs to the hour that ends at its time, so each bar sits left of its x.
    if (chart.bars) series.push({ label: chart.bars.label, scale: 'bars', width: 0, fill: rgba(css(chart.bars.colour), 0.4), points: { show: false },
      paths: uPlot.paths.bars!({ size: [1], gap: 1, align: -1 }) })
    const entries = all.map((s, k) => ({ series: k + 1, label: s.label, colour: css(s.colour), format: (v: number) => `${fmt(v)} ${chart.unit}` }))
    const mark = chart.line?.value
    const axis = { stroke: css('--dim'), grid: { stroke: css('--rule'), width: 1 }, ticks: { show: false }, font: '11px ui-monospace, Menlo, monospace' }
    const dashed = (u: uPlot, colour: string, x0: number, y0: number, x1: number, y1: number) => {
      u.ctx.strokeStyle = colour
      u.ctx.beginPath(); u.ctx.moveTo(x0, y0); u.ctx.lineTo(x1, y1); u.ctx.stroke()
    }
    const u = new uPlot({
      width: host.clientWidth, height,
      tzDate: (t) => uPlot.tzDate(new Date(t * 1e3), 'UTC'),
      legend: { show: false },
      cursor: zoomCursor,
      plugins: [wheelZoom(), readout({ when: whenUTC, entries: () => entries, hover: false })],
      scales: {
        x: { time: true },
        // The reference level stays in view even when every value is far below it.
        ...(mark != null ? { y: { range: (_u: uPlot, min: number | null, max: number | null) => uPlot.rangeNum(Math.min(min ?? mark, mark), Math.max(max ?? mark, mark), 0.1, true) } } : {}),
        // The bars run downward from the top and take the upper third, clear of the lines.
        ...(chart.bars ? { bars: { dir: -1 as const, range: (_u: uPlot, _min: number | null, max: number | null) => [0, max ? max * 3 : 1] as [number, number] } } : {}),
      },
      axes: [axis, { ...axis, size: 56, values: (_u, vals) => vals.map(fmt) }],
      series,
      hooks: {
        draw: [(u) => {
          const { left, top, width, height: h } = u.bbox
          u.ctx.save()
          u.ctx.setLineDash([4, 4])
          u.ctx.lineWidth = 1
          const now = Date.now() / 1000
          if (now >= (u.scales.x.min ?? Infinity) && now <= (u.scales.x.max ?? -Infinity)) {
            const x = u.valToPos(now, 'x', true)
            dashed(u, css('--hot'), x, top, x, top + h)
          }
          if (mark != null) {
            const y = u.valToPos(mark, 'y', true)
            dashed(u, css('--warn'), left, y, left + width, y)
          }
          u.ctx.restore()
        }],
      },
    }, data as uPlot.AlignedData, host)
    const ro = new ResizeObserver(() => u.setSize({ width: host.clientWidth, height }))
    ro.observe(host)
    return () => { ro.disconnect(); u.destroy() }
  }, [times, chart, height])

  return <div className="chart" ref={el} />
}
