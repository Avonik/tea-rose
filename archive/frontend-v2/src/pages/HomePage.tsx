import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { IconChevron, IconCode, IconMap, IconPulse, IconUsers } from '../components/icons'
import { ErrorState, LeanChip, Skeleton, StateView } from '../components/ui'
import { FIXED_LIMITATIONS } from '../content/limitations'
import { factorLabel, readPercentile } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { AnimatedNumber } from '../motion/AnimatedNumber'
import { Page, Reveal } from '../motion/Reveal'
import { fade, springSlow } from '../motion/springs'
import type { AnalysisResult, ShowcaseSummary } from '../types'
import '../styles/home.css'

// ------------------------------------------------------------------ copy

const QUESTIONS = [
  {
    q: 'Same customers?',
    law: 'Relatedness and channels: where each brand ranks among the other’s fans.',
    measure: 'Shared-purchaser percentile',
    icon: <IconUsers size={18} />,
  },
  {
    q: 'Famous with everyone?',
    law: 'Dilution: how evenly the mark is liked across age and gender.',
    measure: 'Fame breadth',
    icon: <IconPulse size={18} />,
  },
  {
    q: 'Known where?',
    law: 'Zone of reputation: the map of where the mark is actually liked.',
    measure: 'Geographic concentration',
    icon: <IconMap size={18} />,
  },
]

const STEPS: { id: string; label: string; who: 'agent' | 'code' | 'both'; text: string }[] = [
  { id: 'extract', label: 'Extract', who: 'agent', text: 'Reads the pleading: parties, marks, goods quoted verbatim, claims.' },
  { id: 'route', label: 'Route', who: 'agent', text: 'Decides which legal questions are live. Dilution pleaded means fame is measured.' },
  { id: 'resolve', label: 'Resolve', who: 'agent', text: 'Finds each brand in Qloo, or picks proxy tags from the menu the API returns.' },
  { id: 'fetch', label: 'Fetch', who: 'agent', text: 'Calls Qloo, retries wider when a query comes back empty, logs every call.' },
  { id: 'score', label: 'Score', who: 'code', text: 'Pure Python, unit-tested, no model. Ranks and percentiles, never raw affinity.' },
  { id: 'interpret', label: 'Interpret', who: 'agent', text: 'Translates scores into factor language and names what is thin or proxied.' },
  { id: 'memo', label: 'Memo', who: 'both', text: 'Neutral memo; the query appendix is assembled by code, not written by the model.' },
]

const WHO_LABEL = { agent: 'Agent judgment', code: 'Deterministic code', both: 'Agent writes, code builds the appendix' }

// ------------------------------------------------------------------ device frame (live evidence preview)

function FrameSkeleton() {
  return (
    <div className="frame__screen" aria-busy="true" aria-label="Loading the evidence preview">
      <div className="frame__top">
        <Skeleton h={12} w="40%" />
      </div>
      <div className="frame__grid">
        <div className="frame__lead">
          <Skeleton h={26} w="96%" />
          <Skeleton h={26} w="88%" />
          <Skeleton h={26} w="54%" />
          <div className="frame__chips">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} h={26} w={`${6 + (i % 2) * 2}rem`} r={999} />
            ))}
          </div>
        </div>
        <div className="frame__gauge">
          <Skeleton h={12} w="70%" />
          <Skeleton h={80} w="11rem" />
          <Skeleton h={8} w="100%" r={999} />
        </div>
      </div>
      <div className="frame__tiles">
        {[0, 1, 2].map((i) => (
          <div key={i} className="frame__tile">
            <Skeleton h={12} w="60%" />
            <Skeleton h={34} w="5rem" />
          </div>
        ))}
      </div>
    </div>
  )
}

function FrameContent({ summary, result }: { summary: ShowcaseSummary; result: AnalysisResult }) {
  const reduce = useReducedMotion()
  const memo = result.memo
  const ev = result.evidence
  const p = ev?.overlap?.symmetric_percentile ?? null
  const pos = p == null ? 0 : Math.max(0, Math.min(1, p))
  const n = memo?.appendix_queries.length ?? 0
  const tiles = [
    { q: 'Same customers?', v: p, label: 'Shared-purchaser percentile' },
    { q: 'Famous with everyone?', v: ev?.fame?.breadth_score ?? null, label: 'Fame breadth' },
    { q: 'Known where?', v: ev?.zone?.concentration_index ?? null, label: 'Geographic concentration' },
  ]
  return (
    <Reveal from="none" className="frame__screen">
      <div className="frame__top">
        <p className="eyebrow frame__eyebrow">
          <span className="frame__live" aria-hidden="true" />
          Live preview · {summary.parties}
        </p>
        <Link to={`/case/${encodeURIComponent(summary.slug)}`} className="frame__open">
          Open the case <IconChevron size={13} />
        </Link>
      </div>

      <div className="frame__grid">
        <div className="frame__lead">
          <p className="frame__headline serif">{memo ? memo.headline : summary.one_liner}</p>
          {memo && memo.findings.length > 0 && (
            <ul className="frame__chips" aria-label="Factor findings">
              {memo.findings.map((f) => (
                <li key={f.factor} className="frame__finding">
                  <span className="caption secondary">{factorLabel(f.factor)}</span>
                  <LeanChip lean={f.lean} size="sm" />
                </li>
              ))}
            </ul>
          )}
        </div>

        {ev?.overlap && (
          <figure className="frame__gauge">
            <figcaption className="caption secondary">Shared-purchaser percentile, both directions averaged</figcaption>
            <AnimatedNumber value={p} className="numeral frame__numeral" />
            <div className="hgauge" role="img" aria-label={`Percentile ${p ?? 'not computable'} on a scale from 0 to 1; 0.50 is the median`}>
              <span className="hgauge__mid" />
              <motion.span
                className="hgauge__fill"
                initial={{ scaleX: 0 }}
                animate={{ scaleX: pos }}
                transition={reduce ? fade : springSlow}
              />
              <motion.span
                className="hgauge__marker"
                initial={{ left: '0%' }}
                animate={{ left: `${pos * 100}%` }}
                transition={reduce ? fade : springSlow}
              />
            </div>
            <div className="hgauge__scale caption tertiary" aria-hidden="true">
              <span>0</span>
              <span>median</span>
              <span>1.00</span>
            </div>
            <p className="caption secondary">{readPercentile(p)}</p>
          </figure>
        )}
      </div>

      <ul className="frame__tiles" aria-label="The three questions, measured">
        {tiles.map((t) => (
          <li key={t.q} className="frame__tile">
            <span className="caption secondary">{t.q}</span>
            <AnimatedNumber value={t.v} className="frame__tile-num" />
            <span className="caption tertiary">{t.label}</span>
          </li>
        ))}
      </ul>

      {memo && (
        <p className="frame__foot caption tertiary num">
          {n} logged Qloo {n === 1 ? 'query' : 'queries'} · every number cites one
        </p>
      )}
    </Reveal>
  )
}

function DeviceFrame() {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'start 0.45'] })
  const scale = useTransform(scrollYProgress, [0, 1], [0.94, 1])
  const opacity = useTransform(scrollYProgress, [0, 1], [0.55, 1])

  const list = useAsync(() => api.showcase(), [])
  const first = list.data?.[0]
  const slug = first?.slug ?? ''
  const detail = useAsync(() => (slug ? api.showcaseCase(slug) : Promise.resolve(null)), [slug])
  const loading = list.loading || (!!first && detail.loading)
  const failed = !loading && (list.error || detail.error || !first || !detail.data)

  if (failed) return null
  return (
    <motion.div ref={ref} className="frame" style={reduce ? undefined : { scale, opacity }}>
      {loading || !first || !detail.data ? <FrameSkeleton /> : <FrameContent summary={first} result={detail.data} />}
    </motion.div>
  )
}

// ------------------------------------------------------------------ cases (grouped list)

function CaseRows() {
  const { data, error, loading, reload } = useAsync(() => api.showcase(), [])
  if (loading)
    return (
      <ul className="group case-list" aria-busy="true" aria-label="Loading cases">
        {[0, 1, 2, 3].map((i) => (
          <li key={i}>
            <div className="group__row case-row">
              <div className="group__main">
                <Skeleton h={18} w="30%" />
                <Skeleton h={12} w="45%" />
                <Skeleton h={12} w="80%" />
              </div>
            </div>
          </li>
        ))}
      </ul>
    )
  if (error) return <ErrorState error={error} onRetry={reload} title="Could not load the showcase" />
  if (!data?.length)
    return (
      <StateView
        kind="empty"
        title="No showcase cases yet"
        body="Pre-computed cases appear here once they are generated. You can still analyze your own document."
      />
    )
  return (
    <ul className="group case-list">
      {data.map((c, i) => (
        <li key={c.slug}>
          <Reveal index={i}>
            <Link to={`/case/${encodeURIComponent(c.slug)}`} className="group__row case-row">
              <span className="group__main">
                <span className="case-row__title">{c.title}</span>
                <span className="case-row__meta">
                  {c.parties}
                  {c.year != null && <span className="num"> · {c.year}</span>}
                </span>
                <span className="case-row__line">{c.one_liner}</span>
                {c.tags.length > 0 && (
                  <span className="chips case-row__tags">
                    {c.tags.map((t) => (
                      <span key={t} className="chip chip--sm chip--quiet">
                        {t}
                      </span>
                    ))}
                  </span>
                )}
              </span>
              <span className="group__chev" aria-hidden="true">
                <IconChevron size={16} />
              </span>
            </Link>
          </Reveal>
        </li>
      ))}
    </ul>
  )
}

// ------------------------------------------------------------------ how it works (timeline)

function StepNode({ who, n }: { who: 'agent' | 'code' | 'both'; n: number }) {
  return (
    <span className={`tl__node tl__node--${who}`} aria-hidden="true">
      {who === 'code' ? <IconCode size={15} /> : <span className="num">{n}</span>}
    </span>
  )
}

function HowItWorks() {
  const reduce = useReducedMotion()
  return (
    <section className="band" aria-labelledby="how-title">
      <div className="wrap wrap--wide">
        <div className="band__head">
          <p className="eyebrow">How it works</p>
          <h2 id="how-title" className="t-headline">
            The agent decides what to measure. Code decides the number.
          </h2>
        </div>
        <div className="tl">
          <span className="tl__track" aria-hidden="true">
            <motion.span
              className="tl__progress"
              initial={{ scaleX: reduce ? 1 : 0, scaleY: reduce ? 1 : 0 }}
              whileInView={{ scaleX: 1, scaleY: 1 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={reduce ? fade : { type: 'spring', bounce: 0, duration: 1.4 }}
            />
          </span>
          <ol className="tl__steps">
            {STEPS.map((s, i) => (
              <li key={s.id} className="tl__step">
                <StepNode who={s.who} n={i + 1} />
                <span className="tl__label">
                  <span className="tl__n num tertiary">{i + 1}</span> {s.label}
                  <span className="sr-only"> ({WHO_LABEL[s.who]})</span>
                </span>
                <span className="tl__text footnote secondary">{s.text}</span>
              </li>
            ))}
          </ol>
        </div>
        <ul className="tl__legend caption secondary" aria-label="Legend">
          {(['agent', 'code', 'both'] as const).map((w) => (
            <li key={w}>
              <span className={`tl__key tl__node--${w}`} aria-hidden="true">
                {w === 'code' && <IconCode size={10} />}
              </span>
              {WHO_LABEL[w]}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ page

export default function HomePage() {
  return (
    <Page className="home">
      <section className="band band--alt hero" aria-labelledby="hero-title">
        <div className="wrap hero__copy">
          <p className="eyebrow">Trademark evidence from the taste graph</p>
          <h1 id="hero-title" className="t-display hero__title">
            Do Jack Daniel’s drinkers buy dog toys?
          </h1>
          <p className="t-subtitle hero__sub">
            A consumer survey costs $15,000–$100,000 and takes weeks to months. Tea Rose answers from Qloo’s taste graph in two
            minutes, and shows its work.
          </p>
          <div className="hero__actions">
            <Link to="/analyze" className="btn btn--primary btn--lg">
              Analyze a dispute
            </Link>
            <Link to="/method" className="btn btn--link btn--lg">
              See the method <IconChevron size={14} />
            </Link>
          </div>
          <p className="caption tertiary hero__source">
            A survey runs about $15,000–$25,000 for a basic internet study, commonly $50,000–$100,000, and takes 7–10 business
            days to about two months (IPWatchdog 2019; Michigan Bar Journal 2020; California Lawyers Association 2025). Tea
            Rose is triage evidence before you commission one; every number traces to a logged Qloo query.
          </p>
        </div>
        <div className="wrap wrap--wide hero__frame">
          <DeviceFrame />
        </div>
      </section>

      <section className="band" aria-labelledby="q-title">
        <div className="wrap wrap--wide">
          <div className="band__head band__head--center">
            <p className="eyebrow">The survey questions, answered first</p>
            <h2 id="q-title" className="t-headline">
              Three questions, three measurements.
            </h2>
          </div>
          <ul className="qtiles">
            {QUESTIONS.map((q, i) => (
              <li key={q.q}>
                <Reveal index={i} className="qtile">
                  <span className="qtile__glyph" aria-hidden="true">
                    {q.icon}
                  </span>
                  <h3 className="qtile__q">{q.q}</h3>
                  <p className="qtile__law secondary">{q.law}</p>
                  <p className="qtile__measure caption">
                    <span className="tertiary">Measured as </span>
                    {q.measure}
                  </p>
                </Reveal>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="band band--alt" aria-labelledby="cases-title">
        <div className="wrap">
          <div className="band__head">
            <p className="eyebrow">Showcase</p>
            <h2 id="cases-title" className="t-headline">
              Decided cases, re-run on the taste graph.
            </h2>
            <p className="t-subtitle">Pre-computed and free to open. Each memo cites every query it used.</p>
          </div>
          <CaseRows />
        </div>
      </section>

      <HowItWorks />

      <section className="band band--alt" aria-labelledby="limits-title">
        <div className="wrap">
          <div className="band__head">
            <p className="eyebrow">Limitations</p>
            <h2 id="limits-title" className="t-headline">
              What this cannot tell you.
            </h2>
            <p className="t-subtitle">
              Affinity is not confusion, scores are ranks and never survey percentages, the data reflects today, small brands may
              be missing, and demographics are age and gender only.
            </p>
          </div>
          <ol className="group limits-group">
            {FIXED_LIMITATIONS.map((l, i) => (
              <li key={l} className="group__row group__row--top">
                <span className="limits-group__n num">{i + 1}</span>
                <span className="group__main">{l}</span>
              </li>
            ))}
          </ol>
          <p className="limits-more">
            <Link to="/method#limitations" className="btn btn--link">
              Read the limitations in the method <IconChevron size={13} />
            </Link>
          </p>
        </div>
      </section>
    </Page>
  )
}
