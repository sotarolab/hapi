import { describe, expect, it } from 'vitest'
import { dayLabel, fmtFlow, pct, recordDay, skill } from './skill'

describe('skill helpers', () => {
  it('scores against a reference and survives a zero reference', () => {
    expect(skill(50, 100)).toBe(0.5)
    expect(skill(150, 100)).toBe(-0.5)
    expect(skill(10, 0)).toBeNull()
    expect(pct(0.1234, 1)).toBe('12.3%')
    expect(pct(null)).toBe('–')
  })
  it('formats flow and dates', () => {
    expect(fmtFlow(4185.9)).toBe('4,186')
    expect(fmtFlow(69060)).toBe('69.1K')
    expect(fmtFlow(104228)).toBe('104K')
    expect(dayLabel('2026-11-18')).toBe('Nov 18')
    expect(recordDay('20261115', new Date('2026-11-15T20:00:00Z'))).toBe(1)
    expect(recordDay('20261115', new Date('2026-12-01T01:00:00Z'))).toBe(17)
  })
})
