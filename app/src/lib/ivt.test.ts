import { describe, expect, it } from 'vitest'
import { lookup, stepOf } from './ivt'

// two rows, three columns: 40 N then 39 N, from 125 W to 123 W
const grid = { north: 40, south: 39, west: -125, east: -123, nx: 3, ny: 2 }
const values = [0, 10, 20, 100, 110, 120]

describe('the IVT field', () => {
  it('reads the grid at a point', () => {
    expect(lookup(grid, values, -125, 40)).toBe(0)
    expect(lookup(grid, values, -123, 39)).toBe(120)
    expect(lookup(grid, values, -124.5, 39.5)).toBe(55) // the mean of 0, 10, 100 and 110
    expect(lookup(grid, values, -122.9, 39.5)).toBeNull()
    expect(lookup(grid, values, -124, 40.1)).toBeNull()
  })
  it('finds the legend step of a value', () => {
    const legend = [250, 500, 750].map((from) => ({ from, colour: '#000', label: `${from}` }))
    expect(stepOf(legend, 249)).toBe(-1)
    expect(stepOf(legend, 250)).toBe(0)
    expect(stepOf(legend, 600)).toBe(1)
    expect(stepOf(legend, 2000)).toBe(2)
  })
})
