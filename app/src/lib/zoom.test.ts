import { describe, expect, it } from 'vitest'
import { zoomAbout } from './zoom'

describe('zoomAbout', () => {
  const [dataMin, dataMax] = [0, 10000]
  it('scales the span about the pointer and keeps its position', () => {
    const [a, b] = zoomAbout(2000, 4000, 3000, 0.5, dataMin, dataMax)
    expect([a, b]).toEqual([2500, 3500])
    const [c, d] = zoomAbout(2000, 4000, 2000, 2, dataMin, dataMax)
    expect([c, d]).toEqual([2000, 6000])
  })
  it('slides at the ends rather than shrinking, and never passes the chart or ten minutes', () => {
    expect(zoomAbout(8000, 10000, 9900, 2, dataMin, dataMax)).toEqual([6000, 10000])
    expect(zoomAbout(0, 2000, 100, 2, dataMin, dataMax)).toEqual([0, 4000])
    expect(zoomAbout(0, 10000, 5000, 2, dataMin, dataMax)).toEqual([0, 10000])
    expect(zoomAbout(3000, 3300, 3150, 0.5, dataMin, dataMax)).toEqual([2850, 3450])
  })
})

