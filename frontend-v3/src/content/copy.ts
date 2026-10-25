/**
 * Small number-to-words helpers for the home page. Numbers are shown as ordinals or whole numbers
 * out of 100, never as raw floats.
 */

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v))

/** 0–1 score to a whole number 0–100. */
export const to100 = (v: number) => Math.round(clamp01(v) * 100)

/** 52 → "52nd", 11 → "11th", 1 → "1st". */
export function ordinalSuffix(n: number): string {
  const r = Math.round(n)
  const m100 = r % 100
  if (m100 >= 11 && m100 <= 13) return `${r}th`
  switch (r % 10) {
    case 1:
      return `${r}st`
    case 2:
      return `${r}nd`
    case 3:
      return `${r}rd`
    default:
      return `${r}th`
  }
}

/** One short sentence for the shared-fans percentile (0–1). */
export function readOverlap(p: number): string {
  if (p >= 0.9) return 'Each brand ranks in the top tenth among the other’s fans: largely the same crowd.'
  if (p >= 0.75) return 'Each brand ranks high among the other’s fans: a shared crowd.'
  if (p > 0.35) return 'Near the middle of comparable brands: no signal either way.'
  return 'Each brand ranks low among the other’s fans: mostly separate crowds.'
}

/** One short sentence for fame breadth (0–1). */
export function readFame(v: number): string {
  if (v >= 0.75) return 'Liked about evenly across ages and genders: known by everyone.'
  if (v >= 0.5) return 'Liked across most groups, with a visible skew.'
  return 'Liked mainly by one group: known by its own crowd.'
}

/** One short sentence for the nationwide score (1 − concentration). */
export function readNationwide(n: number): string {
  if (n >= 0.7) return 'Liked across most of the country, not one region.'
  if (n >= 0.45) return 'Known widely, but some regions clearly lead.'
  return 'Concentrated: a few places hold most of the affinity.'
}

/** "24 Qloo queries, 57 seconds" from the appendix length and the trace timestamps, when both are sane. */
export function runFacts(queries: number, firstTs?: string, lastTs?: string): string | null {
  const parts: string[] = []
  if (queries > 0) parts.push(`${queries} Qloo ${queries === 1 ? 'query' : 'queries'}`)
  if (firstTs && lastTs) {
    const s = Math.round((Date.parse(lastTs) - Date.parse(firstTs)) / 1000)
    if (Number.isFinite(s) && s > 0 && s < 3600) parts.push(s < 90 ? `${s} seconds` : `${Math.round(s / 60)} minutes`)
  }
  return parts.length ? parts.join(', ') : null
}
