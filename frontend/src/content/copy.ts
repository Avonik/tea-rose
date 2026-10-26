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

// ------------------------------------------------------------------ verdict chips

export type ChipSide = 'senior' | 'junior' | null

/** The two sides as one-word chip names: from the case's short title ("Bang v. Monster"), else the brand names. */
function chipNames(story: { short: string; brands: [string, string] }): [string, string] {
  const parts = story.short.split(' v. ')
  return parts.length === 2 ? [parts[0].trim(), parts[1].trim()] : [brandName(story.brands[0]), brandName(story.brands[1])]
}

/** The court's result in one word: the winning side's short name, "Mixed" or "Settled". */
export function courtChip(story: { short: string; brands: [string, string]; outcome: Outcome }): { label: string; side: ChipSide } {
  const [older, newcomer] = chipNames(story)
  const outcome = story.outcome
  if (outcome === 'older brand won') return { label: older, side: 'senior' }
  if (outcome === 'newcomer won') return { label: newcomer, side: 'junior' }
  return { label: outcome === 'mixed' ? 'Mixed' : 'Settled', side: null }
}

/** Tea Rose's read in one word: the brand it leans toward, or "Too close". */
export function readChip(lean: ReadLean, story: { short: string; brands: [string, string] }): { label: string; side: ChipSide } {
  const [older, newcomer] = chipNames(story)
  if (lean === 'older_brand') return { label: older, side: 'senior' }
  if (lean === 'newcomer') return { label: newcomer, side: 'junior' }
  return { label: 'Too close', side: null }
}

// ------------------------------------------------------------------ the results, in words

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty']

/** 4 → "four", 0 → "no", above twenty as digits. */
export const numberWord = (n: number) => WORDS[n] ?? String(n)
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** "a, b and c". */
function joinAnd(parts: string[]): string {
  return parts.length <= 1 ? parts.join('') : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
}

export const RESULTS_CAVEAT =
  'The court’s decision was withheld from the agent, but the model may still know how famous cases ended, so this is a demonstration, not a test.'

/**
 * The showcase results as two or three short paragraphs, computed from the showcase list (read fields) and the
 * hand-written outcomes: how the cases were read, the tally, the pattern, confidence. Null until every case in
 * CASE_ORDER has a read; the caller then shows the caveat alone.
 */
export function resultsParagraphs(list: ShowcaseSummary[] | null | undefined): string[] | null {
  const rows: { f: ReadFields; story: (typeof CASE_STORIES)[string]; a: Agreement }[] = []
  for (const slug of CASE_ORDER) {
    const f = readFieldsFromSummary(list?.find((c) => c.slug === slug))
    const story = CASE_STORIES[slug]
    if (!f || !story) return null
    rows.push({ f, story, a: agreement(f.lean, story.outcome) })
  }
  const total = rows.length
  const count = (p: (r: (typeof rows)[number]) => boolean) => rows.filter(p).length
  const answered = count((r) => !r.f.oneSided)
  const oneSided = total - answered

  // 1. What was read.
  const p1 =
    `Tea Rose read ${numberWord(total)} decided or settled trademark cases from the filed pleadings, with the court’s decision withheld, ` +
    `and each read was then set beside the outcome. ` +
    (answered && oneSided
      ? `For ${numberWord(answered)} of them the record included the defendant’s answer or motion; for the other ${numberWord(oneSided)}, only the complaint.`
      : answered
        ? 'Every record included the defendant’s answer or motion.'
        : 'Every record held the complaint alone.')

  // 2. The tally and the pattern.
  const n = (a: Agreement) => count((r) => r.a === a)
  const tally = [`went the same way as the court in ${numberWord(n('same'))}`]
  if (n('split')) tally.push(`met a split or settled result in ${numberWord(n('split'))}`)
  tally.push(`called ${numberWord(n('close'))} too close to call`, `went the other way in ${numberWord(n('other'))}`)
  const s: string[] = [`The read ${joinAnd(tally)}.`]

  const leans = rows.filter((r) => r.f.lean !== 'too_close_to_call')
  const leansOneSided = leans.filter((r) => r.f.oneSided).length
  const answeredClose = count((r) => !r.f.oneSided && r.f.lean === 'too_close_to_call')
  if (leans.length && leansOneSided === leans.length && answered && answeredClose === answered) {
    s.push(
      `It committed to a side only when the record held the plaintiff’s side alone: all ${numberWord(leans.length)} of its leans came from complaint-only records, ` +
        `and in all ${numberWord(answered)} cases with the defendant’s answer in, it called the case too close.`,
    )
  } else if (leans.length) {
    s.push(`${cap(numberWord(leansOneSided))} of its ${numberWord(leans.length)} leans came from complaint-only records.`)
  }

  const towardNewcomer = count((r) => r.f.lean === 'newcomer')
  const newcomerWins = rows.filter((r) => r.story.outcome === 'newcomer won')
  const closeOnNewcomer = newcomerWins.filter((r) => r.a === 'close').length
  if (newcomerWins.length) {
    const lead = towardNewcomer === 0 ? 'It never leaned toward the newcomer; ' : ''
    s.push(`${lead}${lead ? 'in' : 'In'} ${numberWord(closeOnNewcomer)} of the ${numberWord(newcomerWins.length)} cases the newcomer won, it said too close to call.`)
  }

  const other = rows.filter((r) => r.a === 'other')
  if (other.length) {
    const names = other.length <= 2 ? `, ${joinAnd(other.map((r) => r.story.short))},` : ''
    const allOneSided = other.every((r) => r.f.oneSided)
    const named = other.filter((r) => r.story.readNamedWinningDefence).length
    const subject = other.length === 1 ? `The one case it got the other way${names} was` : `The ${numberWord(other.length)} cases it got the other way${names} were`
    const from = allOneSided ? ' read from the complaint alone' : ''
    const defence =
      named === 0 ? '' : other.length === 1 ? 'the read had named the defence that later won' : named === other.length ? `in ${other.length === 2 ? 'both' : 'all of them'} the read had named the defence that later won` : `in ${numberWord(named)} the read had named the defence that later won`
    if (from || defence) s.push(`${subject}${from}${from && defence ? ', and ' : ''}${defence}.`)
  }
  const p2 = s.join(' ')

  // 3. Confidence, then the caveat.
  const low = count((r) => r.f.confidence === 'low')
  const moderate = count((r) => r.f.confidence === 'medium')
  const high = count((r) => r.f.confidence === 'high')
  const levels = [
    low && `low in ${numberWord(low)} reads`,
    moderate && `moderate in ${numberWord(moderate)}`,
    high && `high in ${numberWord(high)}`,
  ].filter(Boolean) as string[]
  const p3 = `Confidence was ${joinAnd(levels)}${high ? '' : '; none was high'}. ${RESULTS_CAVEAT}`
  return [p1, p2, p3]
}
