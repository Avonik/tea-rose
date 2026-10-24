import { Link } from 'react-router-dom'
import { api } from '../api'
import { IconArrow } from '../components/icons'
import { ErrorState, StateView } from '../components/ui'
import { useAsync } from '../lib/useAsync'
import type { ShowcaseSummary } from '../types'

const STEPS: { id: string; label: string; who: 'agent' | 'code' | 'both'; text: string }[] = [
  { id: 'extract', label: 'Extract', who: 'agent', text: 'Reads the pleading: parties, marks, goods quoted verbatim, claims.' },
  { id: 'route', label: 'Route', who: 'agent', text: 'Decides which legal questions are live. Dilution pleaded means fame is measured.' },
  { id: 'resolve', label: 'Resolve', who: 'agent', text: 'Finds each brand in Qloo, or picks proxy tags from the menu the API returns.' },
  { id: 'fetch', label: 'Fetch', who: 'agent', text: 'Calls Qloo, retries wider when a query comes back empty, logs every call.' },
  { id: 'score', label: 'Score', who: 'code', text: 'Pure Python, unit-tested, no model. Ranks and percentiles, never raw affinity.' },
  { id: 'interpret', label: 'Interpret', who: 'agent', text: 'Translates scores into factor language and names what is thin or proxied.' },
  { id: 'memo', label: 'Memo', who: 'both', text: 'Neutral memo; the query appendix is assembled by code, not written by the model.' },
]

function HowItWorks() {
  return (
    <section className="how" aria-labelledby="how-title">
      <div className="how__head">
        <div>
          <p className="eyebrow">How it works</p>
          <h2 id="how-title">The agent decides what to measure. Code decides the number.</h2>
        </div>
        <ul className="how__legend" aria-label="Legend">
          <li>
            <span className="how__key how__key--agent" aria-hidden="true" /> Agent judgment
          </li>
          <li>
            <span className="how__key how__key--code" aria-hidden="true" /> Deterministic code
          </li>
          <li>
            <span className="how__key how__key--both" aria-hidden="true" /> Agent writes, code builds the appendix
          </li>
        </ul>
      </div>
      <ol className="how__steps">
        {STEPS.map((s, i) => (
          <li key={s.id} className={`how__step how__step--${s.who}`}>
            <span className="how__index num" aria-hidden="true">
              {i + 1}
            </span>
            <span className="how__label">
              {s.label}
              <span className="sr-only">{s.who === 'code' ? ' (deterministic code)' : s.who === 'both' ? ' (agent writes, code builds the appendix)' : ' (agent)'}</span>
            </span>
            <span className="how__text">{s.text}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function CaseCard({ c }: { c: ShowcaseSummary }) {
  return (
    <li>
      <Link to={`/case/${encodeURIComponent(c.slug)}`} className="case-card">
        <span className="case-card__meta">
          <span>{c.parties}</span>
          {c.year != null && <span className="num">{c.year}</span>}
        </span>
        <span className="case-card__title">{c.title}</span>
        <span className="case-card__line">{c.one_liner}</span>
        <span className="case-card__foot">
          <span className="chips">
            {c.tags.map((t) => (
              <span key={t} className="chip">
                {t}
              </span>
            ))}
          </span>
          <span className="case-card__go" aria-hidden="true">
            <IconArrow size={16} />
          </span>
        </span>
      </Link>
    </li>
  )
}

function CaseGrid() {
  const { data, error, loading, reload } = useAsync(() => api.showcase(), [])
  if (loading)
    return (
      <ul className="case-grid" aria-busy="true" aria-label="Loading cases">
        {[0, 1, 2, 3].map((i) => (
          <li key={i}>
            <div className="case-card case-card--skeleton">
              <span className="skeleton" style={{ height: 12, width: '45%' }} />
              <span className="skeleton" style={{ height: 22, width: '70%' }} />
              <span className="skeleton" style={{ height: 12, width: '95%' }} />
              <span className="skeleton" style={{ height: 12, width: '80%' }} />
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
    <ul className="case-grid">
      {data.map((c) => (
        <CaseCard key={c.slug} c={c} />
      ))}
    </ul>
  )
}

export default function ShowcasePage() {
  return (
    <div className="page-enter">
      <section className="hero">
        <div className="container hero__inner">
          <p className="eyebrow hero__eyebrow">Trademark evidence from the taste graph</p>
          <h1 className="hero__title">
            Courts ask whether Jack Daniel’s drinkers and dog-toy buyers are the same people.
          </h1>
          <p className="hero__lead">
            Today that question goes to a consumer survey. Tea Rose gives you triage evidence from Qloo’s taste graph in
            two minutes, before you commission one, and every number traces to a logged Qloo query.
          </p>
          <p className="hero__note">
            A consumer survey costs from about $15,000–$25,000 for a basic internet survey up to the commonly cited
            $50,000–$100,000, and takes from 7–10 business days to about two months (IPWatchdog 2019; Michigan Bar Journal
            2020; California Lawyers Association 2025).
          </p>
          <div className="hero__actions">
            <Link to="/analyze" className="btn btn--primary btn--lg">
              Analyze your own dispute
              <IconArrow size={16} />
            </Link>
            <Link to="/method" className="btn btn--lg">
              How the numbers are made
            </Link>
          </div>
          <ul className="hero__facts" aria-label="The three survey questions Tea Rose answers">
            <li>
              <strong>Same customers?</strong>
              <span>Relatedness and channels: where each brand ranks among the other’s fans</span>
            </li>
            <li>
              <strong>Famous with everyone?</strong>
              <span>Dilution: how evenly the mark is liked across age and gender</span>
            </li>
            <li>
              <strong>Known where?</strong>
              <span>Zone of reputation: the map of where the mark is actually liked</span>
            </li>
          </ul>
        </div>
      </section>

      <section className="container section" aria-labelledby="cases-title">
        <div className="section__head">
          <div>
            <p className="eyebrow">Showcase</p>
            <h2 id="cases-title">Decided cases, re-run on the taste graph</h2>
          </div>
          <p className="muted section__aside">Pre-computed and free to open. Each memo cites every query it used.</p>
        </div>
        <CaseGrid />
      </section>

      <div className="container section">
        <HowItWorks />
      </div>
    </div>
  )
}
