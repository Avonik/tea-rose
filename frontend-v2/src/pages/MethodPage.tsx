import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { IconChevron, IconCode, IconSparkle } from '../components/icons'
import { StateView } from '../components/ui'
import backtest from '../content/backtest.json'
import { FIXED_LIMITATIONS } from '../content/limitations'
import { useActiveSection } from '../lib/sections'
import { Page } from '../motion/Reveal'
import '../styles/method.css'

interface BacktestRow {
  n: string | number
  metric: string
  value: string | number
  baseline: string
}

function BacktestTable({ rows, note, status }: { rows: BacktestRow[]; note?: string; status?: string }) {
  if (!rows.length) return <StateView kind="empty" title="No back-test results yet" body={note} />
  // Before the back-test has run, a table of "pending" pills reads as broken: show the plan.
  if (status === 'pending' && rows.every((r) => r.value === 'pending'))
    return (
      <div className="backtest-plan">
        <div className="group">
          <div className="group__header backtest-plan__status">
            <span className="chip chip--sm">Pre-registered</span>
            <span className="footnote secondary">{note}</span>
          </div>
          <ol className="backtest-plan__list">
            {rows.map((r, i) => (
              <li key={i} className="group__row group__row--top group__sep">
                <span className="method-n num">{i + 1}</span>
                <span className="group__main">
                  <span>{r.metric}</span>
                  {r.baseline && r.baseline !== 'n/a' && (
                    <span className="group__sub">Baseline: {r.baseline.replace(/:\s*pending$/i, '').toLowerCase()}</span>
                  )}
                </span>
                <span className="group__value caption">pending</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    )
  return (
    <>
      <div className="group table-scroll">
        <table className="table backtest">
          <thead>
            <tr>
              <th scope="col" className="r">
                n
              </th>
              <th scope="col">Metric</th>
              <th scope="col" className="r">
                Value
              </th>
              <th scope="col">Baseline</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="r num">{r.n === 'pending' ? <span className="chip chip--sm">pending</span> : r.n}</td>
                <td>{r.metric}</td>
                <td className="r num">{r.value === 'pending' ? <span className="chip chip--sm">pending</span> : r.value}</td>
                <td className="secondary">{r.baseline}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(note || status) && (
        <p className="caption tertiary">
          {status === 'pending' && <strong>Status: pending. </strong>}
          {note}
        </p>
      )}
    </>
  )
}

const QUESTIONS = [
  {
    title: 'Do the two brands share purchasers?',
    law: 'Likelihood of confusion: relatedness of goods, marketing channels and class of purchasers (Polaroid, Sleekcraft, DuPont). Plus bridging the gap: will the senior plausibly expand into the junior’s market?',
    qloo: 'Brand-to-brand affinity in both directions, filtered to each side’s category; the compare endpoint for audience traits; taste tags for bridging.',
    endpoints: ['/v2/insights · filter.type=urn:entity:brand', '/v2/analysis/compare', '/v2/insights · filter.type=urn:tag'],
  },
  {
    title: 'Is the mark famous with the general consuming public?',
    law: 'Dilution, 15 U.S.C. §1125(c). Fame is a threshold the owner must prove; Coach lost on it in 2012.',
    qloo: 'Affinity across six age buckets and both genders, the brand’s popularity percentile, and how much of the national heatmap is above the median.',
    endpoints: ['/v2/insights · filter.type=urn:demographics', '/v2/insights · filter.type=urn:heatmap'],
  },
  {
    title: 'Where is the mark actually known?',
    law: 'Common-law priority and the Tea Rose–Rectanus doctrine: an unregistered senior user’s rights reach only as far as its reputation.',
    qloo: 'A geographic heatmap of affinity for each side, its concentration, the top regions, and how much the two maps overlap.',
    endpoints: ['/v2/insights · filter.type=urn:heatmap · filter.location.query'],
  },
]

const TOC: [string, string][] = [
  ['questions', 'Three legal questions'],
  ['scores', 'How a number is made'],
  ['split', 'Agent vs. code'],
  ['evaluation', 'Evaluation'],
  ['limitations', 'Limitations'],
  ['qloo', 'About Qloo'],
]

const FORMULAS: [string, ReactNode][] = [
  [
    'Reading a percentile',
    <>
      Every overlap and bridging number is a position in a peer set, from 0 to 1. <strong>0.90</strong> means the brand ranks
      ahead of about nine in ten of its peers for that audience: unusually close. <strong>0.50</strong> is the middle of the
      pack: the taste graph shows no pull either way. <strong>Near 0</strong> means it barely shows up. It is never a share of
      consumers, so 0.52 does not mean “52% of buyers overlap”.
    </>,
  ],
  [
    'Overlap, one direction',
    <>
      Seed Qloo with the senior brand and list brands in the junior’s category, 50 per page, up to three pages. The rank is the
      junior brand’s position (on the proxy path, the mean position of the comparator brands). Percentile = 1 − (rank − 1) ÷
      size of the peer set. Not found in 150 results means percentile 0 and a note.
    </>,
  ],
  ['Symmetric overlap', <>The mean of both directions’ percentiles. If only one direction is computable, it is used and the memo says so.</>],
  ['Bridging', <>Seed with the senior brand and list its taste tags; the position of the junior’s category tag, as a percentile of that list.</>],
  [
    'Fame breadth',
    <>
      From the eight demographic buckets (six age, two gender): the average positive affinity divided by the average absolute
      affinity, bounded 0 to 1. A brand liked by every group scores near 1; one loved by a narrow group and disliked by the
      rest scores low. Reported with the popularity percentile and the share of national heatmap cells above the median.
    </>,
  ],
  [
    'Zone concentration',
    <>
      The Gini coefficient of heatmap affinity across cells (0 even, 1 concentrated). Top regions aggregate cells by label.
      Geographic overlap is the cosine similarity of the two sides’ binned maps.
    </>,
  ],
]

const AGENT = [
  'Reads the pleading; quotes goods verbatim.',
  'Decides which doctrines are live.',
  'Resolves brands; on the proxy path picks tags only from the menu Qloo returned, and records every option.',
  'Retries a query wider when it comes back empty, and records give-ups.',
  'Translates scores into factor language and writes the memo.',
]

const CODE = [
  'Every score is a pure, unit-tested Python function with no model in its path.',
  'Every Qloo call is logged with its exact parameters and result count.',
  'The query appendix is assembled by code, so every number in the memo cites a call.',
]

function MBand({ id, alt, eyebrow, title, children }: { id: string; alt?: boolean; eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className={`band ${alt ? 'band--alt' : ''} method__band`}>
      <div className="wrap wrap--wide method__wrap">
        <div className="method__content">
          <div className="band__head">
            <p className="eyebrow">{eyebrow}</p>
            <h2 id={`${id}-h`} className="t-headline">
              {title}
            </h2>
          </div>
          {children}
        </div>
      </div>
    </section>
  )
}

export default function MethodPage() {
  const active = useActiveSection(
    TOC.map(([id]) => id),
    200,
  )
  return (
    <Page className="method">
      <header className="band page-top method__band">
        <div className="wrap wrap--wide method__wrap">
          <div className="method__content method__intro">
            <p className="eyebrow">Method</p>
            <h1 className="t-display method__title">How Tea Rose turns taste data into evidence.</h1>
            <p className="t-subtitle">
              A trademark survey asks people questions. Tea Rose asks Qloo’s taste graph the same three questions and shows the
              ranks it got back. It is not a survey and does not replace one; it tells you whether commissioning one (about
              $15,000–$25,000 for a basic internet survey, up to the commonly cited $50,000–$100,000, and from 7–10 business days
              to about two months) is worth it, and what to ask.
            </p>
          </div>
        </div>
      </header>

      <div className="method__body">
      <nav className="method__toc no-print" aria-label="Sections">
        <div className="method__toc-inner">
          <p className="eyebrow method__toc-title">On this page</p>
          <ol>
            {TOC.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="method__toc-item pressable" aria-current={active === id ? 'location' : undefined}>
                  {label}
                </a>
              </li>
            ))}
          </ol>
        </div>
      </nav>

      <MBand id="questions" alt eyebrow="Doctrine" title="The three legal questions">
        <ol className="mq">
          {QUESTIONS.map((q, i) => (
            <li key={q.title} className="mq__tile">
              <span className="mq__n num" aria-hidden="true">
                {i + 1}
              </span>
              <h3 className="t-title-2">{q.title}</h3>
              <div className="mq__part">
                <p className="eyebrow">The law</p>
                <p className="callout">{q.law}</p>
              </div>
              <div className="mq__part">
                <p className="eyebrow">Qloo capability</p>
                <p className="callout">{q.qloo}</p>
              </div>
              <div className="mq__part">
                <p className="eyebrow">Endpoints</p>
                <ul className="chips">
                  {q.endpoints.map((e) => (
                    <li key={e}>
                      <code className="chip chip--mono">{e}</code>
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
        </ol>
      </MBand>

      <MBand id="scores" eyebrow="Scores" title="How a number is made">
        <p className="t-subtitle method__p">
          Qloo normalizes affinity <em>within each query</em>, so a 0.91 in one response and a 0.92 in another mean nothing side
          by side. Tea Rose therefore reports <strong>ranks inside a defined peer set</strong>: “ranks 131st of 300 pet-supply
          brands” is a statement a lawyer can check; a raw affinity is not.
        </p>
        <dl className="group formulas">
          {FORMULAS.map(([dt, dd]) => (
            <div key={dt} className="group__row group__row--top formulas__row group__sep">
              <dt className="formulas__dt">{dt}</dt>
              <dd className="formulas__dd">{dd}</dd>
            </div>
          ))}
        </dl>
      </MBand>

      <MBand id="split" alt eyebrow="Agent vs. code" title="The agent decides what to measure. Code decides the number.">
        <div className="split">
          <div>
            <h3 className="group-label split__label">
              <IconSparkle size={13} /> The agent (judgment)
            </h3>
            <ul className="group">
              {AGENT.map((t) => (
                <li key={t} className="group__row">
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="group-label split__label">
              <IconCode size={13} /> Code (arithmetic)
            </h3>
            <ul className="group">
              {CODE.map((t) => (
                <li key={t} className="group__row">
                  {t}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="secondary method__note">
          Like a firm commissioning a survey: the associate chooses the universe of consumers; the survey house runs the math. A
          model that remembers how a case ended can only influence which IDs are looked up, and every such choice is logged.
        </p>
      </MBand>

      <MBand id="evaluation" eyebrow="Evaluation" title="A narrow claim, tested before the scores exist.">
        <p className="t-subtitle method__p">
          The claim is narrow and testable: Qloo’s overlap signal agrees with how courts weighed the relatedness and purchaser
          factors. Labels from decided federal opinions are committed before any score is computed; the interpreting model sees
          “Brand A” and “Brand B”, never the parties’ names.
        </p>
        <BacktestTable rows={backtest.rows as BacktestRow[]} note={backtest.note} status={backtest.status} />
      </MBand>

      <MBand id="limitations" alt eyebrow="Limitations" title="What this cannot tell you.">
        <ol className="group method-limits">
          {FIXED_LIMITATIONS.map((l, i) => (
            <li key={l} className="group__row group__row--top">
              <span className="method-n num">{i + 1}</span>
              <span className="group__main">{l}</span>
            </li>
          ))}
        </ol>
        <p className="secondary method__note">
          These five appear in every memo, followed by anything specific to the case. Tea Rose is triage for the letter and
          early-motion stage. It does not replace a litigation survey and says so. Overlap evidence informs two factors; it does
          not decide a case: in Bad Spaniels the relatedness and channel factors favored Jack Daniel’s, and VIP still won on
          remand.
        </p>
      </MBand>

      <MBand id="qloo" eyebrow="Data" title="About Qloo">
        <p className="t-subtitle method__p">
          Qloo’s Taste AI is a graph of anonymized consumer preferences across brands, dining, music, film, travel and more. Its
          Insights API returns which entities and traits over-index for an audience defined by what it already likes, plus
          demographic and geographic breakdowns. Tea Rose sends only brand names, goods phrases and IDs; no personal data, and
          nothing about any individual.
        </p>
        <p className="secondary method__note">
          Without Qloo the product has nothing to say; without the agent it cannot read a complaint, choose a doctrine, or handle
          a brand the graph does not know.
        </p>
        <p className="method__cta">
          <Link to="/" className="btn btn--primary">
            Open a showcase case
          </Link>
          <Link to="/analyze" className="btn btn--link">
            Analyze a dispute <IconChevron size={13} />
          </Link>
        </p>
      </MBand>
      </div>
    </Page>
  )
}
