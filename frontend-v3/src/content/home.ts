/**
 * Home page copy, in the order of docs/SITE_STORY.md. Plain English, brand names instead of roles,
 * legal terms defined in the sentence where they first appear, numbers as ordinals or whole
 * percentages.
 */

export const HERO = {
  eyebrow: 'Tea Rose',
  money: { from: '$15,000', to: '$100,000' },
  weeks: 'Six to eight weeks.',
  minute: 'About one minute.',
  stake: 'That is what a consumer survey costs when two brands fight over who their customers are.',
  source:
    'Survey costs: about $15,000 to $25,000 for a basic internet study (California Lawyers Association 2025; IPWatchdog 2019), commonly cited at $50,000 to $100,000, with about two months from start to report (IPWatchdog 2019; Michigan Bar Journal 2020).',
  turn: 'Before you spend it, know what the audience data already says.',
  turnSr: 'With Tea Rose: about one minute.',
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

export const QUESTIONS: { key: QuestionKey; q: string; measure: string; court: string }[] = [
  {
    key: 'overlap',
    q: 'Do the same people buy both?',
    measure: 'Where each brand ranks among the other’s fans, checked in both directions.',
    court:
      'Feeds two of the factors behind likelihood of confusion, the question whether buyers would think both products come from one company: whether the goods are related, and whether they reach the same purchasers through the same channels.',
  },
  {
    key: 'fame',
    q: 'Is the older brand famous with everyone, or only with its own crowd?',
    measure: 'How evenly the older brand is liked across age groups and genders, plus how far its reach extends nationally.',
    court:
      'Answers the threshold question for dilution, the claim that a look-alike weakens a name the general public knows, even when nobody is confused. Only a brand famous with everyone can bring it.',
  },
  {
    key: 'zone',
    q: 'Where is it actually known?',
    measure: 'The affinity map: the regions where people who like the brand actually live.',
    court:
      'Decides geographic disputes over an unregistered name, which is protected only in its zone of reputation, the places where the public already knows it.',
  },
]

export const PREVIEW = {
  eyebrow: 'Live preview',
  title: 'Watch it read a real case.',
  sub: 'The model read the complaint and picked the brands, Qloo returned the audiences, code computed every number.',
  foot: 'Read from the complaint, resolved against Qloo, scored in code.',
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

/** The five showcase fights, in the order the story tells them. Bad Spaniels leads because of the twist. */
export const CASE_ORDER = ['bad_spaniels', 'charbucks', 'chewy_vuiton', 'coach_triumph', 'vans_mschf'] as const

export const FIGHTS = {
  eyebrow: 'Showcase',
  title: 'Five famous fights.',
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
