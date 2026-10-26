import { motion, useReducedMotion } from 'motion/react'
import { readFromText, turnsOnPhrase } from '../content/copy'
import { factorLabel, plainProse } from '../lib/format'
import { fade, spring } from '../motion/springs'
import type { Confidence, FactorLean, Memo, PreliminaryRead as Read, ReadLean } from '../types'

/** Plain words for every factor a read can name, document-read and data-measured alike. */
export const READ_FACTOR_LABEL: Record<string, string> = {
  similarity_of_marks: 'How alike the marks are',
  intent: 'Copying on purpose',
  actual_confusion: 'Actual confusion alleged',
  buyer_care: 'How careful the buyers are',
  protectability: 'Is the mark protectable at all',
  mark_strength: 'How strong the mark is',
  defences: 'Defences raised',
  defenses: 'Defences raised',
  relatedness_of_goods: 'Related goods',
  channels_and_purchasers: 'Same channels and buyers',
  bridging_the_gap: 'Bridging the gap',
  fame: 'Fame',
  zone_of_reputation: 'Where it is known',
  other: 'Anything else that matters',
}
export const readFactorLabel = (f: string) => READ_FACTOR_LABEL[f] ?? factorLabel(f)

const CONFIDENCE_WORD: Record<Confidence, string> = { high: 'High', medium: 'Moderate', low: 'Low' }

/**
 * The computed read line without its "Preliminary read:" label, first letter capitalised, so it can
 * stand as a headline or follow a label of its own. "" when the run predates it.
 */
export function readSentence(line: string | null | undefined): string {
  const t = (line ?? '').replace(/^\s*preliminary read\s*:\s*/i, '').trim()
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : ''
}

export function leanText(lean: ReadLean, names: { senior: string; junior: string }): string {
  if (lean === 'older_brand') return `Leans toward ${names.senior}`
  if (lean === 'newcomer') return `Leans toward ${/^the newcomer$/i.test(names.junior) ? 'the newcomer' : names.junior}`
  return 'Too close to call'
}

const LEAN_DOT: Record<ReadLean, FactorLean> = { older_brand: 'favors_senior', newcomer: 'favors_junior', too_close_to_call: 'neutral' }

/** The lean chip (brand name + party dot) and the confidence chip; shared by the case page and the home frame. */
export function ReadChips({ read, names, size }: { read: Read; names: { senior: string; junior: string }; size?: 'sm' }) {
  const sm = size === 'sm' ? 'chip--sm' : ''
  return (
    <span className="chips read-chips">
      <span className={`chip lean--${LEAN_DOT[read.lean]} ${sm}`}>
        <span className="dot" aria-hidden="true" />
        {leanText(read.lean, names)}
      </span>
      <span className={`chip chip--quiet ${sm}`}>{CONFIDENCE_WORD[read.confidence] ?? read.confidence} confidence</span>
    </span>
  )
}

/** "The case most likely turns on X." reads as "X." after the label "What it turns on:". */
function turnsOn(s: string): string {
  const t = s.replace(/^\s*the case (most likely |likely )?turns on\s+/i, '').trim()
  return t.charAt(0).toUpperCase() + t.slice(1)
}

function LeanDot({ lean }: { lean: FactorLean }) {
  const word = lean === 'favors_senior' ? 'leans to the older brand' : lean === 'favors_junior' ? 'leans to the newcomer' : lean === 'neutral' ? 'neutral' : 'not enough to say'
  return (
    <span className={`read-dot lean--${lean}`} title={word}>
      <span className={`dot ${lean === 'insufficient_data' ? 'dot--hollow' : ''}`} aria-hidden="true" />
      <span className="sr-only">{word}</span>
    </span>
  )
}

const CONFUSION = ['relatedness_of_goods', 'channels_and_purchasers', 'bridging_the_gap']

/**
 * When the read is too close to call but the measured confusion factors favour one side, one sentence
 * bridges the two: "Audience overlap favours Vans; the read stays open because …". Computed from fields.
 */
export function bridgeSentence(memo: Memo, names: { senior: string; junior: string }, skip: string[] = []): string {
  const read = memo.preliminary_read
  if (!read || read.lean !== 'too_close_to_call') return ''
  const f = memo.findings.filter((x) => CONFUSION.includes(x.factor) && !skip.includes(x.factor))
  const s = f.filter((x) => x.lean === 'favors_senior').length
  const j = f.filter((x) => x.lean === 'favors_junior').length
  if (s === j) return ''
  const why = turnsOnPhrase(read.turns_on)
  return `Audience overlap favours ${s > j ? names.senior : names.junior}; the read stays open because it turns on ${why || 'what the data cannot measure'}.`
}

/**
 * "Preliminary read": how the factors are likely to weigh, from the pleadings and the audience data.
 * Never a prediction; renders nothing for runs stored before the assess step existed.
 */
export default function PreliminaryReadCard({
  memo,
  names,
  docType,
  contextFactors = [],
}: {
  memo: Memo | null
  names: { senior: string; junior: string }
  /** Extraction.document_type: "pleadings" when the defendant's answer or motion was in the input. */
  docType?: string | null
  /** Factors measured for context only (the pleading did not raise them). */
  contextFactors?: string[]
}) {
  const reduce = useReducedMotion()
  const read = memo?.preliminary_read
  if (!memo || !read) return null
  const headline = readSentence(memo.read_line) || leanText(read.lean, names)
  const paragraphs = plainProse(read.rationale)
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
  const fromDoc = read.read_factors.filter((f) => f.basis === 'document')
  const used = new Set(read.data_factors_used)
  const measured = (used.size ? memo.findings.filter((f) => used.has(f.factor)) : memo.findings).filter((f) => !contextFactors.includes(f.factor))
  const bridge = bridgeSentence(memo, names, contextFactors)
  const source = readFromText(docType, read.one_sided_input)

  return (
    <motion.section
      id="read"
      className="read"
      aria-labelledby="read-title"
      initial={{ opacity: 0, y: reduce ? 0 : 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduce ? fade : spring}
    >
      <p className="eyebrow" id="read-title">
        Preliminary read
      </p>
      <p className="read__headline serif">{headline}</p>
      <ReadChips read={read} names={names} />
      <p className="read__intro footnote secondary">
        How the factors a court weighs are likely to fall, read from the pleadings (the complaint that starts the lawsuit and, where the docket has it, the
        defendant’s answer) and the audience data. Not the court’s decision. {source}.
      </p>
      {bridge && <p className="read__turns">{bridge}</p>}

      {read.turns_on && (
        <p className="read__turns">
          <span className="read__k">What it turns on:</span> {turnsOn(read.turns_on)}
        </p>
      )}

      {read.best_defence?.trim() && (
        <p className="read__turns">
          <span className="read__k">Strongest defence:</span> {plainProse(read.best_defence.trim())}
        </p>
      )}

      {paragraphs.length > 0 && (
        <div className="read__rationale">
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}

      {read.flip_risks.length > 0 && (
        <div className="read__flips">
          <h3 className="read__h">What could flip it</h3>
          <ul className="read__flip-list">
            {read.flip_risks.map((f, i) => (
              <li key={i}>{plainProse(f)}</li>
            ))}
          </ul>
        </div>
      )}

      {(fromDoc.length > 0 || measured.length > 0) && (
        <div className="read__table">
          <div className="read__col">
            <h3 className="read__h">Read from the pleadings</h3>
            <ul className="group read__list">
              {fromDoc.map((f, i) => (
                <li key={`${f.factor}-${i}`} className="group__row group__row--top group__sep read__row">
                  <LeanDot lean={f.lean} />
                  <span className="group__main">
                    <span className="group__title">{readFactorLabel(f.factor)}</span>
                    <span className="group__sub read__finding" title={f.finding}>
                      {plainProse(f.finding)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="read__col">
            <h3 className="read__h">Measured from the data</h3>
            <ul className="group read__list">
              {measured.map((f) => (
                <li key={f.factor} className="group__row group__sep read__row">
                  <LeanDot lean={f.lean} />
                  <span className="group__main">
                    <span className="group__title">{readFactorLabel(f.factor)}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="caption tertiary read__legend">
              <span className="read__legend-item">
                <span className="dot dot--senior" aria-hidden="true" /> {names.senior}
              </span>
              <span className="read__legend-item">
                <span className="dot dot--junior" aria-hidden="true" /> {names.junior}
              </span>
              <span className="read__legend-item">
                <span className="dot" aria-hidden="true" /> Neutral
              </span>
              <span className="read__legend-item">
                <span className="dot dot--hollow" aria-hidden="true" /> Not enough to say
              </span>
            </p>
          </div>
        </div>
      )}

      {read.not_a_prediction && <p className="read__foot footnote secondary">{read.not_a_prediction}</p>}
    </motion.section>
  )
}
