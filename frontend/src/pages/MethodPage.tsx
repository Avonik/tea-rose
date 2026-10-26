import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { IconChevron, IconCode, IconSparkle } from '../components/icons'
import { Disclosure } from '../components/ui'
import { showcaseAgreements, tallyLine } from '../content/copy'
import { FIXED_LIMITATIONS } from '../content/limitations'
import { useActiveSection } from '../lib/sections'
import { useAsync } from '../lib/useAsync'
import { api } from '../api'
import { Page } from '../motion/Reveal'
import '../styles/method.css'

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
      Small brands are often missing from Qloo. Then code builds a shortlist of well-known brands from the same product category, the model picks three of
      them (Pedigree and Milk-Bone for a dog toy, say) and decides whether that category is close enough to measure at all. Every block measured that way
      starts with “Measured through stand-ins” and says how close the category is: exact, partial, or only the nearest one Qloo has.
    </>,
  ],
  [
    'What the preliminary read is',
    <>
      After the numbers, the agent reads the pleadings (the complaint and, where the docket has it, the defendant’s answer) and says which way the case
      leans: toward the older brand, toward the newcomer, or too close to call. It names what the case turns on, the strongest defence and what could flip
      it, and reads what data cannot measure: how alike the marks are, copying on purpose, actual confusion alleged, how careful buyers are. Confidence
      (high, moderate or low) is the agent’s own judgment, not a probability. When only the plaintiff’s side is in the record, confidence is capped at low
      and the page says so. “Too close to call” is an honest answer, not a failure. The court’s decision is never in the agent’s input, but the model may
      remember how a famous case ended, so the showcase cases are a demonstration, not a test.
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
  ['backtest', 'How it was evaluated'],
  ['math', 'Show the math'],
  ['split', 'Agent vs. code'],
  ['limitations', 'Limitations'],
  ['qloo', 'About Qloo'],
]

const AGENT = [
  'Reads the pleadings; quotes goods verbatim.',
  'Decides which of the four analyses the dispute calls for.',
  'Finds each brand in Qloo; for a missing company picks a category only from the menu Qloo returned, and records every option.',
  'Chooses three stand-in brands from a shortlist code builds, and decides whether the category is close enough to measure.',
  'Retries a query wider when it comes back empty, and records give-ups.',
  'Turns the scores into the factors a court weighs and writes the memo.',
  'Gives the preliminary read: the lean, its confidence, what the case turns on, the strongest defence.',
]

const CODE = [
  'Every score is a pure, unit-tested Python function with no model in its path.',
  'Every Qloo call is logged with its exact parameters and result count.',
  'The query appendix is assembled by code, so every number in the memo cites a call.',
  'The bottom-line sentence is counted in code from the factor leans, never written by the model.',
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
  const tally = showcaseAgreements(useAsync(() => api.showcase(), []).data)
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
            Every case page answers first, then explains. The preliminary read and the bottom line come first, then three questions, each with one gauge on
            the same 0 to 100 scale and one sentence saying what it means. These are the six things worth knowing before you read one.
          </p>
          <DefList rows={READING} />
        </MBand>

        <MBand id="glossary" eyebrow="Glossary" title="The legal words, in one line each">
          <DefList rows={GLOSSARY} />
        </MBand>

        <MBand id="backtest" alt eyebrow="Evaluation" title="How it was evaluated">
          <div className="method__story">
            <p>
              <strong>On eight real cases.</strong> Tea Rose read each showcase case from the filed pleadings (the complaint and, where the docket has it, the
              defendant’s answer) with the court’s decision withheld, and gave its preliminary read. Then we compared that read with what the court decided.
              {tally && <> {tallyLine(tally)}</>} The court’s decision was withheld from the agent, but the model may still know how famous cases ended; treat
              this as a demonstration.
            </p>
            <p>
              <strong>On 80 decided cases.</strong> Separately, we labelled what the courts found about related goods and shared customers in 80 decided cases,
              from the opinions and before any data was pulled, and compared those findings with the audience measure. Where both brands are in Qloo, it tells
              the court’s “related goods” findings from the “unrelated” ones well: in 88 of 100 random pairs of a “related” and an “unrelated” case, it ranks the
              related one higher. Where a company is missing from Qloo, the stand-in method only tells you about its category.
            </p>
          </div>
          <p className="method__cta">
            <Link to="/#cases" className="btn btn--link">
              Court and Tea Rose on the eight cases <IconChevron size={13} />
            </Link>
            <a className="btn btn--link" href={RESULTS_URL} target="_blank" rel="noreferrer">
              Full back-test report (repository) <IconChevron size={13} />
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
            Like a firm commissioning a survey: the associate chooses who to ask; the survey house runs the math. The court’s decision is never given to the
            agent, but a model may remember how a famous case ended, and that memory can colour its preliminary read; it cannot change a number. That is why
            the showcase is a demonstration, not a test.
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
            The first five appear in every memo, followed by anything specific to the case; the last applies whenever there is a preliminary read. Overlap
            informs, it does not decide: in Bad Spaniels the court found that whiskey drinkers and pet-product buyers overlap, and the dog toy still won.
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
