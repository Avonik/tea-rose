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
  ...[45, 30, 20, 10, 5, 3, 2].map((n) => ({ n, unit: 'minutes' as const })),
]

export const tickUnit = (t: Tick) => (t.n === 1 ? t.unit.slice(0, -1) : t.unit)

export const HERO = {
  /** The word next to the rose glyph: one brand mark, not a second headline. */
  brand: 'Tea Rose',
  /** Above the clock through beats 1 and 2: what the clock is counting. */
  eyebrow: 'Every trademark fight asks the same question: who are the customers? Finding out takes',
  /** Beat 1: the survey, under "6 weeks". */
  survey: 'with a consumer survey, at',
  money: '$15,000 to $100,000.',
  source:
    'Sources: California Lawyers Association 2025, IPWatchdog 2019, Michigan Bar Journal 2020. From about $15,000; commonly $50,000 to $100,000; weeks to two months.',
  /** Beat 2: replaces the survey line while the clock counts down to two minutes. */
  answer: 'with Tea Rose, which reads the pleadings and answers from Qloo’s taste graph.',
  /** Read once by assistive tech instead of the ticking numeral. */
  sr: 'Every trademark fight asks the same question: who are the customers? Finding out takes six weeks with a consumer survey, at $15,000 to $100,000, or about two minutes with Tea Rose, which reads the pleadings and answers from Qloo’s taste graph.',
  /** Beat 3: the clock has settled on two minutes. */
  title: 'Trademark evidence from the taste graph.',
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
    court: 'Two factors in likelihood of confusion (would buyers mistake who makes it): related goods, and the same buyers.',
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

/** The preliminary read, introduced right after the three questions: what the agent reads that data cannot measure. */
export const READ_BAND = {
  eyebrow: 'Then the agent reads the rest',
  title: 'A preliminary read, from the pleadings.',
  rows: [
    {
      title: 'What it is',
      text: 'Which way the case leans (toward the older brand, the newcomer, or too close to call), how confident the agent is, what the case turns on, the strongest defence, and what could flip it.',
    },
    {
      title: 'What it reads that data cannot measure',
      text: 'From the pleadings (the complaint and, where the docket has it, the defendant’s answer): how alike the marks are, copying on purpose, actual confusion alleged, how careful buyers are, and whether the mark can be protected at all.',
    },
    {
      title: 'What it is not',
      text: 'A prediction or a probability. The court’s decision is withheld from the agent, but the model may still know how famous cases ended, so the showcase is a demonstration, not a test.',
    },
  ],
}

export const PREVIEW = {
  eyebrow: 'Live preview',
  title: 'Watch it read a real case.',
  sub: 'The model read the pleadings and picked the brands, Qloo returned the audiences, code computed every number.',
  /** Follows readFromText (content/copy.ts), which names the documents the agent read. */
  foot: 'resolved against Qloo, scored in code.',
  /** The caption under the frame: what the agent was given, and what it never sees. */
  caption: 'Read from the pleadings, never the court’s decision.',
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

/** The results on the eighteen showcase cases, told as text (content/copy.ts resultsParagraphs computes the numbers). */
export const SCORECARD = {
  eyebrow: 'Does it hold up?',
  title: 'How it did on eighteen real cases.',
  court: 'Court:',
  read: 'Tea Rose:',
  /** The data back-test, as a side note: two sentences, no statistics. */
  dataNote:
    'Separately, we checked the audience measure itself against 80 decided cases, labelled from the opinions before any data was pulled. Where both brands are in Qloo, it tells the court’s “related goods” findings from the “unrelated” ones well: in 88 of 100 random pairs of a “related” and an “unrelated” case, it ranks the related one higher.',
  link: 'How it was evaluated',
}

/** All eighteen showcase fights, in manifest order (backend/data/showcase/manifest.json). */
export const CASE_ORDER = [
  'vans_mschf',
  'adidas_skechers',
  'hermes_rothschild',
  'vans_walmart',
  'nike_stockx',
  'bang_monster',
  'bad_spaniels',
  'adidas_thom_browne',
  'stone_millercoors',
  'rolex_beckertime',
  'kraft_cracker_barrel',
  'innout_smashburger',
  'lv_my_other_bag',
  'am_general_activision',
  'sazerac_fetzer',
  'tmobile_aio',
  'penn_state_vintage_brand',
  'ohio_state_redbubble',
] as const

/** The seven cases the home page shows first, in story order; the other eleven sit behind "All eighteen cases". */
export const FEATURED: readonly (typeof CASE_ORDER)[number][] = [
  'vans_mschf',
  'bad_spaniels',
  'hermes_rothschild',
  'vans_walmart',
  'rolex_beckertime',
  'lv_my_other_bag',
  'bang_monster',
]

export const FIGHTS = {
  eyebrow: 'Showcase',
  title: 'Seven famous fights.',
  sub: 'What the court decided, what Tea Rose read, and why. All eighteen cases are one tap away.',
  more: 'All eighteen cases',
}

export const WILL_NOT = {
  eyebrow: 'Limits',
  title: 'What it will not tell you.',
  /** Leads the list: these four are read from the pleadings in the preliminary read, never measured. */
  lead: 'Not measured, only read from what the parties allege:',
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
    { id: 'extract', label: 'Extract', who: 'agent', text: 'The model reads the pleadings: parties, marks, goods quoted verbatim, claims.' },
    { id: 'route', label: 'Route', who: 'agent', text: 'The model decides which of the four analyses the dispute calls for. Dilution pleaded means fame is measured.' },
    {
      id: 'resolve',
      label: 'Resolve',
      who: 'agent',
      text: 'The model finds each brand in Qloo. For a company Qloo does not know, it picks three stand-in brands from a shortlist code builds, and decides whether that category is close enough to measure.',
    },
    { id: 'fetch', label: 'Fetch', who: 'agent', text: 'The agent calls Qloo, retries wider when a query comes back empty, and logs every call.' },
    { id: 'score', label: 'Score', who: 'code', text: 'Code computes ranks and percentiles: tested Python, no model, never a raw affinity score.' },
    { id: 'interpret', label: 'Interpret', who: 'agent', text: 'The model turns the scores into the factors a court weighs and names what is thin or stood in.' },
    {
      id: 'assess',
      label: 'Assess',
      who: 'agent',
      text: 'The model gives the preliminary read: which way the case leans, how confident, what it turns on, the strongest defence. The court’s decision is never in its input.',
    },
    { id: 'memo', label: 'Memo', who: 'both', text: 'The model writes a neutral memo; code writes the bottom line and the query appendix.' },
  ] as { id: string; label: string; who: StepWho; text: string }[],
  who: { agent: 'Model judgment', code: 'Deterministic code', both: 'Model writes, code adds the bottom line and appendix' } as Record<StepWho, string>,
}

export const ANALYZE = {
  eyebrow: 'Analyze your own',
  title: 'Bring your own dispute.',
  sub: 'Paste or upload a complaint (with the defendant’s answer, if you have it) or a cease-and-desist letter and get the same memo for your two brands.',
  cta: 'Analyze a document',
}
