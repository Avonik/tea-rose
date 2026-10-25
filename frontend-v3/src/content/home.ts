/**
 * Home page copy, in the order of docs/SITE_STORY.md. Plain English, brand names instead of roles,
 * legal terms defined in the sentence where they first appear, numbers as ordinals or whole
 * percentages.
 */

/** One countdown step: the number and its unit, singular when the number is 1. */
export type Tick = { n: number; unit: 'weeks' | 'days' | 'hours' | 'minutes' }

/**
 * The hero clock, from what a survey takes down to what a Tea Rose run takes. Strictly decreasing,
 * so scrolling only ever moves it one way per direction.
 */
export const COUNTDOWN: Tick[] = [
  ...[6, 5, 4, 3, 2, 1].map((n) => ({ n, unit: 'weeks' as const })),
  ...[6, 5, 4, 3, 2, 1].map((n) => ({ n, unit: 'days' as const })),
  ...[23, 18, 12, 8, 6, 4, 3, 2, 1].map((n) => ({ n, unit: 'hours' as const })),
  ...[45, 30, 20, 10, 5, 3, 2, 1].map((n) => ({ n, unit: 'minutes' as const })),
]

export const tickUnit = (t: Tick) => (t.n === 1 ? t.unit.slice(0, -1) : t.unit)

export const HERO = {
  /** Beat 1: what the clock is counting. */
  eyebrow: 'A consumer survey, when two brands fight over who their customers are',
  money: '$15,000 to $100,000.',
  weeks: 'Six to eight weeks.',
  source:
    'Survey costs: about $15,000 to $25,000 for a basic internet study (California Lawyers Association 2025; IPWatchdog 2019), commonly cited at $50,000 to $100,000, with about two months from start to report (IPWatchdog 2019; Michigan Bar Journal 2020).',
  /** Beat 2: the clock has reached a minute. */
  endEyebrow: 'With Tea Rose',
  end: 'Tea Rose reads the dispute and answers the customer questions in about a minute.',
  /** Read once by assistive tech instead of the ticking numeral. */
  sr: 'A consumer survey costs $15,000 to $100,000 and takes six to eight weeks. Tea Rose reads the dispute and answers the customer questions in about a minute.',
  /** Beat 3. */
  title: 'Trademark evidence from the taste graph.',
  promise:
    'Trademark fights turn on who the customers are. Tea Rose reads the dispute, answers the customer questions from Qloo’s taste graph, then says exactly what it cannot tell you.',
  openCase: 'Open a case',
  analyze: 'Analyze a document',
  hint: 'Scroll',
}

export type QuestionKey = 'overlap' | 'fame' | 'zone'

export const QUESTIONS_HEAD = {
  eyebrow: 'What it measures',
  title: 'The three questions a judge asks about customers.',
}

/** Three rows of one grid: headings of one length class, and two sentences of similar length each. */
export const QUESTIONS: { key: QuestionKey; q: string; measure: string; court: string }[] = [
  {
    key: 'overlap',
    q: 'Do the same people buy both?',
    measure: 'Where each brand ranks among the other’s fans, checked in both directions.',
    court: 'Two confusion factors: whether the goods are related, and whether they reach the same buyers.',
  },
  {
    key: 'fame',
    q: 'Is it famous with everyone?',
    measure: 'How evenly the brand is liked across ages and genders, and how far its reach extends.',
    court: 'The threshold for dilution: only a name the general public knows can stop a look-alike.',
  },
  {
    key: 'zone',
    q: 'Where is it actually known?',
    measure: 'The affinity map: the regions where the people who like the brand actually live.',
    court: 'Settles fights over an unregistered name, protected only where the public already knows it.',
  },
]

export const QUESTION_COLUMNS = { q: 'The question', measure: 'What we measure', court: 'What a court does with it' }

export const PREVIEW = {
  eyebrow: 'Live preview',
  title: 'Watch it read a real case.',
  sub: 'The model read the filing and picked the brands, Qloo returned the audiences, code computed every number.',
  foot: 'resolved against Qloo, scored in code.',
  /** How the foot names the source document, by extracted document type. */
  readFrom: {
    complaint: 'Read from the complaint',
    cease_and_desist: 'Read from the letter',
    opinion: 'Read from the court’s opinion',
    petition: 'Read from the petition',
  } as Record<string, string>,
  readFromDefault: 'Read from the filing',
  notMeasured: 'Not measured in this case',
  /** Why a gauge is empty: the question was not part of the dispute, or Qloo had too little data. */
  notPleaded: {
    overlap: 'No confusion claim in this dispute, so the audiences were not compared.',
    fame: 'No dilution claim in this dispute, so fame was not measured.',
    zone: 'No dispute over where the name is known, so no map was drawn.',
  },
  tooThin: 'Qloo returned too little data to measure this fairly; the memo says so.',
  high: 'high',
}

export const BACKTEST = {
  eyebrow: 'Back-test',
  title: 'Does it hold up?',
  body:
    'We checked it against 80 decided cases. Where both brands are in Qloo, the audience signal agrees with the court’s finding on related goods and shared customers in 88% of pairings, against 67% for the obvious rule “same product category”.',
  fallback:
    'Where one side is a company Qloo does not know, we fall back to its product category and the memo says so; that fallback is only as good as the category.',
  link: 'See the full report, including the two times we changed our method and why',
}

/** The eight showcase fights, in manifest order (backend/data/showcase/manifest.json). */
export const CASE_ORDER = [
  'vans_mschf',
  'adidas_skechers',
  'hermes_rothschild',
  'vans_walmart',
  'nike_stockx',
  'bang_monster',
] as const

export const FIGHTS = {
  eyebrow: 'Showcase',
  title: 'Six famous fights.',
  sub: 'What the court decided, and what the taste data shows. Pre-computed and free to open; every memo cites the Qloo queries it used.',
}

export const WILL_NOT = {
  eyebrow: 'Limits',
  title: 'What it will not tell you.',
  items: [
    'Whether the marks look or sound alike.',
    'Whether the newcomer copied on purpose.',
    'Whether anyone has actually been confused.',
    'How careful these buyers are when they shop.',
  ],
  closing: 'Not a survey. Not a verdict. A tool for counsel.',
  link: 'Read every limitation in the method',
}

export type StepWho = 'agent' | 'code' | 'both'

export const HOW = {
  eyebrow: 'How it works',
  title: 'The agent decides what to measure. Code decides the number.',
  expand: 'Show what each step does',
  collapse: 'Hide the step details',
  steps: [
    { id: 'extract', label: 'Extract', who: 'agent', text: 'The model reads the pleading: parties, marks, goods quoted verbatim, claims.' },
    { id: 'route', label: 'Route', who: 'agent', text: 'The model decides which legal questions are live. Dilution pleaded means fame is measured.' },
    { id: 'resolve', label: 'Resolve', who: 'agent', text: 'The model finds each brand in Qloo, or picks stand-in categories from the menu Qloo returns.' },
    { id: 'fetch', label: 'Fetch', who: 'agent', text: 'The agent calls Qloo, retries wider when a query comes back empty, and logs every call.' },
    { id: 'score', label: 'Score', who: 'code', text: 'Code computes ranks and percentiles: unit-tested Python, no model, never raw affinity.' },
    { id: 'interpret', label: 'Interpret', who: 'agent', text: 'The model translates the scores into factor language and names what is thin or stood in.' },
    { id: 'memo', label: 'Memo', who: 'both', text: 'The model writes a neutral memo; code assembles the query appendix.' },
  ] as { id: string; label: string; who: StepWho; text: string }[],
  who: { agent: 'Model judgment', code: 'Deterministic code', both: 'Model writes, code builds the appendix' } as Record<StepWho, string>,
}

export const ANALYZE = {
  eyebrow: 'Analyze your own',
  title: 'Bring your own dispute.',
  sub: 'Paste or upload a complaint or a cease-and-desist letter and get the same memo for your two brands.',
  cta: 'Analyze a document',
}
