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

/** "15 Qloo queries, 2 minutes" from the appendix length and the trace timestamps, when both are sane. */
export function runFacts(queries: number, firstTs?: string, lastTs?: string): string | null {
  const parts: string[] = []
  if (queries > 0) parts.push(`${queries} Qloo ${queries === 1 ? 'query' : 'queries'}`)
  if (firstTs && lastTs) {
    const s = Math.round((Date.parse(lastTs) - Date.parse(firstTs)) / 1000)
    if (Number.isFinite(s) && s > 0 && s < 3600) {
      const m = Math.max(1, Math.round(s / 60))
      parts.push(s < 60 ? `${s} seconds` : `${m} ${m === 1 ? 'minute' : 'minutes'}`)
    }
  }
  return parts.length ? parts.join(', ') : null
}

const READ_FROM: Record<string, string> = {
  pleadings: 'Read from the complaint and the answer',
  complaint: 'Read from the complaint; the defendant’s side is not in the record',
  cease_and_desist: 'Read from the letter',
  opinion: 'Read from the court’s opinion',
  petition: 'Read from the petition',
}

/**
 * Which documents the agent read, from the extracted document type (code sets "pleadings" when the
 * defendant's answer or motion is in the input). No trailing full stop.
 */
export function readFromText(docType: string | null | undefined, oneSided?: boolean): string {
  // Runs stored before code detected bundled pleadings: the read itself records whether the defendant's side was in.
  if (docType === 'complaint' && oneSided === false) return READ_FROM.pleadings
  return (docType && READ_FROM[docType]) || 'Read from the filing'
}

/** "The case most likely turns on X." → "x", to sit inside a sentence. */
export function turnsOnPhrase(s: string | null | undefined): string {
  const t = (s ?? '')
    .replace(/^\s*(the case )?(most likely |likely )?turns on\s+/i, '')
    .trim()
    .replace(/[.\s]+$/, '')
  return t ? t.charAt(0).toLowerCase() + t.slice(1) : ''
}

/**
 * One framing sentence for the reveal, computed from the read's lean and the court's outcome.
 * `lean`: older_brand | newcomer | too_close_to_call. `outcome`: the hand-written CaseStory outcome.
 */
export function courtFraming(
  lean: string,
  outcome: 'older brand won' | 'newcomer won' | 'mixed' | 'settled',
  turnsOn: string,
  names: { senior: string; junior: string },
): string {
  const on = turnsOnPhrase(turnsOn)
  const flagged = on ? `; the read had flagged the open question: ${on}` : ''
  if (lean === 'too_close_to_call') {
    if (outcome === 'settled') return 'The read called it too close; the parties settled before a verdict.'
    if (outcome === 'mixed') return 'The read called it too close, and the court split the result.'
    return `The read called it too close; the court decided it on ${on || 'the facts the read left open'}.`
  }
  const toward = lean === 'older_brand' ? names.senior : names.junior
  if (outcome === 'settled') return `The read leaned toward ${toward}; the parties settled before a verdict.`
  if (outcome === 'mixed') return `The read leaned toward ${toward}; the court split the result${on ? `. The read had flagged the open question: ${on}` : ''}.`
  const same = (lean === 'older_brand' && outcome === 'older brand won') || (lean === 'newcomer' && outcome === 'newcomer won')
  return same ? 'The read and the court point the same way.' : `The court went the other way${flagged}.`
}
