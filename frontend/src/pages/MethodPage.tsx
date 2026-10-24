import { Link } from 'react-router-dom'
import backtest from '../content/backtest.json'
import { StateView } from '../components/ui'
import { FIXED_LIMITATIONS } from '../content/limitations'

interface BacktestRow {
  n: string | number
  metric: string
  value: string | number
  baseline: string
}

function BacktestTable({ rows, note, status }: { rows: BacktestRow[]; note?: string; status?: string }) {
  if (!rows.length) return <StateView kind="empty" title="No back-test results yet" body={note} />
  return (
    <>
      <div className="table-scroll">
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
                <td className="r num">{r.n === 'pending' ? <span className="chip chip--outline">pending</span> : r.n}</td>
                <td>{r.metric}</td>
                <td className="r num">{r.value === 'pending' ? <span className="chip chip--outline">pending</span> : r.value}</td>
                <td className="muted">{r.baseline}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(note || status) && (
        <p className="caption faint">
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

export default function MethodPage() {
  const toc = [
    ['questions', 'Three legal questions'],
    ['scores', 'How scores are computed'],
    ['split', 'Agent vs. code'],
    ['evaluation', 'Evaluation'],
    ['limitations', 'Limitations'],
    ['qloo', 'About Qloo'],
  ]
  return (
    <div className="container method page-enter">
      <header className="method__head">
        <p className="eyebrow">Method</p>
        <h1>How Tea Rose turns taste data into evidence</h1>
        <p className="method__lead muted">
          Three questions that are decided today on expensive surveys or on intuition are all questions about consumer
          taste. Here is what Tea Rose measures for each, how a number is computed, and where it stops.
        </p>
      </header>

      <div className="method__grid">
        <nav className="method__toc no-print" aria-label="Sections">
          <ol>
            {toc.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`}>{label}</a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="method__body">
          <section id="questions" aria-labelledby="questions-h">
            <h2 id="questions-h">The three legal questions</h2>
            <div className="q-cards">
              {QUESTIONS.map((q, i) => (
                <article key={q.title} className="q-card card card--flat">
                  <span className="q-card__n num">{i + 1}</span>
                  <h3>{q.title}</h3>
                  <p className="footnote">
                    <span className="faint">The law · </span>
                    {q.law}
                  </p>
                  <p className="footnote">
                    <span className="faint">Qloo capability · </span>
                    {q.qloo}
                  </p>
                  <ul className="q-card__eps">
                    {q.endpoints.map((e) => (
                      <li key={e}>
                        <code>{e}</code>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </section>

          <section id="scores" aria-labelledby="scores-h">
            <h2 id="scores-h">How scores are computed</h2>
            <p>
              Qloo normalizes affinity <em>within each query</em>, so a 0.91 in one response and a 0.92 in another mean
              nothing side by side. Tea Rose therefore reports <strong>ranks inside a defined peer set</strong>: “ranks
              131st of 300 pet-supply brands” is a statement a lawyer can check; a raw affinity is not.
            </p>
            <dl className="formulas">
              <div>
                <dt>Overlap, one direction</dt>
                <dd>
                  Seed Qloo with the senior brand and list brands in the junior’s category, 50 per page, up to three pages.
                  The rank is the junior brand’s position (on the proxy path, the mean position of the comparator brands).
                  Percentile = 1 − (rank − 1) ÷ size of the peer set. Not found in 150 results means percentile 0 and a
                  note.
                </dd>
              </div>
              <div>
                <dt>Symmetric overlap</dt>
                <dd>The mean of both directions’ percentiles. If only one direction is computable, it is used and the memo says so.</dd>
              </div>
              <div>
                <dt>Bridging</dt>
                <dd>Seed with the senior brand and list its taste tags; the position of the junior’s category tag, as a percentile of that list.</dd>
              </div>
              <div>
                <dt>Fame breadth</dt>
                <dd>
                  From the eight demographic buckets (six age, two gender): the average positive affinity divided by the
                  average absolute affinity, bounded 0 to 1. A brand liked by every group scores near 1; one loved by a
                  narrow group and disliked by the rest scores low. Reported with the popularity percentile and the share
                  of national heatmap cells above the median.
                </dd>
              </div>
              <div>
                <dt>Zone concentration</dt>
                <dd>
                  The Gini coefficient of heatmap affinity across cells (0 even, 1 concentrated). Top regions aggregate
                  cells by label. Geographic overlap is the cosine similarity of the two sides’ binned maps.
                </dd>
              </div>
            </dl>
          </section>

          <section id="split" aria-labelledby="split-h">
            <h2 id="split-h">The agent decides what to measure. Code decides the number.</h2>
            <div className="split">
              <div className="split__col split__col--agent">
                <h3>The agent (judgment)</h3>
                <ul>
                  <li>Reads the pleading; quotes goods verbatim.</li>
                  <li>Decides which doctrines are live.</li>
                  <li>Resolves brands; on the proxy path picks tags only from the menu Qloo returned, and records every option.</li>
                  <li>Retries a query wider when it comes back empty, and records give-ups.</li>
                  <li>Translates scores into factor language and writes the memo.</li>
                </ul>
              </div>
              <div className="split__col split__col--code">
                <h3>Code (arithmetic)</h3>
                <ul>
                  <li>Every score is a pure, unit-tested Python function with no model in its path.</li>
                  <li>Every Qloo call is logged with its exact parameters and result count.</li>
                  <li>The query appendix is assembled by code, so every number in the memo cites a call.</li>
                </ul>
              </div>
            </div>
            <p className="muted footnote">
              Like a firm commissioning a survey: the associate chooses the universe of consumers; the survey house runs the
              math. A model that remembers how a case ended can only influence which IDs are looked up, and every such choice
              is logged.
            </p>
          </section>

          <section id="evaluation" aria-labelledby="evaluation-h">
            <h2 id="evaluation-h">Evaluation</h2>
            <p>
              The claim is narrow and testable: Qloo’s overlap signal agrees with how courts weighed the relatedness and
              purchaser factors. Labels from decided federal opinions are committed before any score is computed; the
              interpreting model sees “Brand A” and “Brand B”, never the parties’ names.
            </p>
            <BacktestTable rows={backtest.rows as BacktestRow[]} note={backtest.note} status={backtest.status} />
          </section>

          <section id="limitations" aria-labelledby="limitations-h">
            <h2 id="limitations-h">Limitations</h2>
            <div className="limits">
              <ul className="limits__list">
                {FIXED_LIMITATIONS.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </div>
            <p className="muted footnote">
              These five appear in every memo, followed by anything specific to the case. Tea Rose is triage for the letter
              and early-motion stage. It does not replace a litigation survey and says so.
            </p>
          </section>

          <section id="qloo" aria-labelledby="qloo-h">
            <h2 id="qloo-h">About Qloo</h2>
            <p>
              Qloo’s Taste AI is a graph of anonymized consumer preferences across brands, dining, music, film, travel and
              more. Its Insights API returns which entities and traits over-index for an audience defined by what it already
              likes, plus demographic and geographic breakdowns. Tea Rose sends only brand names, goods phrases and IDs; no
              personal data, and nothing about any individual.
            </p>
            <p className="muted footnote">
              Without Qloo the product has nothing to say; without the agent it cannot read a complaint, choose a doctrine,
              or handle a brand the graph does not know.
            </p>
            <p>
              <Link to="/" className="btn btn--sm">
                Open a showcase case
              </Link>
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
