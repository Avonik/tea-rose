/**
 * Hand-written context for the showcase cases (current and former):what the court decided and what the taste
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
  gucci_guess: {
    short: 'Gucci v. Guess',
    brands: ['Gucci', 'Guess'],
    court:
      'The court held that mid-market Guess and high-end Gucci still meet on the street, where a passer-by never sees the price tag, and found infringement for the brown/beige Quattro G and the green-red-green stripe but not for the Script Guess.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Different price points, same street.',
    outcome: 'mixed',
  },
  tiffany_costco: {
    short: 'Tiffany v. Costco',
    brands: ['Tiffany', 'Costco ‘Tiffany setting’ rings'],
    court:
      'The Second Circuit agreed the two stores’ engagement rings already compete, but threw out the $21 million judgment and sent the case to trial because a jury could find Costco’s ring buyers careful enough not to be confused.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Same product, but are the buyers too careful to be fooled?',
    outcome: 'mixed',
  },
  makers_mark_cuervo: {
    short: 'Maker’s Mark v. Cuervo',
    brands: ['Maker’s Mark', 'Jose Cuervo Reserva de la Familia'],
    court:
      'The Sixth Circuit called a $24 bourbon and a $100 tequila only somewhat related and gave that and the shared sales channels little weight, then affirmed infringement on the strength and similarity of the red dripping wax seal.',
    data: 'DATA PENDING: computed after the run',
    twist: 'The goods barely mattered; the wax did.',
    outcome: 'older brand won',
  },
  adidas_skechers: {
    short: 'adidas v. Skechers',
    brands: ['adidas', 'Skechers'],
    court:
      'The Ninth Circuit found the sneakers so closely related that buyers would assume one source and upheld the injunction against the Onix copy of the Stan Smith, but lifted the Cross Court injunction for lack of evidence of irreparable harm.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Same goods, same buyers, and still only half a win.',
    outcome: 'mixed',
  },
  caterpillar_disney: {
    short: 'Caterpillar v. Disney',
    brands: ['Caterpillar', 'George of the Jungle 2 (Disney)'],
    court:
      'The court saw no competition between bulldozers and a children’s film, doubted heavy-equipment buyers would be swayed by the movie, and refused to stop the video release.',
    data: 'DATA PENDING: computed after the run',
    twist: 'A famous mark, but no shared customers.',
    outcome: 'newcomer won',
  },
}

export function caseStory(slug: string | undefined | null): CaseStory | undefined {
  return slug ? CASE_STORIES[slug] : undefined
}

/** Display names for sample documents that are not one of the showcase cases. */
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
