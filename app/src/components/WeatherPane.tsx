import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { Weather, WeatherChart } from '../api'
import { css, rgba } from './PointChart'

/** The weather site.py wrote for the point, in two pieces: its tiles, which join the point's tile strip, and
 *  a card with one chart per entry of `charts` behind a toggle. Nothing here knows about weather: every
 *  label, unit, colour and number comes from the data. */
export function WeatherTiles({ weather }: { weather: Weather }) {
  return <>{weather.tiles.map((t) => <div key={t.label} className={`tile${t.flag ? ` flag--${t.flag}` : ''}`}><span className="eyebrow">{t.label}</span><b className="num">{t.value}</b><p className="note">{t.note}</p></div>)}</>
}

export function WeatherCard({ weather: w }: { weather: Weather }) {
  const [id, setId] = useState<string | null>(null)
  const chart = w.charts.find((c) => c.id === id) ?? w.charts[0]
  if (!chart) return null
  return (
    <section className="card">
      <div className="card-h">
        <h2>Weather</h2>
        <div className="seg">{w.charts.map((c) => <button key={c.id} className={c === chart ? 'on' : ''} onClick={() => setId(c.id)}>{c.label}</button>)}</div>
      </div>
      <WeatherPlot times={w.times} chart={chart} />
      <div className="legend">
        {chart.series.map((s) => <span key={s.label}><i style={{ background: `var(${s.colour})` }} />{s.label}</span>)}
        {chart.bars && <span><i className="band" style={{ background: `var(${chart.bars.colour})` }} />{chart.bars.label}</span>}
        {chart.line && <span><i style={{ background: 'var(--warn)' }} />{chart.line.label}</span>}
        <span><i style={{ background: 'var(--hot)' }} />now</span>
      </div>
      <p className="note">{w.note}</p>
    </section>
  )
}

/** One chart of the panel: a line per series, the optional hourly bars hanging from the top, the optional
 *  reference level and the present hour as dashed lines. Hovering reads every series at the cursor. */
function WeatherPlot({ times, chart, height = 240 }: { times: string[]; chart: WeatherChart; height?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const tip = useRef<HTMLDivElement>(null)

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
      cursor: { y: false, points: { size: 6 } },
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
        setCursor: [(u) => {
          const t = tip.current
          const i = u.cursor.idx
          if (!t) return
          if (i == null) { t.style.display = 'none'; return }
          const rows = all.map((s, k) => ({ s, v: u.data[k + 1][i] })).filter((r) => r.v != null)
          if (!rows.length) { t.style.display = 'none'; return }
          const when = new Date(u.data[0][i] * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'UTC' })
          t.innerHTML = `<b>${when} UTC</b>` + rows.map((r) => `<span><i style="background:${css(r.s.colour)}"></i>${r.s.label}<em>${fmt(r.v as number)} ${chart.unit}</em></span>`).join('')
          t.style.display = 'block'
          const x = u.cursor.left ?? 0
          t.style.left = `${x + (x > host.clientWidth / 2 ? -t.offsetWidth - 14 : 14)}px`
          t.style.top = '8px'
        }],
      },
    }, data as uPlot.AlignedData, host)
    const ro = new ResizeObserver(() => u.setSize({ width: host.clientWidth, height }))
    ro.observe(host)
    return () => { ro.disconnect(); u.destroy() }
  }, [times, chart, height])

  return <div className="chart"><div ref={el} /><div className="tip" ref={tip} /></div>
}
