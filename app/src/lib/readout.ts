// The readout of camanchaca's charts (client/src/lib/readout.ts), so the two apps answer a click the same way.
// The one difference: the caller words the time (`when`), because a chart here spans weeks, not a day.
import type uPlot from 'uplot'
import { DRAG_PX } from './zoom'

/** One line of a chart's readout: which series it reads, how it is named and drawn, and how
 *  its value is printed. `held` is a step line, drawn held forward from each point: its value at
 *  an instant is the last point at or before it, not the nearest. `reach` overrides the
 *  readout's own, in seconds. `format` prints the value its own way, in place of `decimals` and
 *  `unit`, so a chart's box and its legend can write a number the same way. */
export interface ReadoutEntry { series: number; label: string; colour: string; faint?: boolean; decimals?: number; unit?: string; held?: boolean; reach?: number; format?: (v: number) => string }

/** A series' value at the point `idx` of the chart's x values: for a line, the closest point
 *  that has one within `reach` seconds either side (the earlier on a tie); for a held line, the
 *  last point at or before, within `reach` back. Null when there is none. A chart's x axis is
 *  the union of every series' times, so the point under the cursor usually belongs to one
 *  series only (a minute report between two hourly forecast values); reading that point alone
 *  shows nothing for the rest. */
export function valueNear(xs: ArrayLike<number>, col: ArrayLike<number | null | undefined>, idx: number, reach: number, held = false): number | null {
  const at = xs[idx]
  let best: number | null = null, gap = Infinity
  for (let j = idx; j >= 0 && at - xs[j] <= reach; j--) {
    const v = col[j]
    if (v != null) { best = v; gap = at - xs[j]; break }
  }
  if (held) return best
  for (let j = idx + 1; j < xs.length && xs[j] - at <= reach && xs[j] - at < gap; j++) {
    const v = col[j]
    if (v != null) { best = v; break }
  }
  return best
}

/** What a click does to the pin: a click on the pinned time (within six pixels of its mark)
 *  lets it go; a click anywhere else pins the time under the cursor. */
export function nextPin(pinPx: number | null, cursorPx: number, cursorTime: number): number | null {
  return pinPx != null && Math.abs(pinPx - cursorPx) <= 6 ? null : cursorTime
}

/** Text safe to place in the readout's markup: a station's name comes from the feed. */
export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

/** The rows a readout shows at a point: every entry whose series is drawn and has a value near
 *  it, with the value printed. */
export function readoutRows(entries: ReadoutEntry[], values: (number | null)[], shown: (series: number) => boolean): { entry: ReadoutEntry; text: string }[] {
  return entries.flatMap((entry, i) => {
    const v = values[i]
    return v == null || !shown(entry.series) ? [] : [{ entry, text: entry.format ? entry.format(v) : `${v.toFixed(entry.decimals ?? 1)}${entry.unit ?? ''}` }]
  })
}

/** Where a readout keeps its pinned time. */
export interface PinStore { at: number | null }

/** What the box shows: the pinned time while its mark is inside the window; otherwise the time
 *  under the pointer when the chart lets the box follow it (`hover`); otherwise nothing. A chart
 *  with `hover` off shows values only where the reader clicked, so the box never covers the
 *  line being followed. */
export function boxMode(pinInside: boolean, pointerInside: boolean, hover: boolean): 'pin' | 'pointer' | 'none' {
  if (pinInside) return 'pin'
  return hover && pointerInside ? 'pointer' : 'none'
}

/** A uPlot plugin: a box that follows the cursor with the time and each drawn line's nearest
 *  value, as Plotly's unified hover does. A click pins the box at that time (it stays when the
 *  pointer leaves, with a mark on the plot); a click again moves the pin, and a click on the
 *  pinned time, or a double-click, lets it go. `entries` is asked on every move, so it can
 *  follow a legend toggle. `reach` is how far, in seconds, a line's nearest value may be. `pin`
 *  is where the pinned time is kept: a chart that is rebuilt on new data hands in a store that
 *  lives as long as the component, so the pin comes back with the new plot. With `hover` false
 *  the box does not follow the pointer: it shows on a click only (the thin cursor line still
 *  follows), for a chart whose line the box would cover. */
export function readout(opts: { when: (t: number) => string; entries: () => ReadoutEntry[]; reach?: number; className?: string; pin?: PinStore; hover?: boolean }): uPlot.Plugin {
  const reach = opts.reach ?? 1800
  const hover = opts.hover ?? true
  let tip: HTMLDivElement | null = null
  let mark: HTMLDivElement | null = null
  const store = opts.pin ?? { at: null }    // the pinned instant, in the x axis's seconds; the caller's store outlives a rebuilt plot
  const indexOf = (u: uPlot, t: number) => {
    const xs = u.data[0]
    let lo = 0, hi = xs.length - 1
    while (lo < hi) { const m = (lo + hi) >> 1; if (xs[m] < t) lo = m + 1; else hi = m }
    return lo > 0 && t - xs[lo - 1] < xs[lo] - t ? lo - 1 : lo
  }
  const draw = (u: uPlot) => {
    if (!tip || !mark) return
    const xs = u.data[0]
    // A pin from another day's data is not this plot's.
    if (store.at != null && (!xs.length || store.at < xs[0] || store.at > xs[xs.length - 1])) store.at = null
    const width = u.over.clientWidth
    const pinPx = store.at != null ? u.valToPos(store.at, 'x') : null
    // The pin shows while it is inside the window; zoomed away from it, the box follows the cursor again.
    const pinned = pinPx != null && pinPx >= 0 && pinPx <= width
    mark.style.display = pinned ? 'block' : 'none'
    if (pinned) mark.style.left = `${pinPx}px`
    const live = u.cursor.idx != null && u.cursor.left != null && u.cursor.left >= 0 && u.cursor.left <= width
    if (boxMode(pinned, live, hover) === 'none') { tip.style.display = 'none'; return }
    const left = pinned ? pinPx! : u.cursor.left!
    const idx = pinned ? indexOf(u, store.at!) : u.cursor.idx!
    const entries = opts.entries()
    const values = entries.map((e) => valueNear(xs, u.data[e.series] as (number | null)[], idx, e.reach ?? reach, e.held))
    const rows = readoutRows(entries, values, (k) => u.series[k]?.show !== false)
    if (!rows.length) { tip.style.display = 'none'; return }
    const at = pinned ? store.at! : u.posToVal(left, 'x')
    tip.innerHTML = `<b>${escapeHtml(opts.when(at))}${pinned ? ' · pinned' : ''}</b>` + rows.map(({ entry, text }) =>
      `<span><i style="background:${escapeHtml(entry.colour)};opacity:${entry.faint ? 0.5 : 1}"></i>${escapeHtml(entry.label)}<em>${escapeHtml(text)}</em></span>`).join('')
    tip.style.display = 'block'
    const flip = left > width * 0.55
    tip.style.left = `${left + (flip ? -12 : 12)}px`
    tip.style.top = '6px'
    tip.style.transform = flip ? 'translateX(-100%)' : ''
  }
  return {
    hooks: {
      init: (u) => {
        tip = document.createElement('div'); tip.className = `tip readout ${opts.className ?? ''}`.trim(); u.over.appendChild(tip)
        mark = document.createElement('div'); mark.className = 'readout-pin'; u.over.appendChild(mark)
        let down: [number, number] | null = null
        u.over.addEventListener('mousedown', (e) => { down = [e.clientX, e.clientY] }, { capture: true })
        u.over.addEventListener('click', (e) => {
          if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) >= DRAG_PX) return     // the end of a drag is a zoom, not a pin
          // Where the click itself landed, not uPlot's cursor: that is updated a frame after
          // the pointer moves, so a quick second click on the mark read the place before it.
          const box = u.over.getBoundingClientRect()
          const left = e.clientX - box.left
          if (left < 0 || left > box.width) return
          const pinPx = store.at != null ? u.valToPos(store.at, 'x') : null
          store.at = nextPin(pinPx, left, u.posToVal(left, 'x'))
          draw(u)
        })
        u.over.addEventListener('dblclick', () => { store.at = null; draw(u) })
      },
      ready: (u) => draw(u),               // a pin kept from the plot this one replaces
      setCursor: (u) => draw(u),
      setScale: (u, key) => { if (key === 'x') draw(u) },
    },
  }
}
