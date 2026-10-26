/**
 * Hand-written context for the showcase cases (current and former): what the court decided and what the taste
 * data shows. Plain English, brand names instead of "senior"/"junior". The agent's input is always the
 * pleadings (the complaint, plus the answer or motion where the docket has one); opinions and the sources below
 * are used only for the court line. Facts verified on
 * 2026-10-24/25 (see backend/eval/cases_candidates.csv and each entry's `source`). Live runs have no
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
  /** Where the court sentence was verified (opinion, docket entry or reliable report). */
  source?: string
  /**
   * Hand-checked: the strongest defence named in the pre-computed read (read_best_defence) is the ground the
   * court later ruled on. Set only where that holds; used by the home page's results paragraphs.
   */
  readNamedWinningDefence?: boolean
}

export const CASE_STORIES: Record<string, CaseStory> = {
  bad_spaniels: {
    short: 'Jack Daniel’s v. Bad Spaniels',
    brands: ['Jack Daniel’s', 'Bad Spaniels dog toy'],
    court:
      'The court found that whiskey drinkers and pet-product buyers do overlap, and the dog toy still won: a parody, no confusion.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Overlap was there. It did not decide the case.',
    outcome: 'newcomer won',
    source: 'https://www.govinfo.gov/content/pkg/USCOURTS-azd-2_14-cv-02057/pdf/USCOURTS-azd-2_14-cv-02057-3.pdf',
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
    data: 'DATA PENDING: computed after the run',
    outcome: 'older brand won',
    source: 'https://storage.courtlistener.com/pdf/2023/12/05/vans_inc._v._mschf_product_studio_inc..pdf',
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
    source: 'https://static.case.law/f3d/890/cases/0747-01.json',
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
  hermes_rothschild: {
    short: 'Hermès v. Rothschild',
    brands: ['Hermès (Birkin)', 'MetaBirkins NFTs (Mason Rothschild)'],
    court:
      'A New York jury found in February 2023 that the MetaBirkins NFTs infringed and diluted the Birkin mark and awarded Hermès $133,000, and the judge refused a new trial and barred further sales.',
    data: 'DATA PENDING: computed after the run',
    twist: 'A handbag and a digital token, and the jury saw one brand.',
    outcome: 'older brand won',
    source: 'https://storage.courtlistener.com/recap/gov.uscourts.nysd.573363/gov.uscourts.nysd.573363.191.0.pdf',
  },
  vans_walmart: {
    short: 'Vans v. Walmart',
    brands: ['Vans', 'Walmart side-stripe sneakers'],
    court:
      'The court granted Vans a preliminary injunction in March 2022, finding its side stripe and shoe designs valid and shoppers likely to be confused, and stopped Walmart selling the look-alike sneakers while the case went on.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Walmart conceded the shoes were related; the fight was over the stripe.',
    outcome: 'older brand won',
    source: 'https://storage.courtlistener.com/recap/gov.uscourts.cacd.836756/gov.uscourts.cacd.836756.65.0.pdf',
  },
  adidas_thom_browne: {
    short: 'adidas v. Thom Browne',
    brands: ['adidas', 'Thom Browne'],
    court:
      'A New York jury cleared Thom Browne of infringing or diluting the three stripes in January 2023; the Second Circuit upheld the verdict in 2024 and in April 2026 affirmed the refusal of a new trial.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Stripes on sportswear, stripes on luxury tailoring, and the jury saw two markets.',
    outcome: 'newcomer won',
    source: 'https://storage.courtlistener.com/pdf/2026/04/29/adidas_america_inc._v._thom_browne_inc..pdf',
  },
  nike_stockx: {
    short: 'Nike v. StockX',
    brands: ['Nike', 'StockX Vault NFTs'],
    court:
      'In March 2025 the court granted Nike summary judgment that StockX sold counterfeit Nike shoes but denied it on the other claims; the NFT trademark claims were headed for a jury when the parties settled in August 2025.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Sued over NFTs, won on fake shoes.',
    outcome: 'settled',
    source: 'https://www.thefashionlaw.com/nike-v-stockx-a-timeline-behind-the-trademark-lawsuit/',
  },
  bang_monster: {
    short: 'Bang v. Monster',
    brands: ['Bang (VPX)', 'Reign (Monster)'],
    court:
      'After a bench trial the court ruled for Monster: both are energy drinks for the same buyers, but Bang’s can design had no secondary meaning and shoppers were unlikely to confuse Reign with Bang.',
    data: 'DATA PENDING: computed after the run',
    twist: 'Same drink, same buyers, and still no confusion.',
    outcome: 'newcomer won',
    // Read named commonplace can features and the distinct BANG/REIGN wording; the court found no secondary meaning and no confusion.
    readNamedWinningDefence: true,
    source: 'https://www.govinfo.gov/content/pkg/USCOURTS-flsd-0_19-cv-60809/pdf/USCOURTS-flsd-0_19-cv-60809-4.pdf',
  },
  stone_millercoors: {
    short: 'Stone Brewing v. MillerCoors',
    brands: ['Stone Brewing', 'Keystone Light “Stone” cans (MillerCoors)'],
    court:
      'A San Diego jury found in 2022 that MillerCoors’ “Stone” branding of Keystone Light infringed Stone Brewing’s mark and awarded $56 million, and the Ninth Circuit upheld the award in 2025.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'older brand won',
    source: 'https://www.govinfo.gov/content/pkg/USCOURTS-casd-3_18-cv-00331/pdf/USCOURTS-casd-3_18-cv-00331-25.pdf',
  },
  rolex_beckertime: {
    short: 'Rolex v. BeckerTime',
    brands: ['Rolex', 'BeckerTime modified Rolex watches'],
    court:
      'The court held that BeckerTime’s Rolexes refitted with aftermarket parts infringed, and the Fifth Circuit upheld that in 2024 but denied Rolex BeckerTime’s profits because Rolex had waited too long to sue.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'older brand won',
    source: 'https://storage.courtlistener.com/pdf/2024/03/21/rolex_watch_v._beckertime.pdf',
  },
  kraft_cracker_barrel: {
    short: 'Kraft v. Cracker Barrel',
    brands: ['Cracker Barrel cheese (Kraft)', 'Cracker Barrel Old Country Store grocery hams'],
    court:
      'The court barred the restaurant chain from selling Cracker Barrel hams in grocery stores, and the Seventh Circuit upheld the injunction because the products would sit in the same aisles as Kraft’s cheese.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'older brand won',
    source: 'https://static.case.law/f3d/735/cases/0735-01.json',
  },
  innout_smashburger: {
    short: 'In-N-Out v. Smashburger',
    brands: ['In-N-Out (Double-Double)', 'Smashburger Triple Double'],
    court: 'The court never ruled on confusion: it refused to dismiss part of In-N-Out’s claims, and the burger chains settled in June 2019.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'settled',
    source: 'https://www.courtlistener.com/docket/6144796/idb/in-n-out-burgers-v-smashburger-ip-holder-llc/',
  },
  lv_my_other_bag: {
    short: 'Louis Vuitton v. My Other Bag',
    brands: ['Louis Vuitton', 'My Other Bag canvas totes'],
    court:
      'The court ruled for My Other Bag: a $35 canvas tote with a cartoon of a Louis Vuitton bag is an obvious joke that does not compete with the handbags, and the Second Circuit affirmed.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'newcomer won',
    source: 'https://static.case.law/f-supp-3d/156/cases/0425-01.json',
  },
  am_general_activision: {
    short: 'AM General v. Activision',
    brands: ['Humvee (AM General)', 'Call of Duty (Activision)'],
    court:
      'The court granted Activision summary judgment on every claim: showing Humvees in Call of Duty is artistic realism, and military vehicles and video games are too far apart to confuse buyers.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'newcomer won',
    source: 'https://storage.courtlistener.com/recap/gov.uscourts.nysd.483511/gov.uscourts.nysd.483511.218.0.pdf',
  },
  sazerac_fetzer: {
    short: 'Buffalo Trace v. 1000 Stories',
    brands: ['Buffalo Trace bourbon (Sazerac)', '1000 Stories wine (Fetzer)'],
    court:
      'After a bench trial the court ruled for Fetzer: bourbon and bourbon-barrel wine share some sales channels, but the two labels looked too different to confuse buyers.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'newcomer won',
    // Read named the distinct label presentation and branding; the court found the labels too different to confuse.
    readNamedWinningDefence: true,
    source: 'https://static.case.law/f-supp-3d/265/cases/1013-01.json',
  },
  tmobile_aio: {
    short: 'T-Mobile v. Aio',
    brands: ['T-Mobile magenta', 'Aio Wireless plum (AT&T)'],
    court:
      'The court stopped Aio using its plum colour because both sell no-contract plans to the same budget customers, but held T-Mobile’s magenta not famous enough with the general public for a dilution claim.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'mixed',
    source: 'https://static.case.law/f-supp-2d/991/cases/0888-01.json',
  },
  penn_state_vintage_brand: {
    short: 'Penn State v. Vintage Brand',
    brands: ['Penn State', 'Vintage Brand retro merchandise'],
    court:
      'A jury found in November 2024 that Vintage Brand’s retro Penn State merchandise willfully infringed the university’s marks, rejected its fair-use and functionality defences, and awarded $28,000.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'older brand won',
    source: 'https://www.mofo.com/resources/insights/241209-penn-state-secures-trademark-victory-in-dispute-over-vintage-merch',
  },
  ohio_state_redbubble: {
    short: 'Ohio State v. Redbubble',
    brands: ['Ohio State', 'Redbubble print-on-demand merchandise'],
    court:
      'The district court cleared Redbubble because it never sold the shirts itself, the Sixth Circuit reversed in 2021, and Ohio State dropped the case in a 2022 settlement.',
    data: 'DATA PENDING: computed after the run',
    outcome: 'settled',
    source: 'https://news.bloomberglaw.com/ip-law/ohio-state-redbubble-settle-leaving-trademark-liability-murky',
  },
}

export function caseStory(slug: string | undefined | null): CaseStory | undefined {
  return slug ? CASE_STORIES[slug] : undefined
}

/** Display names for sample documents that are not one of the showcase cases. */
const SAMPLE_NAMES: Record<string, string> = {
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
