import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { IconChevron, IconCode, IconSparkle } from '../components/icons'
import { Disclosure, StateView } from '../components/ui'
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

const RESULTS_URL = 'https://github.com/Avonik/tea-rose/tree/main/backend/eval/results'

/** Plain English first: how to read a memo, before any formula. */
const READING: [string, ReactNode][] = [
  [
    'What a lean is',
    <>
      For each question a court weighs, the memo says which way the taste data leans: toward the older brand (the one that sent the letter), toward the
      newcomer, neutral, or not enough data. A lean is a reading of the evidence, never a prediction of who wins.
    </>,
  ],
  [
    'What a percentile means here',
    <>
      Every score sits on the same 0 to 100 scale. For fans overlap, the 80th percentile means: among the brands in the other side’s category, this brand
      ranks ahead of about 80 in 100 with that audience. It is a position in a list, never a share of consumers, so the 52nd percentile does not mean “52% of
      buyers overlap”. 75 or more counts as high; around 50 means the data shows no pull either way.
    </>,
  ],
  [
    'Why a small category is coarse',
    <>
      A rank in a category of 300 brands moves in steps of a third of a point; in a category of 12 brands one place up or down moves the percentile by about
      eight points. Below 20 brands the memo says so in the same sentence as the number.
    </>,
  ],
  [
    'What a stand-in is',
    <>
      Small brands are often missing from Qloo. Then the model picks a few well-known brands from the same product category (Pedigree and Blue Buffalo for a
      pet food, say) and measures those instead. Every block measured that way starts with “Measured through stand-ins” and says how close the category is:
      exact, partial, or only the nearest one Qloo has.
    </>,
  ],
  [
    'Beyond the 150 strongest',
    <>
      Qloo lists the 150 brands an audience likes most. When a brand is not among them, its rank is unknown, so instead of a rank we show its affinity
      measured directly, as a share of the category’s strongest brand (“61% of the category’s strongest”).
    </>,
  ],
]

const GLOSSARY: [string, ReactNode][] = [
  ['Senior user (the older brand)', <>The party that used the mark first and usually sends the letter. On case pages we use its name instead.</>],
  ['Junior user (the newcomer)', <>The party accused of using a mark too close to the older one.</>],
  [
    'Likelihood of confusion',
    <>
      The core infringement test: would an appreciable number of ordinary buyers be confused about who makes or backs the product? Courts weigh about eight
      factors (Polaroid, Sleekcraft, DuPont); taste data informs two of them.
    </>,
  ],
  ['Relatedness of goods', <>Whether buyers would expect the two products to come from the same company. Informed by fans overlap.</>],
  ['Channels and purchasers', <>Whether the two products reach the same customers through the same kinds of shops. Informed by fans overlap.</>],
  [
    'Bridging the gap',
    <>Whether the older brand is likely to move into the newcomer’s market. Informed by how strongly its fans already like that category.</>,
  ],
  [
    'Fame and dilution',
    <>
      Dilution (15 U.S.C. §1125(c)) protects a famous mark from being blurred or tarnished even without confusion. Fame with the general consuming public is
      the threshold, and owners often lose on it: Coach did in 2012.
    </>,
  ],
  [
    'Zone of reputation',
    <>
      Under the Tea Rose–Rectanus doctrine an unregistered older user’s rights reach only as far as its reputation. The map answers where that is.
    </>,
  ],
  [
    'Parody',
    <>
      A use that comments on or mocks the original. In Jack Daniel’s v. VIP (2023) the Supreme Court held that parody used as a mark gets no special shield,
      but it still weighs in the confusion analysis; the dog toy won on remand.
    </>,
  ],
]

/** The formulas, grouped by measure, behind "Show the math". */
const MATH: { title: string; endpoints: string[]; rows: [string, ReactNode][] }[] = [
  {
    title: 'Fans overlap and bridging',
    endpoints: ['/v2/insights · filter.type=urn:entity:brand', '/v2/analysis/compare', '/v2/insights · filter.type=urn:tag'],
    rows: [
      [
        'Overlap, one direction',
        <>
          Seed Qloo with one brand and list brands in the other side’s category, 50 per page, up to three pages. The rank is the other brand’s position (with
          stand-ins, the mean position of the stand-in brands). Percentile = 1 − (rank − 1) ÷ size of the category.
        </>,
      ],
      [
        'Beyond the 150 strongest',
        <>
          A brand not found in the 150 results has no rank: the direction is marked censored, never counted as zero. One extra call looks up the brand’s
          affinity directly; the affinity ratio is that affinity divided by the top brand’s, shown as a whole percentage.
        </>,
      ],
      ['Symmetric overlap', <>The mean of both directions’ percentiles. If only one direction has a rank, it is used alone and the memo says so.</>],
      [
        'Bridging',
        <>
          Seed with the older brand and list its fans’ taste categories; the position of the newcomer’s category, as a percentile of that list. If the category
          itself is absent, the nearest parent category that is present counts, at half the score for each level up.
        </>,
      ],
    ],
  },
  {
    title: 'Known by everyone',
    endpoints: ['/v2/insights · filter.type=urn:demographics', '/v2/insights · filter.type=urn:heatmap'],
    rows: [
      [
        'Breadth',
        <>
          Qloo reports for six age groups and both genders how much more or less than average they like the brand. Breadth = 100 minus the average size of
          those deviations: a brand liked about equally by everyone scores near 100, one loved by a narrow group scores low. Shown as a score of 100.
        </>,
      ],
      ['Popularity', <>Qloo’s own popularity percentile for the brand, among all brands it knows.</>],
      ['National reach', <>The share of US map cells where liking for the brand is above its own median.</>],
      ['Fame score', <>The mean of breadth, popularity and national reach, out of 100. If one part is missing, breadth alone is shown and labelled so.</>],
    ],
  },
  {
    title: 'Known where',
    endpoints: ['/v2/insights · filter.type=urn:heatmap · filter.location.query'],
    rows: [
      [
        'Nationwide spread',
        <>
          100 minus the concentration (Gini coefficient) of the brand’s liking across map cells: 100 means spread evenly across the country, near 0 means a
          few places hold all of it.
        </>,
      ],
      ['Strongest regions', <>Map cells grouped by region; each region’s share of all liking on the map, as a whole percentage.</>],
      ['Same places', <>How closely the two brands’ maps match (cosine similarity), out of 100.</>],
    ],
  },
]

const TOC: [string, string][] = [
  ['read', 'How to read a memo'],
  ['glossary', 'Glossary'],
  ['backtest', 'Does it hold up?'],
  ['math', 'Show the math'],
  ['split', 'Agent vs. code'],
  ['limitations', 'Limitations'],
  ['qloo', 'About Qloo'],
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

function DefList({ rows, className = '' }: { rows: [string, ReactNode][]; className?: string }) {
  return (
    <dl className={`group formulas ${className}`}>
      {rows.map(([dt, dd]) => (
        <div key={dt} className="group__row group__row--top formulas__row group__sep">
          <dt className="formulas__dt">{dt}</dt>
          <dd className="formulas__dd">{dd}</dd>
        </div>
      ))}
    </dl>
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
            <h1 className="t-display method__title">How to read what Tea Rose tells you.</h1>
            <p className="t-subtitle">
              A trademark survey asks people questions. Tea Rose asks Qloo’s taste graph three of the questions a court asks about customers, and shows where
              each answer sits on one 0 to 100 scale. It is not a survey and does not replace one; it tells you, before you spend $15,000 to $100,000 and six to
              eight weeks on one, what the audience data already says.
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

        <MBand id="read" alt eyebrow="Plain English" title="How to read a memo">
          <p className="t-subtitle method__p">
            Every case page answers first, then explains. The bottom line comes first, then three questions, each with one gauge on the same 0 to 100 scale
            and one sentence saying what it means. These are the five things worth knowing before you read one.
          </p>
          <DefList rows={READING} />
        </MBand>

        <MBand id="glossary" eyebrow="Glossary" title="The legal words, in one line each">
          <DefList rows={GLOSSARY} />
        </MBand>

        <MBand id="backtest" alt eyebrow="Evaluation" title="Does it hold up?">
          <div className="method__story">
            <p>
              <strong>Run 1, as pre-registered.</strong> We wrote down how courts decided relatedness and shared customers in 80 decided cases before computing
              a single score, then ran the harness exactly as registered. It contained two measurement errors. It took a brand’s category from what its
              audience likes rather than what it sells, so a sneaker brand came out as “Food &amp; Beverage”; and a brand missing from the 150 strongest was
              counted as the very bottom of its category instead of as unknown.
            </p>
            <p>
              <strong>Run 2, both errors fixed.</strong> The category now comes from the brand’s own tags, and a missing rank is reported as “beyond the 150
              strongest”, backed by a direct affinity reading. The court labels did not change. Because the fixes came after we had seen run 1, run 2 is
              post-hoc and reported as such.
            </p>
            <p>
              <strong>Run 3, the product’s own resolver.</strong> Runs 1 and 2 identified brands with a strict name rule the product does not use, a design
              error that made the test stricter than the shipped tool. Run 3 identifies them with the same model-driven step the product runs, given no court
              labels. Scoring stays in code. Every report is kept, dated, unchanged.
            </p>
          </div>
          <BacktestTable rows={backtest.rows as BacktestRow[]} note={backtest.note} status={backtest.status} />
          <p className="method__cta">
            <a className="btn btn--link" href={RESULTS_URL} target="_blank" rel="noreferrer">
              Read every report in backend/eval/results <IconChevron size={13} />
            </a>
          </p>
        </MBand>

        <MBand id="math" eyebrow="Formulas" title="Show the math">
          <p className="t-subtitle method__p">
            Qloo scores affinity <em>within each query</em>, so a raw score from one answer means nothing next to another. Tea Rose therefore reports positions
            inside a stated category: “ranks 131st of 300 pet-supply brands” is a statement a lawyer can check. Code computes every number; no model touches
            them.
          </p>
          <div className="math">
            {MATH.map((m) => (
              <Disclosure key={m.title} className="math__item" summary={<>Show the math: {m.title.toLowerCase()}</>}>
                <DefList rows={m.rows} />
                <ul className="chips math__endpoints" aria-label="Qloo endpoints">
                  {m.endpoints.map((e) => (
                    <li key={e}>
                      <code className="chip chip--mono">{e}</code>
                    </li>
                  ))}
                </ul>
              </Disclosure>
            ))}
          </div>
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
            Like a firm commissioning a survey: the associate chooses who to ask; the survey house runs the math. A model that remembers how a case ended can only
            influence which brands are looked up, and every such choice is logged.
          </p>
        </MBand>

        <MBand id="limitations" eyebrow="Limitations" title="What it cannot tell you.">
          <ol className="group method-limits">
            {FIXED_LIMITATIONS.map((l, i) => (
              <li key={l} className="group__row group__row--top">
                <span className="method-n num">{i + 1}</span>
                <span className="group__main">{l}</span>
              </li>
            ))}
          </ol>
          <p className="secondary method__note">
            These five appear in every memo, followed by anything specific to the case. Overlap informs, it does not decide: in Bad Spaniels the court found
            that whiskey drinkers and pet-product buyers overlap, and the dog toy still won.
          </p>
        </MBand>

        <MBand id="qloo" alt eyebrow="Data" title="About Qloo">
          <p className="t-subtitle method__p">
            Qloo’s Taste AI is a graph of anonymized consumer preferences across brands, dining, music, film, travel and more. Its Insights API returns which
            brands and traits an audience likes more than average, plus age, gender and map breakdowns. Tea Rose sends only brand names, goods phrases and IDs;
            no personal data, and nothing about any individual.
          </p>
          <p className="method__cta">
            <Link to="/" className="btn btn--primary">
              Open a case
            </Link>
            <Link to="/analyze" className="btn btn--link">
              Analyze a document <IconChevron size={13} />
            </Link>
          </p>
        </MBand>
      </div>
    </Page>
  )
}
