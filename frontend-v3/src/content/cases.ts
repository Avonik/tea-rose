/**
 * Hand-written context for the five showcase cases: what the court decided and what the taste
 * data shows. Plain English, brand names instead of "senior"/"junior". Facts verified against the
 * opinions on 2026-10-24/25 (see backend/eval/cases_candidates.csv for sources). Live runs have no
 * entry here and render without the court line.
 */
export type CaseStory = {
  /** Short display name for tiles and the home page list. */
  short: string
  /** The two brands as the reader knows them, older brand first. */
  brands: [string, string]
  /** One sentence: what the court decided. */
  court: string
  /** One sentence: what the taste data shows (from the pre-computed run). */
  data: string
  /** Optional one-line twist, used on the home page list. */
  twist?: string
  /** Where the dispute ended, for the header chip. */
  outcome: 'older brand won' | 'newcomer won' | 'mixed' | 'settled'
}

export const CASE_STORIES: Record<string, CaseStory> = {
  bad_spaniels: {
    short: 'Jack Daniel’s v. Bad Spaniels',
    brands: ['Jack Daniel’s', 'Bad Spaniels dog toy'],
    court:
      'The court found that whiskey drinkers and pet-product buyers do overlap, and the dog toy still won: a parody, no confusion.',
    data: 'The taste data supports Jack Daniel’s on two of three confusion factors and on fame, and is silent on parody.',
    twist: 'Overlap was there. It did not decide the case.',
    outcome: 'newcomer won',
  },
  charbucks: {
    short: 'Starbucks v. Charbucks',
    brands: ['Starbucks', 'Charbucks (Black Bear Micro Roastery)'],
    court:
      'The factors favoured Starbucks, yet the court denied the dilution claim: the marks were not similar enough.',
    data: 'The taste data puts audience overlap at the 80th percentile and supports Starbucks on both measured factors and on fame.',
    twist: 'Strong audience evidence, lost on similarity.',
    outcome: 'newcomer won',
  },
  chewy_vuiton: {
    short: 'Louis Vuitton v. Chewy Vuiton',
    brands: ['Louis Vuitton', 'Chewy Vuiton dog toys'],
    court: 'The court ruled for the parody: the joke works because everyone knows Louis Vuitton.',
    data: 'The taste data finds overlap, but only through a nearest-category stand-in (pet food), so the memo stays neutral and says why.',
    twist: 'The fame that makes the joke land is the fame the data confirms.',
    outcome: 'newcomer won',
  },
  coach_triumph: {
    short: 'Coach v. Triumph Learning',
    brands: ['Coach', 'COACH test-prep books'],
    court: 'The Federal Circuit found handbags and test-prep materials unrelated and Coach not famous enough for dilution.',
    data: 'The taste data agrees on the goods: Coach’s audience does not extend to educational publishing.',
    twist: 'Same word, different worlds, and the data sees it.',
    outcome: 'newcomer won',
  },
  vans_mschf: {
    short: 'Vans v. MSCHF',
    brands: ['Vans', 'Wavy Baby sneakers (MSCHF)'],
    court: 'The Second Circuit upheld the injunction: a distorted sneaker sold as a sneaker is not a protected parody.',
    data: 'The taste data puts audience overlap at the 98th percentile and supports Vans on both confusion factors.',
    twist: 'Same shoppers, same shelves, and the court agreed.',
    outcome: 'older brand won',
  },
}

export function caseStory(slug: string | undefined | null): CaseStory | undefined {
  return slug ? CASE_STORIES[slug] : undefined
}

/** Display names for sample documents that are not one of the five showcase cases. */
const SAMPLE_NAMES: Record<string, string> = {
  adidas_thom_browne: 'Adidas v. Thom Browne',
  taco_tuesday: 'Taco Tuesday',
  jack_daniels_v_vip: 'Jack Daniel’s v. VIP Products',
}

/** Trailing document kinds in sample file names, longest first, and how they are captioned. */
const SAMPLE_KINDS: [string, string][] = [
  ['cease_and_desist', 'Cease-and-desist letter'],
  ['counterclaims', 'Counterclaims'],
  ['complaint', 'Complaint'],
  ['opinion', 'Opinion'],
  ['petition', 'Petition'],
  ['letter', 'Letter'],
]

/** "cedar_hollow" → "Cedar Hollow", "a_v_b" → "A v. B". */
function humanise(id: string): string {
  return id
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((w) => (w === 'v' || w === 'vs' ? 'v.' : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ')
}

/**
 * A clean tile label for a sample document id such as "bad_spaniels_complaint" or
 * "cedar_hollow_cease_and_desist.txt": the case's short name where Tea Rose knows it, else the
 * humanised id, with the document kind split off as a caption. The backend's own titles are the
 * documents' first lines (docket numbers, banners), so they are not used.
 */
export function sampleLabel(name: string): { title: string; kind: string | null } {
  let id = name.replace(/\.(txt|md|pdf)$/i, '').toLowerCase()
  let kind: string | null = null
  for (const [suffix, label] of SAMPLE_KINDS) {
    if (id === suffix || id.endsWith(`_${suffix}`)) {
      kind = label
      id = id.slice(0, Math.max(0, id.length - suffix.length - 1))
      break
    }
  }
  const title = CASE_STORIES[id]?.short ?? SAMPLE_NAMES[id] ?? (id ? humanise(id) : humanise(name))
  return { title, kind }
}
