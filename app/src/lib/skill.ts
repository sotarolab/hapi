/** Skill of a score against a reference: 1 is perfect, 0 matches the reference, negative is worse. */
export const skill = (crps: number, reference: number): number | null =>
  reference > 0 ? 1 - crps / reference : null

export const pct = (v: number | null, digits = 0): string => (v == null ? '–' : `${(100 * v).toFixed(digits)}%`)

/** Flow for a label: full under 10,000 cfs, compact above. */
export const fmtFlow = (v: number | null | undefined): string =>
  v == null ? '–' : v >= 10_000 ? `${(v / 1000).toFixed(v >= 100_000 ? 0 : 1)}K` : Math.round(v).toLocaleString('en-US')

/** The day's label for a date string, "Nov 18". */
export const dayLabel = (iso: string): string =>
  new Date(iso.slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })

/** Days since the record started, counted so the first day is day 1. */
export const recordDay = (start: string | null, now = new Date()): number | null => {
  if (!start) return null
  const s = Date.UTC(+start.slice(0, 4), +start.slice(4, 6) - 1, +start.slice(6, 8))
  return Math.floor((now.getTime() - s) / 86_400_000) + 1
}
