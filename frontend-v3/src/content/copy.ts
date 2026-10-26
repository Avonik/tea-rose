import type { Confidence, PreliminaryRead, ReadLean, ShowcaseSummary } from '../types'
import { CASE_STORIES } from './cases'
import { CASE_ORDER } from './home'

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

/** Words that open a clause and read lower-case mid-sentence; anything else (a brand, "StockX’s") keeps its case. */
const LOWER_OPENERS = /^(The|Whether|A|An|Its|How|If|Which|What|Each|Both)\b/

function lowerFirst(t: string): string {
  return LOWER_OPENERS.test(t) ? t.charAt(0).toLowerCase() + t.slice(1) : t
}

/** "The case most likely turns on X." → "x", to sit inside a sentence. */
export function turnsOnPhrase(s: string | null | undefined): string {
  const t = (s ?? '')
    .replace(/^\s*(the case )?(most likely |likely )?turns on\s+/i, '')
    .trim()
    .replace(/[.\s]+$/, '')
  return lowerFirst(t)
}

/**
 * The first clause of a phrase, at most `max` characters, without a trailing full stop: cut at the
 * first comma or semicolon, then (if still long) before the last joining word ("and", "rather than") that fits.
 */
export function shortClause(s: string, max = 90): string {
  let t = s.trim().replace(/[.\s]+$/, '')
  const stop = t.search(/[,;:]\s/)
  if (stop >= 20) t = t.slice(0, stop)
  if (t.length <= max) return t
  // Cut before a joining word that still fits; never mid-phrase. Nothing fits: keep the clause whole.
  const head = t.slice(0, max + 1)
  const cut = Math.max(...JOINS.map((j) => head.lastIndexOf(j)))
  return cut >= 20 ? t.slice(0, cut) : t
}

const JOINS = [' and ', ' or ', ' rather than ', ' together with ', ' with ', ' because ', ' while ', ' despite ', ' instead of ']

/** What the case turns on, as a short phrase for a list row. */
export const turnsOnShort = (s: string | null | undefined) => shortClause(turnsOnPhrase(s))

/**
 * The strongest defence the read named, as a short phrase: "No defence is pleaded" and the
 * "X’s strongest defence is" lead-in are dropped, citations and second sentences cut.
 */
export function defenceShort(s: string | null | undefined): string {
  let t = (s ?? '').trim().replace(/^no defen[cs]e is pleaded[^.]*\.\s*/i, '')
  const m = t.match(/strongest (?:apparent )?defen[cs]e (?:is|was)\s+(that\s+)?([\s\S]*)/i)
  if (m) t = (m[1] ? 'that ' : '') + m[2]
  t = t.split(/(?<=[a-z)”’])\.\s/)[0].split(/\s\(|:\s|;\s/)[0]
  t = t.replace(/^its\s+/i, 'the ')
  return shortClause(lowerFirst(t))
}

/** The fields of a preliminary read that the court-vs-Tea-Rose statements need. */
export type ReadFields = {
  lean: ReadLean
  confidence: Confidence
  turnsOn: string
  bestDefence: string
  oneSided: boolean
}

export function readFieldsFromSummary(s: ShowcaseSummary | undefined): ReadFields | null {
  if (!s?.read_lean) return null
  return {
    lean: s.read_lean,
    confidence: s.read_confidence ?? 'low',
    turnsOn: s.read_turns_on ?? '',
    bestDefence: s.read_best_defence ?? '',
    oneSided: !!s.read_one_sided,
  }
}

export function readFieldsFromRead(r: PreliminaryRead | null | undefined): ReadFields | null {
  if (!r) return null
  return { lean: r.lean, confidence: r.confidence, turnsOn: r.turns_on, bestDefence: r.best_defence ?? '', oneSided: !!r.one_sided_input }
}

/** "Bang (VPX)" → "Bang": the brand as a reader names it. */
export const brandName = (s: string) => s.replace(/\s*\([^)]*\)\s*$/, '').trim()

const CONFIDENCE_WORD: Record<Confidence, string> = { high: 'high', medium: 'moderate', low: 'low' }

/**
 * Tea Rose's read in one sentence: "Leans toward Bang, low confidence, because it turns on X." or
 * "Too close to call, low confidence: it turns on X." `full` keeps the whole turns-on phrase and adds
 * the strongest defence the read saw (case page); otherwise the phrase is shortened (list rows).
 */
export function teaRoseSentence(f: ReadFields, brands: [string, string], full = false): string {
  const on = full ? turnsOnPhrase(f.turnsOn) : turnsOnShort(f.turnsOn)
  const conf = `${CONFIDENCE_WORD[f.confidence] ?? f.confidence} confidence`
  const tail = f.oneSided ? ' (only the complaint was on the record)' : ''
  let s: string
  if (f.lean === 'too_close_to_call') s = `Too close to call, ${conf}${on ? `: it turns on ${on}` : ''}${tail}.`
  else {
    const toward = brandName(f.lean === 'older_brand' ? brands[0] : brands[1])
    s = `Leans toward ${toward}, ${conf}${on ? `, because it turns on ${on}` : ''}${tail}.`
  }
  const d = full ? defenceShort(f.bestDefence) : ''
  if (!d) return s
  return d.startsWith('that ') ? `${s} The strongest defence it saw is ${d}.` : `${s} The strongest defence it saw: ${d}.`
}

export type Outcome = 'older brand won' | 'newcomer won' | 'mixed' | 'settled'
export type Agreement = 'same' | 'split' | 'close' | 'other'

/** Read lean against the court's outcome. A lean against a split or settled result counts as split. */
export function agreement(lean: ReadLean, outcome: Outcome): Agreement {
  if (lean === 'too_close_to_call') return 'close'
  if (outcome === 'mixed' || outcome === 'settled') return 'split'
  const same = (lean === 'older_brand') === (outcome === 'older brand won')
  return same ? 'same' : 'other'
}

export const AGREEMENT_LABEL: Record<Agreement, string> = {
  same: 'Same way',
  split: 'Split result',
  close: 'Too close to call',
  other: 'Other way',
}

/** The clause after the agreement chip: why the read and the court line up, or where they part. */
export function agreementDetail(f: ReadFields, outcome: Outcome, brands: [string, string]): string {
  const a = agreement(f.lean, outcome)
  if (a === 'same') return `the read and the court both favour ${brandName(outcome === 'older brand won' ? brands[0] : brands[1])}`
  if (a === 'split') return outcome === 'settled' ? 'the parties settled before a verdict' : 'the court gave each side part of it'
  if (a === 'close') {
    if (outcome === 'settled') return 'the parties settled before a verdict'
    if (outcome === 'mixed') return 'the court split the result'
    const on = turnsOnShort(f.turnsOn)
    const winner = brandName(outcome === 'older brand won' ? brands[0] : brands[1])
    // Say what the read left open and who the court ruled for; never claim the court's reason.
    return on ? `the read left it open on ${on}; the court ruled for ${winner}` : `the court ruled for ${winner}`
  }
  const d = defenceShort(f.bestDefence)
  return d ? `the read had flagged ${d}` : 'the read had not seen it coming'
}

/** "Same way 1, split result 1, too close to call 5, other way 1." Split appears only when it occurs. */
export function tallyLine(list: Agreement[]): string {
  const n = (a: Agreement) => list.filter((x) => x === a).length
  const parts = [`Same way ${n('same')}`]
  if (n('split')) parts.push(`split result ${n('split')}`)
  parts.push(`too close to call ${n('close')}`, `other way ${n('other')}`)
  return `${parts.join(', ')}.`
}

/** Every showcase case's agreement, in CASE_ORDER; null until the list carries the read fields for all of them. */
export function showcaseAgreements(list: ShowcaseSummary[] | null | undefined): Agreement[] | null {
  const out: Agreement[] = []
  for (const slug of CASE_ORDER) {
    const f = readFieldsFromSummary(list?.find((c) => c.slug === slug))
    const story = CASE_STORIES[slug]
    if (!f || !story) return null
    out.push(agreement(f.lean, story.outcome))
  }
  return out
}
