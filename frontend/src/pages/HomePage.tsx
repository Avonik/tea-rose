import { AnimatePresence, motion, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useId, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { IconChevron, IconCode, IconMap, IconPulse, IconUsers } from '../components/icons'
import { Disclosure, LeanChip, Skeleton, VerdictChips } from '../components/ui'
import { CASE_STORIES, type CaseStory } from '../content/cases'
import {
  AGREEMENT_LABEL,
  agreement,
  agreementDetail,
  clamp01,
  courtChip,
  ordinalSuffix,
  readFame,
  readFieldsFromSummary,
  readFromText,
  readChip,
  readNationwide,
  readOverlap,
  RESULTS_CAVEAT,
  resultsParagraphs,
  runFacts,
  teaRoseSentence,
  to100,
} from '../content/copy'
import {
  ANALYZE,
  CASE_ORDER,
  FEATURED,
  FIGHTS,
  HOW,
  PREVIEW,
  QUESTION_COLUMNS,
  QUESTIONS,
  QUESTIONS_HEAD,
  READ_BAND,
  SCORECARD,
  WILL_NOT,
  type QuestionKey,
  type StepWho,
} from '../content/home'
import { factorLabel, plainHeadline, sideNames } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { AnimatedNumber } from '../motion/AnimatedNumber'
import { PinnedHero } from '../motion/PinnedHero'
import { ReadChips, readSentence } from '../run/PreliminaryRead'
import { Page, Reveal } from '../motion/Reveal'
import { fade, springQuick, springSlow } from '../motion/springs'
import type { AnalysisResult, ShowcaseSummary } from '../types'
import '../styles/home.css'

/** The case in the device frame and behind "Open a case": clean overlap, every confusion factor, court agreed. */
const LEAD_SLUG = 'vans_mschf'
const HIGH = 0.75

const Q_ICON: Record<QuestionKey, ReactNode> = {
  overlap: <IconUsers size={18} />,
  fame: <IconPulse size={18} />,
  zone: <IconMap size={18} />,
}

/** Vans v. MSCHF when the showcase lists it, else the first showcase case. */
function leadCase(list: ShowcaseSummary[] | null | undefined): ShowcaseSummary | undefined {
  if (!list?.length) return undefined
  return list.find((c) => c.slug === LEAD_SLUG) ?? list[0]
}

// ------------------------------------------------------------------ 2. the three questions

function Questions() {
  return (
    <section className="band" aria-labelledby="q-title">
      <div className="wrap">
        <div className="band__head">
          <p className="eyebrow">{QUESTIONS_HEAD.eyebrow}</p>
          <h2 id="q-title" className="t-headline">
            {QUESTIONS_HEAD.title}
          </h2>
        </div>
        <div className="group qgrid">
          <div className="qgrid__row qgrid__head caption tertiary" aria-hidden="true">
            <span>{QUESTION_COLUMNS.q}</span>
            <span>{QUESTION_COLUMNS.measure}</span>
            <span>{QUESTION_COLUMNS.court}</span>
          </div>
          <ul className="qgrid__list">
            {QUESTIONS.map((q, i) => (
              <li key={q.key}>
                <Reveal index={i} className="qgrid__row">
                  <h3 className="qgrid__q">
                    <span className="qgrid__glyph" aria-hidden="true">
                      {Q_ICON[q.key]}
                    </span>
                    {q.q}
                  </h3>
                  <dl className="qgrid__facts">
                    <div>
                      <dt className="caption tertiary qgrid__dt">{QUESTION_COLUMNS.measure}</dt>
                      <dd>{q.measure}</dd>
                    </div>
                    <div>
                      <dt className="caption tertiary qgrid__dt">{QUESTION_COLUMNS.court}</dt>
                      <dd className="secondary">{q.court}</dd>
                    </div>
                  </dl>
                </Reveal>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ 2b. the preliminary read

function ReadBand() {
  return (
    <section className="band band--alt" aria-labelledby="read-band-title">
      <div className="wrap">
        <div className="band__head">
          <p className="eyebrow">{READ_BAND.eyebrow}</p>
          <h2 id="read-band-title" className="t-headline">
            {READ_BAND.title}
          </h2>
        </div>
        <ul className="group limits-group">
          {READ_BAND.rows.map((r, i) => (
            <li key={r.title} className="group__row group__row--top">
              <span className="limits-group__n num" aria-hidden="true">
                {i + 1}
              </span>
              <span className="group__main">
                <span className="group__title">{r.title}</span>
                <span className="group__sub">{r.text}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ 3. device frame (live evidence preview)

function FrameSkeleton() {
  return (
    <div className="frame__screen" aria-busy="true" aria-label="Loading the evidence preview">
      <div className="frame__top">
        <Skeleton h={12} w="40%" />
      </div>
      <div className="frame__lead">
        <Skeleton h={26} w="96%" />
        <Skeleton h={26} w="70%" />
      </div>
      <div className="frame__gauges">
        {[0, 1, 2].map((i) => (
          <div key={i} className="pgauge">
            <Skeleton h={12} w="50%" />
            <Skeleton h={40} w="6rem" />
            <Skeleton h={8} w="100%" r={999} />
            <Skeleton h={12} w="85%" />
          </div>
        ))}
      </div>
    </div>
  )
}

type GaugeProps = {
  label: string
  value: number | null
  /** How the number reads: ordinal percentile or "out of 100". */
  kind: 'percentile' | 'score'
  left: string
  right: string
  meaning: string | null
  /** Shown instead of the gauge when there is no value. */
  missing: string
  note?: string
}

/** A 0–100 gauge with end labels, the value, one sentence of meaning and a "high starts here" tick. */
function PlainGauge({ label, value, kind, left, right, meaning, missing, note }: GaugeProps) {
  const reduce = useReducedMotion()
  if (value == null) {
    return (
      <figure className="pgauge pgauge--empty">
        <figcaption className="pgauge__label">{label}</figcaption>
        <p className="pgauge__none">{PREVIEW.notMeasured}</p>
        <p className="pgauge__meaning footnote secondary">{missing}</p>
      </figure>
    )
  }
  const pos = clamp01(value)
  const shown = to100(value)
  const fmt = (v: number) => (kind === 'percentile' ? ordinalSuffix(v) : String(Math.round(v)))
  const reading = kind === 'percentile' ? `${ordinalSuffix(shown)} percentile` : `${shown} out of 100`
  const spoken = `${label}: ${reading}, on a scale from ${left} at 0 to ${right} at 100. High starts at ${to100(HIGH)}.`
  return (
    <figure className="pgauge">
      <figcaption className="pgauge__label">{label}</figcaption>
      <p className="pgauge__value">
        <AnimatedNumber value={shown} format={fmt} className="pgauge__num" />
        <span className="pgauge__unit secondary">{kind === 'percentile' ? 'percentile' : 'out of 100'}</span>
      </p>
      <div className="pgauge__bar" role="img" aria-label={spoken}>
        <span className="hgauge">
          <span className="pgauge__high" style={{ left: `${HIGH * 100}%` }}>
            <span className="pgauge__high-label caption tertiary">{PREVIEW.high}</span>
          </span>
          <motion.span className="hgauge__fill" initial={{ scaleX: 0 }} animate={{ scaleX: pos }} transition={reduce ? fade : springSlow} />
          <motion.span
            className="hgauge__marker"
            initial={{ left: '0%' }}
            animate={{ left: `${pos * 100}%` }}
            transition={reduce ? fade : springSlow}
          />
        </span>
      </div>
      <div className="hgauge__scale caption tertiary" aria-hidden="true">
        <span>{left}</span>
        <span>{right}</span>
      </div>
      {meaning && <p className="pgauge__meaning footnote secondary">{meaning}</p>}
      {note && <p className="caption tertiary">{note}</p>}
    </figure>
  )
}

function FrameContent({ summary, result }: { summary: ShowcaseSummary; result: AnalysisResult }) {
  const memo = result.memo
  const ev = result.evidence
  const names = sideNames(result)
  const story = CASE_STORIES[summary.slug]
  const older = story?.brands[0] ?? names.senior
  // Lean chips name the brand that a factor favours, never "senior"/"junior".
  const [olderShort, newerShort] = story?.short.split(' v. ') ?? [names.senior, names.junior]
  const chipNames = { senior: olderShort ?? names.senior, junior: newerShort ?? names.junior }

  const overlap = ev?.overlap?.symmetric_percentile ?? null
  const fameRaw = ev?.fame?.fame_score ?? ev?.fame?.breadth_score ?? null
  const conc = ev?.zone?.concentration_index ?? null
  const nationwide = conc == null ? null : 1 - clamp01(conc)

  // Why a gauge is empty: the question was never part of this dispute, or Qloo had too little data.
  const routed = result.routing?.analyses
  const context = result.routing?.context_only ?? []
  const missing = (a: 'overlap' | 'fame' | 'zone') => (routed && !routed.includes(a) ? PREVIEW.notPleaded[a] : PREVIEW.tooThin)

  // Chips only for questions this dispute raised; an unpleaded one already says so in its gauge card.
  // Context-only analyses (measured, not raised by the pleading) are not factor findings of this dispute.
  const FACTOR_ANALYSIS: Record<string, 'overlap' | 'bridging' | 'fame' | 'zone'> = {
    relatedness_of_goods: 'overlap',
    channels_and_purchasers: 'overlap',
    bridging_the_gap: 'bridging',
    fame: 'fame',
    zone_of_reputation: 'zone',
  }
  const findings = (memo?.findings ?? []).filter((f) => {
    const a = FACTOR_ANALYSIS[f.factor]
    return !(a && ((routed && !routed.includes(a)) || context.includes(a)))
  })

  // Lead with the preliminary read (from the pleadings), then the code-computed bottom line.
  const read = memo?.preliminary_read ?? null
  const readLine = readSentence(memo?.read_line)
  const bottom = memo?.bottom_line || plainHeadline(memo?.headline || summary.one_liner)
  const lead = readLine || bottom
  const trace = result.trace
  const facts = runFacts(memo?.appendix_queries.length ?? 0, trace[0]?.ts, trace[trace.length - 1]?.ts)
  const readFrom = readFromText(result.extraction?.document_type, read?.one_sided_input)

  return (
    <Reveal from="none" className="frame__screen">
      <div className="frame__top">
        <p className="eyebrow frame__eyebrow">
          <span className="frame__live" aria-hidden="true" />
          {story?.short ?? summary.parties}
        </p>
        <Link to={`/case/${encodeURIComponent(summary.slug)}`} className="frame__open">
          Open the case <IconChevron size={13} />
        </Link>
      </div>

      <div className="frame__lead">
        <p className="caption tertiary">{readLine ? 'Preliminary read' : 'The bottom line'}</p>
        <p className="frame__headline serif">{lead}</p>
        {readLine && read && <ReadChips read={read} names={chipNames} size="sm" />}
        {readLine && bottom && <p className="frame__second">{bottom}</p>}
        {findings.length > 0 && (
          <ul className="frame__chips" aria-label="How each factor leans">
            {findings.map((f) => (
              <li key={f.factor} className="frame__finding">
                <span className="caption secondary">{factorLabel(f.factor)}</span>
                <LeanChip lean={f.lean} size="sm" names={chipNames} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="frame__gauges">
        <PlainGauge
          label="Fans overlap"
          kind="percentile"
          value={overlap}
          left="separate crowds"
          right="same crowd"
          meaning={overlap == null ? null : readOverlap(overlap)}
          missing={missing('overlap')}
          note={ev?.overlap?.used_proxy ? `Measured through stand-in brands for ${chipNames.junior}.` : undefined}
        />
        <PlainGauge
          label="Known by everyone"
          kind="score"
          value={fameRaw}
          left="one crowd"
          right="everyone"
          meaning={fameRaw == null ? null : `${older}: ${readFame(fameRaw)}`}
          missing={missing('fame')}
        />
        <PlainGauge
          label="Known where"
          kind="score"
          value={nationwide}
          left="one region"
          right="nationwide"
          meaning={nationwide == null ? null : `${older}: ${readNationwide(nationwide)}`}
          missing={missing('zone')}
        />
      </div>

      <p className="frame__foot caption tertiary num">
        {readFrom}, {PREVIEW.foot}
        {facts && ` ${facts}.`}
      </p>
    </Reveal>
  )
}

function DeviceFrame({ list, loadingList }: { list: ShowcaseSummary[] | null | undefined; loadingList: boolean }) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'start 0.45'] })
  const scale = useTransform(scrollYProgress, [0, 1], [0.94, 1])
  const opacity = useTransform(scrollYProgress, [0, 1], [0.55, 1])

  const first = leadCase(list)
  const slug = first?.slug ?? ''
  const detail = useAsync(() => (slug ? api.showcaseCase(slug) : Promise.resolve(null)), [slug])
  const loading = loadingList || (!!first && detail.loading)
  const failed = !loading && (detail.error || !first || !detail.data)

  if (failed) return null
  return (
    <motion.div ref={ref} className="frame" style={reduce ? undefined : { scale, opacity }}>
      {loading || !first || !detail.data ? <FrameSkeleton /> : <FrameContent summary={first} result={detail.data} />}
    </motion.div>
  )
}

function Preview(props: { list: ShowcaseSummary[] | null | undefined; loadingList: boolean }) {
  return (
    <section className="band" aria-labelledby="preview-title">
      <div className="wrap wrap--wide">
        <div className="band__head band__head--center">
          <p className="eyebrow">{PREVIEW.eyebrow}</p>
          <h2 id="preview-title" className="t-headline">
            {PREVIEW.title}
          </h2>
          <p className="t-subtitle">{PREVIEW.sub}</p>
        </div>
        <DeviceFrame {...props} />
        <p className="caption tertiary frame__caption">{PREVIEW.caption}</p>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ 4. the results, in words

/** Court vs Tea Rose for one showcase case: two one-word verdict chips, two statements and the agreement line, all computed. */
function Verdict({ story, summary }: { story: CaseStory; summary: ShowcaseSummary | undefined }) {
  const f = readFieldsFromSummary(summary)
  const a = f ? agreement(f.lean, story.outcome) : null
  return (
    <>
      <VerdictChips court={courtChip(story)} read={f ? readChip(f.lean, story) : null} />
      <span className="case-row__line">
        <span className="case-row__k">{SCORECARD.court}</span> {story.court}
      </span>
      {f && (
        <span className="case-row__line">
          <span className="case-row__k">{SCORECARD.read}</span> {teaRoseSentence(f, story.brands)}
        </span>
      )}
      {f && a && (
        <span className="case-row__line">
          <span className="chip chip--sm">{AGREEMENT_LABEL[a]}</span>
          <span className="sr-only">;</span>{' '}
          <span className="secondary">{agreementDetail(f, story.outcome, story.brands)}</span>
        </span>
      )}
    </>
  )
}

/** The eighteen-case results as a short statistical write-up (numbers computed live); the data back-test as a side note. */
function Scorecard({ list }: { list: ShowcaseSummary[] | null | undefined }) {
  const paras = resultsParagraphs(list)
  return (
    <section className="band band--alt" aria-labelledby="bt-title">
      <div className="wrap">
        <div className="band__head">
          <p className="eyebrow">{SCORECARD.eyebrow}</p>
          <h2 id="bt-title" className="t-headline">
            {SCORECARD.title}
          </h2>
        </div>
        <div className="bt__text">
          {(paras ?? [RESULTS_CAVEAT]).map((p, i) => (
            <p key={i} className="bt__body">
              {p}
            </p>
          ))}
        </div>
        <p className="secondary bt__note">{SCORECARD.dataNote}</p>
        <p className="bt__more">
          <Link to="/method#backtest" className="btn btn--link">
            {SCORECARD.link} <IconChevron size={13} />
          </Link>
        </p>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ 5. seven famous fights

function CaseRows({ slugs, list }: { slugs: readonly string[]; list: ShowcaseSummary[] | null | undefined }) {
  return (
    <ul className="group case-list">
      {slugs.map((slug, i) => {
        const c = CASE_STORIES[slug]
        if (!c) return null
        return (
          <li key={slug}>
            <Reveal index={i}>
              <Link to={`/case/${encodeURIComponent(slug)}`} className="group__row case-row">
                <span className="group__main">
                  <span className="case-row__title">{c.short}</span>
                  <span className="case-row__meta">{c.brands.join(' · ')}</span>
                  <Verdict story={c} summary={list?.find((x) => x.slug === slug)} />
                </span>
                <span className="group__chev" aria-hidden="true">
                  <IconChevron size={16} />
                </span>
              </Link>
            </Reveal>
          </li>
        )
      })}
    </ul>
  )
}

/** Seven cases chosen for the story; the other eleven behind a quiet disclosure, same rows. */
function Fights({ list }: { list: ShowcaseSummary[] | null | undefined }) {
  const rest = CASE_ORDER.filter((slug) => !FEATURED.includes(slug))
  return (
    <section id="cases" className="band" aria-labelledby="cases-title">
      <div className="wrap">
        <div className="band__head">
          <p className="eyebrow">{FIGHTS.eyebrow}</p>
          <h2 id="cases-title" className="t-headline">
            {FIGHTS.title}
          </h2>
          <p className="t-subtitle">{FIGHTS.sub}</p>
        </div>
        <CaseRows slugs={FEATURED} list={list} />
        {rest.length > 0 && (
          <Disclosure className="cases-more" printOpen={false} summary={FIGHTS.more}>
            <CaseRows slugs={rest} list={list} />
          </Disclosure>
        )}
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ 6. what it will not tell you

function WillNot() {
  return (
    <section className="band band--alt" aria-labelledby="limits-title">
      <div className="wrap">
        <div className="band__head">
          <p className="eyebrow">{WILL_NOT.eyebrow}</p>
          <h2 id="limits-title" className="t-headline">
            {WILL_NOT.title}
          </h2>
          <p className="t-subtitle">{WILL_NOT.lead}</p>
        </div>
        <ul className="group limits-group">
          {WILL_NOT.items.map((l, i) => (
            <li key={l} className="group__row group__row--top">
              <span className="limits-group__n num" aria-hidden="true">
                {i + 1}
              </span>
              <span className="group__main">{l}</span>
            </li>
          ))}
        </ul>
        <p className="t-title limits-closing">{WILL_NOT.closing}</p>
        <p className="limits-more">
          <Link to="/method#limitations" className="btn btn--link">
            {WILL_NOT.link} <IconChevron size={13} />
          </Link>
        </p>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ 7. how it works (collapsible timeline)

function StepNode({ who, n }: { who: StepWho; n: number }) {
  return (
    <span className={`tl__node tl__node--${who}`} aria-hidden="true">
      {who === 'code' ? <IconCode size={15} /> : <span className="num">{n}</span>}
    </span>
  )
}

function HowItWorks() {
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(false)
  const listId = useId()
  return (
    <section className="band" aria-labelledby="how-title">
      <div className="wrap wrap--wide">
        <div className="band__head">
          <p className="eyebrow">{HOW.eyebrow}</p>
          <h2 id="how-title" className="t-headline">
            {HOW.title}
          </h2>
        </div>
        <div className="tl" data-open={open || undefined}>
          <span className="tl__track" aria-hidden="true">
            <motion.span
              className="tl__progress"
              initial={{ scaleX: reduce ? 1 : 0, scaleY: reduce ? 1 : 0 }}
              whileInView={{ scaleX: 1, scaleY: 1 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={reduce ? fade : { type: 'spring', bounce: 0, duration: 1.4 }}
            />
          </span>
          <ol className="tl__steps" id={listId}>
            {HOW.steps.map((s, i) => (
              <li key={s.id} className="tl__step">
                <StepNode who={s.who} n={i + 1} />
                <span className="tl__label">
                  <span className="tl__n num tertiary">{i + 1}</span> {s.label}
                  <span className="sr-only"> ({HOW.who[s.who]})</span>
                </span>
                <AnimatePresence initial={false}>
                  {open && (
                    <motion.span
                      className="tl__text footnote secondary"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={reduce ? fade : springQuick}
                    >
                      {s.text}
                    </motion.span>
                  )}
                </AnimatePresence>
                {!open && <span className="tl__text tl__text--print footnote secondary">{s.text}</span>}
              </li>
            ))}
          </ol>
        </div>
        <div className="tl__foot">
          <button
            type="button"
            className="btn btn--sm pressable tl__toggle"
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => setOpen((o) => !o)}
          >
            <motion.span className="tl__toggle-chev" animate={{ rotate: open ? 90 : 0 }} transition={reduce ? fade : springQuick} aria-hidden="true">
              <IconChevron size={13} />
            </motion.span>
            {open ? HOW.collapse : HOW.expand}
          </button>
          <ul className="tl__legend caption secondary" aria-label="Legend">
            {(['agent', 'code', 'both'] as const).map((w) => (
              <li key={w}>
                <span className={`tl__key tl__node--${w}`} aria-hidden="true">
                  {w === 'code' && <IconCode size={10} />}
                </span>
                {HOW.who[w]}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ 8. analyze your own

function AnalyzeBand() {
  const limits = useAsync(() => api.limits(), [])
  const l = limits.data
  const caps =
    l?.daily_cap != null && l?.session_cap != null
      ? `A passcode is required. Live runs are capped at ${l.daily_cap} a day across the site and ${l.session_cap} per session.`
      : 'A passcode is required. Live runs are capped per day and per session.'
  return (
    <section className="band band--alt analyze-band" aria-labelledby="analyze-title">
      <div className="wrap analyze-band__inner">
        <div className="analyze-band__copy">
          <p className="eyebrow">{ANALYZE.eyebrow}</p>
          <h2 id="analyze-title" className="t-headline">
            {ANALYZE.title}
          </h2>
          <p className="t-subtitle">{ANALYZE.sub}</p>
          <p className="caption tertiary">{caps}</p>
        </div>
        <Link to="/analyze" className="btn btn--primary btn--lg">
          {ANALYZE.cta}
        </Link>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ page

export default function HomePage() {
  const list = useAsync(() => api.showcase(), [])
  const lead = leadCase(list.data)
  const caseHref = `/case/${encodeURIComponent(lead?.slug ?? LEAD_SLUG)}`
  return (
    <Page className="home">
      <PinnedHero caseHref={caseHref} />
      <Questions />
      <ReadBand />
      <Preview list={list.data} loadingList={list.loading} />
      <Scorecard list={list.data} />
      <Fights list={list.data} />
      <WillNot />
      <HowItWorks />
      <AnalyzeBand />
    </Page>
  )
}
