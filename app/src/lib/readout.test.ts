import { describe, expect, it } from 'vitest'
import { boxMode, escapeHtml, nextPin, readoutRows, valueNear, type ReadoutEntry } from './readout'

describe('readoutRows', () => {
  const entries: ReadoutEntry[] = [{ series: 1, label: 'NWS now', colour: 'red', unit: '°' }, { series: 2, label: 'Observed', colour: 'white', decimals: 0, unit: ' mph' }, { series: 3, label: 'Hidden', colour: 'grey' }]
  it('prints the lines that are drawn and have a value', () => {
    const rows = readoutRows(entries, [72, 13.4, 5], (k) => k !== 3)
    expect(rows.map((r) => `${r.entry.label} ${r.text}`)).toEqual(['NWS now 72.0°', 'Observed 13 mph'])
    expect(readoutRows(entries, [null, null, 5], (k) => k !== 3)).toEqual([])
  })
})

describe('valueNear on a held line', () => {
  // The hour's maximum, placed at the hour's start and drawn held to the next: 10:00, 11:00.
  const hours = [36000, 37200, 38400, 39600, 40800]
  const held = [76, null, null, 78, null]
  it('reads the last point at or before, as the step is drawn, not the nearer hour ahead', () => {
    expect(valueNear(hours, held, 2, 3600, true)).toBe(76)      // 10:40: the 10:00 hour's value, though 11:00 is nearer
    expect(valueNear(hours, held, 2, 3600, false)).toBe(78)     // what a nearest reading would have said
    expect(valueNear(hours, held, 4, 3600, true)).toBe(78)      // 11:20: the hour in progress
    expect(valueNear(hours, held, 2, 1800, true)).toBeNull()    // nothing within reach back
  })
})

describe('nextPin', () => {
  it('pins the time under the cursor, moves the pin on a click elsewhere, and lets go on a click on it', () => {
    expect(nextPin(null, 200, 5000)).toBe(5000)
    expect(nextPin(120, 200, 5000)).toBe(5000)
    expect(nextPin(197, 200, 5000)).toBeNull()
  })
})

describe('escapeHtml', () => {
  it('makes a name from the feed safe in the box', () => {
    expect(escapeHtml('Burbank <b>CA</b> & "x"')).toBe('Burbank &lt;b&gt;CA&lt;/b&gt; &amp; &quot;x&quot;')
  })
})

describe('boxMode', () => {
  it('shows the pin while its mark is inside the window, whatever the pointer does', () => {
    expect(boxMode(true, true, true)).toBe('pin')
    expect(boxMode(true, false, false)).toBe('pin')
  })
  it('follows the pointer only on a chart that lets it', () => {
    expect(boxMode(false, true, true)).toBe('pointer')
    expect(boxMode(false, true, false)).toBe('none')       // click only: nothing until a click pins a time
    expect(boxMode(false, false, true)).toBe('none')
  })
})

describe('readoutRows with a format', () => {
  it("prints the value the entry's own way, in place of the decimals and the unit", () => {
    const entries: ReadoutEntry[] = [{ series: 1, label: '77–78', colour: '#0f0', format: (v) => `${Math.round(v)}¢` }, { series: 2, label: 'Obs', colour: '#fff', decimals: 1, unit: '°' }]
    expect(readoutRows(entries, [79.5, 71.26], () => true).map((r) => r.text)).toEqual(['80¢', '71.3°'])
  })
})
