// The zoom of camanchaca's charts (client/src/lib/dayWindow.ts): a dragged range zooms into it, the wheel
// zooms about the pointer, a double-click (uPlot's own) returns to the whole series.
import type uPlot from 'uplot'

/** The least a pointer must travel between press and release for the gesture to be a drag; a
 *  click with a hand's jitter stays a click. Given to uPlot as `cursor.drag.dist` and used by
 *  the readout to tell a click from the end of a drag. */
export const DRAG_PX = 5

/** The cursor every chart takes: a thin line that follows the pointer, and a dragged range zooms into it. */
export const zoomCursor = { y: false, points: { size: 6 }, drag: { x: true, y: false, dist: DRAG_PX } }

/** The x range after one wheel notch about `xVal`: the span scaled by `factor` (under one to
 *  zoom in), the pointer's position kept, never under ten minutes, never wider than the chart,
 *  and slid rather than clipped at the chart's ends so the requested span survives. */
export function zoomAbout(min: number, max: number, xVal: number, factor: number, dataMin: number, dataMax: number): [number, number] {
  const span = Math.min(dataMax - dataMin, Math.max(10 * 60, (max - min) * factor))
  const share = max > min ? (xVal - min) / (max - min) : 0.5
  let nMin = xVal - share * span
  let nMax = nMin + span
  if (nMin < dataMin) { nMin = dataMin; nMax = dataMin + span }
  if (nMax > dataMax) { nMax = dataMax; nMin = dataMax - span }
  return [nMin, nMax]
}

/** A uPlot plugin: the wheel zooms the x axis about the pointer (a notch is 20 percent), the
 *  window sliding at the chart's ends rather than shrinking; double-click (uPlot's own) resets. */
export function wheelZoom(step = 0.2): uPlot.Plugin {
  return {
    hooks: {
      ready: (u) => {
        u.over.addEventListener('wheel', (e) => {
          e.preventDefault()
          const xs = u.data[0]
          const { min, max } = u.scales.x
          if (min == null || max == null || !xs.length) return
          const xVal = u.posToVal(e.clientX - u.over.getBoundingClientRect().left, 'x')
          const [nMin, nMax] = zoomAbout(min, max, xVal, e.deltaY < 0 ? 1 - step : 1 + step, xs[0], xs[xs.length - 1])
          u.setScale('x', { min: nMin, max: nMax })
        }, { passive: false })
      },
    },
  }
}
