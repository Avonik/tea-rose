// Generates src/mock/jack-daniels.json: a realistic, internally consistent AnalysisResult for
// "Jack Daniel's v. VIP Products" (proxy path). Every tool_call in the trace is one of the
// memo's appendix queries, so the mock exercises the "every number cites a query" contract.
// Run: npm run gen:mock
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'

const here = dirname(fileURLToPath(import.meta.url))
const out = join(here, '..', 'src', 'mock')
mkdirSync(out, { recursive: true })

const uid = (s) => {
  const h = createHash('sha1').update(s).digest('hex').toUpperCase()
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`
}

const JD = uid('jack daniels')
const TAG_PET = 'urn:tag:category:qloo:pet_supplies'
const TAG_DOGTOY = 'urn:tag:category:qloo:dog_toys'
const TAG_WHISKEY = 'urn:tag:category:qloo:whiskey'
const comparators = ['KONG', 'Chuckit!', 'Nylabone', 'BarkBox', 'Petstages']
const comparatorIds = comparators.map(uid)

// ------------------------------------------------------------------------------- queries
const q = (endpoint, params, result_count, elapsed_ms, extra = {}) => ({
  endpoint,
  params,
  cache_hit: false,
  status: 200,
  elapsed_ms,
  result_count,
  fixture_file: null,
  ...extra,
})

const Q = {
  searchJD: q('/search', { query: "Jack Daniel's", types: 'urn:entity:brand', take: 10 }, 7, 212),
  searchBS: q('/search', { query: 'Bad Spaniels', types: 'urn:entity:brand', take: 10 }, 0, 188),
  tags: q('/v2/tags', { 'filter.query': 'dog toys', take: 10 }, 8, 164),
  comparators: q(
    '/v2/insights',
    { 'filter.type': 'urn:entity:brand', 'filter.tags': TAG_DOGTOY, 'sort_by': 'popularity', take: 5 },
    5,
    301,
  ),
  pet1: q(
    '/v2/insights',
    { 'filter.type': 'urn:entity:brand', 'signal.interests.entities': JD, 'filter.tags': TAG_PET, take: 50, page: 1, 'feature.explainability': true },
    50,
    644,
  ),
  pet2: q(
    '/v2/insights',
    { 'filter.type': 'urn:entity:brand', 'signal.interests.entities': JD, 'filter.tags': TAG_PET, take: 50, page: 2, 'feature.explainability': true },
    50,
    598,
  ),
  pet3: q(
    '/v2/insights',
    { 'filter.type': 'urn:entity:brand', 'signal.interests.entities': JD, 'filter.tags': TAG_PET, take: 50, page: 3, 'feature.explainability': true },
    50,
    611,
    { cache_hit: true, elapsed_ms: 9 },
  ),
  whiskey: q(
    '/v2/insights',
    { 'filter.type': 'urn:entity:brand', 'signal.interests.entities': comparatorIds.join(','), 'filter.tags': TAG_WHISKEY, take: 50, page: 1 },
    50,
    702,
  ),
  compare: q(
    '/v2/analysis/compare',
    { 'a.signal.interests.entities': JD, 'b.signal.interests.entities': comparatorIds.join(','), 'filter.type': 'urn:entity:brand', take: 50 },
    48,
    880,
  ),
  tagsNarrow: q(
    '/v2/insights',
    { 'filter.type': 'urn:tag', 'signal.interests.entities': JD, 'filter.tag.types': 'urn:tag:category:qloo:pet', take: 50 },
    0,
    233,
  ),
  tagsWide: q(
    '/v2/insights',
    { 'filter.type': 'urn:tag', 'signal.interests.entities': JD, 'filter.parents.types': 'urn:tag:category', take: 400 },
    400,
    1104,
  ),
  demo: q('/v2/insights', { 'filter.type': 'urn:demographics', 'signal.interests.entities': JD }, 1, 276),
  heatJD: q('/v2/insights', { 'filter.type': 'urn:heatmap', 'signal.interests.entities': JD, 'filter.location.query': 'United States' }, 40, 1388),
  heatJr: q(
    '/v2/insights',
    { 'filter.type': 'urn:heatmap', 'signal.interests.entities': comparatorIds.join(','), 'filter.location.query': 'United States' },
    32,
    1290,
  ),
}
// Fixture-mode run: every non-cached query names the fixture file that served it.
for (const [k, v] of Object.entries(Q)) if (!v.cache_hit) v.fixture_file = `fixtures/qloo/jd_${k.replace(/[A-Z]/g, (c) => '_' + c.toLowerCase())}.json`
const order = Object.keys(Q)
const qid = (k) => `Q${order.indexOf(k) + 1}`

// ------------------------------------------------------------------------------- trace
const t0 = Date.parse('2026-10-22T14:03:11Z')
const trace = []
let clock = t0
const ev = (node, type, title, detail = null, data = {}, dt = 400) => {
  clock += dt
  trace.push({ ts: new Date(clock).toISOString(), seq: trace.length + 1, node, type, title, detail, data })
}
const tool = (node, key, tool, title, resultTitle, dt = 300) => {
  const query = Q[key]
  ev(node, 'tool_call', title, null, { tool, query_id: qid(key), endpoint: query.endpoint, params: query.params }, dt)
  ev(node, 'tool_result', resultTitle, null, {
    query_id: qid(key),
    endpoint: query.endpoint,
    result_count: query.result_count,
    cache_hit: query.cache_hit,
    elapsed_ms: query.elapsed_ms,
    status: query.status,
  }, query.elapsed_ms)
}

ev('extract', 'run_started', 'Run started', 'Fixture mode · document of 41,212 characters', { mode: 'fixture' }, 0)
ev('extract', 'node_started', 'Reading the document')
ev('extract', 'decision', "Parties: Jack Daniel's Properties (senior) v. VIP Products (junior)", 'Senior = registrant and counterclaim plaintiff; junior = maker of the Bad Spaniels toy.', {}, 2400)
ev('extract', 'note', 'Claims pleaded: likelihood of confusion, dilution by tarnishment', 'Goods quoted verbatim: "Tennessee sour mash whiskey"; "durable rubber squeaky chew toys for dogs".')
ev('extract', 'node_finished', 'Extraction complete', '2 parties · 5 marks · 2 claims · 3 key quotes')

ev('route', 'node_started', 'Choosing analyses')
ev('route', 'decision', 'Run overlap + bridging', 'Likelihood of confusion pleaded: relatedness and channels/purchasers factors apply.', { analyses: ['overlap', 'bridging'] }, 1200)
ev('route', 'decision', 'Run fame + zone (as fame support)', 'Dilution pleaded: fame is a threshold. No priority dispute; heatmap used only for national coverage.', { analyses: ['fame', 'zone'] })
ev('route', 'node_finished', 'Routing complete', '4 analyses')

ev('resolve', 'node_started', 'Resolving brands in Qloo')
tool('resolve', 'searchJD', 'qloo_search', 'Search brand "Jack Daniel\'s"', '7 candidates')
ev('resolve', 'decision', "Senior → Jack Daniel's (brand)", 'Chose the parent brand over "Jack Daniel\'s Tennessee Honey" and the distillery venue.', { entity_id: JD })
tool('resolve', 'searchBS', 'qloo_search', 'Search brand "Bad Spaniels"', 'No results')
ev('resolve', 'warning', 'Junior brand not in Qloo → proxy path', 'Neither "Bad Spaniels" nor "VIP Products" resolves to a brand entity. Using the goods phrase verbatim.')
tool('resolve', 'tags', 'qloo_tags_search', 'Tags for goods phrase "dog toys"', '8 tag options')
ev('resolve', 'decision', 'Proxy tags: Dog Toys + Pet Supplies', 'Picked from the returned menu only; rejected "Toys & Games" (children) and "Dog Breeds" (not goods).', { chosen: [TAG_DOGTOY, TAG_PET] })
tool('resolve', 'comparators', 'qloo_insights_entities', 'Category-leading dog-toy brands', '5 comparator brands')
ev('resolve', 'decision', 'Comparators: KONG, Chuckit!, Nylabone, BarkBox, Petstages', 'Junior rank will be the mean rank of these five.')
ev('resolve', 'node_finished', 'Resolution complete', 'Universes: 300 pet-supply brands · 120 whiskey brands')

ev('fetch', 'node_started', 'Fetching evidence')
tool('fetch', 'pet1', 'qloo_insights_entities', "Pet-supply brands seeded by Jack Daniel's · page 1", '50 brands · 1 of 5 comparators')
tool('fetch', 'pet2', 'qloo_insights_entities', 'Same query · page 2', '50 brands · 2 of 5 comparators')
tool('fetch', 'pet3', 'qloo_insights_entities', 'Same query · page 3', '50 brands · 3 of 5 comparators (cached)')
ev('fetch', 'warning', '3 of 5 comparators within the 150-result limit (ranks 44, 97, 129)', 'KONG and BarkBox fall beyond page 3; ranks 158 and 227 interpolated from the explainability tail and flagged.')
tool('fetch', 'whiskey', 'qloo_insights_entities', 'Whiskey brands seeded by the comparators', "50 brands · Jack Daniel's at #64")
tool('fetch', 'compare', 'qloo_compare', "Audience comparison: Jack Daniel's vs comparators", '48 entities')
tool('fetch', 'tagsNarrow', 'qloo_insights_tags', "Jack Daniel's taste tags, pet types only", 'Empty response')
ev('fetch', 'decision', 'Retry with a wider tag filter', 'An empty narrow query is a parameter problem, not a finding. Widening to all category tags and locating Pet Supplies by position.')
tool('fetch', 'tagsWide', 'qloo_insights_tags', "Jack Daniel's taste tags, all categories", '400 tags')
tool('fetch', 'demo', 'qloo_demographics', "Demographics for Jack Daniel's", '6 age buckets · 2 genders')
tool('fetch', 'heatJD', 'qloo_heatmap', "US heatmap for Jack Daniel's", '40 cells')
tool('fetch', 'heatJr', 'qloo_heatmap', 'US heatmap for the dog-toy comparators', '32 cells')
ev('fetch', 'node_finished', 'Fetch complete', '14 queries · 1 retry · 1 cache hit')

ev('score', 'node_started', 'Scoring (pure Python, no model)')
ev('score', 'note', 'Overlap: senior→junior #131 of 300 (p=0.57); junior→senior #64 of 120 (p=0.48)', 'Symmetric percentile 0.52 · proxy path', {}, 120)
ev('score', 'note', 'Fame breadth 0.80 · popularity p=0.99 · coverage 0.61; zone Gini 0.27', 'Bridging: Pet Supplies #184 of 400 senior tags (p=0.54)', {}, 80)
ev('score', 'node_finished', 'Scores computed', 'Deterministic; same inputs give the same numbers', {}, 60)

ev('interpret', 'node_started', 'Translating scores into factor language')
ev('interpret', 'decision', 'Channels & purchasers: neutral (medium)', 'Overlap sits near the median of the pet-supply universe in both directions.', {}, 3100)
ev('interpret', 'decision', 'Fame: favors senior (high)', 'Positive affinity in 5 of 6 age buckets and among men; near-universal popularity.')
ev('interpret', 'node_finished', 'Findings ready', '5 factors · 6 limitations')

ev('memo', 'node_started', 'Writing the memo')
ev('memo', 'note', 'Appendix built in code from 14 recorded queries', null, {}, 4200)
ev('memo', 'node_finished', 'Memo complete', '4 sections')
ev('memo', 'run_finished', 'Memo ready', 'Total 41 s')

// ------------------------------------------------------------------------------- evidence
const peers = (names, start = 0.94, step = 0.035) =>
  names.map((name, i) => ({ entity_id: uid(name), name, rank: i + 1, affinity: +(start - i * step).toFixed(3) }))

const cities = [
  ['Nashville, TN', 36.16, -86.78, 1.0], ['Lynchburg, TN', 35.28, -86.37, 0.98], ['Knoxville, TN', 35.96, -83.92, 0.93],
  ['Memphis, TN', 35.15, -90.05, 0.91], ['Chattanooga, TN', 35.05, -85.31, 0.9], ['Louisville, KY', 38.25, -85.76, 0.86],
  ['Birmingham, AL', 33.52, -86.8, 0.84], ['Atlanta, GA', 33.75, -84.39, 0.78], ['Jackson, MS', 32.3, -90.18, 0.8],
  ['Little Rock, AR', 34.75, -92.29, 0.79], ['New Orleans, LA', 29.95, -90.07, 0.74], ['Dallas, TX', 32.78, -96.8, 0.72],
  ['Houston, TX', 29.76, -95.37, 0.68], ['San Antonio, TX', 29.42, -98.49, 0.63], ['Oklahoma City, OK', 35.47, -97.52, 0.7],
  ['Charlotte, NC', 35.23, -80.84, 0.69], ['Raleigh, NC', 35.78, -78.64, 0.6], ['Columbia, SC', 34.0, -81.03, 0.66],
  ['Jacksonville, FL', 30.33, -81.66, 0.61], ['Tampa, FL', 27.95, -82.46, 0.55], ['Miami, FL', 25.76, -80.19, 0.41],
  ['St. Louis, MO', 38.63, -90.2, 0.71], ['Kansas City, MO', 39.1, -94.58, 0.62], ['Indianapolis, IN', 39.77, -86.16, 0.6],
  ['Columbus, OH', 39.96, -83.0, 0.55], ['Detroit, MI', 42.33, -83.05, 0.5], ['Chicago, IL', 41.88, -87.63, 0.52],
  ['Milwaukee, WI', 43.04, -87.91, 0.47], ['Minneapolis, MN', 44.98, -93.27, 0.38], ['Denver, CO', 39.74, -104.99, 0.44],
  ['Phoenix, AZ', 33.45, -112.07, 0.43], ['Las Vegas, NV', 36.17, -115.14, 0.49], ['Los Angeles, CA', 34.05, -118.24, 0.33],
  ['San Francisco, CA', 37.77, -122.42, 0.22], ['Seattle, WA', 47.61, -122.33, 0.27], ['Portland, OR', 45.52, -122.68, 0.25],
  ['Salt Lake City, UT', 40.76, -111.89, 0.18], ['New York, NY', 40.71, -74.01, 0.31], ['Philadelphia, PA', 39.95, -75.17, 0.36],
  ['Boston, MA', 42.36, -71.06, 0.24],
]
const geohash = (lat, lon) => uid(`${lat},${lon}`).slice(0, 6).toLowerCase()
const points = cities.map(([label, latitude, longitude, affinity], i) => ({
  latitude, longitude, geohash: geohash(latitude, longitude), affinity, affinity_rank: +(1 - i / cities.length).toFixed(3), popularity: null, label,
}))
const jrCities = [
  ['Seattle, WA', 47.61, -122.33, 1.0], ['Portland, OR', 45.52, -122.68, 0.97], ['Denver, CO', 39.74, -104.99, 0.95],
  ['San Francisco, CA', 37.77, -122.42, 0.88], ['Los Angeles, CA', 34.05, -118.24, 0.83], ['San Diego, CA', 32.72, -117.16, 0.86],
  ['Austin, TX', 30.27, -97.74, 0.84], ['Minneapolis, MN', 44.98, -93.27, 0.79], ['Boston, MA', 42.36, -71.06, 0.74],
  ['New York, NY', 40.71, -74.01, 0.7], ['Chicago, IL', 41.88, -87.63, 0.72], ['Phoenix, AZ', 33.45, -112.07, 0.66],
  ['Salt Lake City, UT', 40.76, -111.89, 0.77], ['Boise, ID', 43.62, -116.2, 0.69], ['Raleigh, NC', 35.78, -78.64, 0.62],
  ['Atlanta, GA', 33.75, -84.39, 0.58], ['Nashville, TN', 36.16, -86.78, 0.6], ['Dallas, TX', 32.78, -96.8, 0.55],
  ['Philadelphia, PA', 39.95, -75.17, 0.57], ['Washington, DC', 38.91, -77.04, 0.63], ['Columbus, OH', 39.96, -83.0, 0.51],
  ['Kansas City, MO', 39.1, -94.58, 0.49], ['Tampa, FL', 27.95, -82.46, 0.5], ['Miami, FL', 25.76, -80.19, 0.42],
  ['Houston, TX', 29.76, -95.37, 0.47], ['Detroit, MI', 42.33, -83.05, 0.4], ['Las Vegas, NV', 36.17, -115.14, 0.45],
  ['Albuquerque, NM', 35.08, -106.65, 0.41], ['Charlotte, NC', 35.23, -80.84, 0.53], ['St. Louis, MO', 38.63, -90.2, 0.38],
  ['Memphis, TN', 35.15, -90.05, 0.29], ['Birmingham, AL', 33.52, -86.8, 0.27],
]
const junior_points = jrCities.map(([label, latitude, longitude, affinity], i) => ({
  latitude, longitude, geohash: geohash(latitude, longitude), affinity, affinity_rank: +(1 - i / jrCities.length).toFixed(3), popularity: null, label,
}))

const evidence = {
  overlap: {
    senior_to_junior_rank: 131,
    senior_to_junior_universe: 300,
    junior_to_senior_rank: 64,
    junior_to_senior_universe: 120,
    symmetric_percentile: 0.52,
    top_peers_senior_seed: peers(['Ruffwear', 'Orvis Dog', 'Carhartt Pet', 'Kurgo', 'Tractor Supply Pet', 'Yeti Boomer', 'Duluth Trading Pet', 'Purina Pro Plan', 'Blue Buffalo', 'Pedigree']),
    top_peers_junior_seed: peers(['Fireball', 'Crown Royal', 'Jameson', "Maker's Mark", 'Bulleit', 'Jim Beam', 'Woodford Reserve', 'Buffalo Trace', 'Evan Williams', 'Knob Creek'], 0.91, 0.032),
    senior_to_junior_percentile: 0.567,
    junior_to_senior_percentile: 0.475,
    // Qloo compare returns audience tags: traits that connect the two groups.
    shared_affinities: [
      ['Outdoor recreation', 'urn:tag:audience:qloo:outdoor_recreation', 0.81], ['Rural lifestyle', 'urn:tag:audience:qloo:rural', 0.74],
      ['Home ownership', 'urn:tag:audience:qloo:homeowners', 0.69], ['Grilling & barbecue', 'urn:tag:keyword:qloo:barbecue', 0.66],
      ['Country music', 'urn:tag:genre:qloo:country', 0.58], ['Pickup trucks', 'urn:tag:keyword:qloo:pickup_trucks', 0.55],
      ['Hunting & fishing', 'urn:tag:audience:qloo:hunting_fishing', 0.49], ['Warehouse clubs', 'urn:tag:keyword:qloo:warehouse_club', 0.41],
    ].map(([name, tag_id, score]) => ({ tag_id, name, type: tag_id.split(':').slice(0, 3).join(':'), score })),
    distinct_to_senior: [
      ['Harley-Davidson', 0.86, 0.21], ['Zippo', 0.77, 0.14], ['Copenhagen', 0.69, 0.09], ['Coors Light', 0.73, 0.2], ['Stetson', 0.62, 0.12], ['Wrangler', 0.66, 0.24],
    ].map(([name, a, b]) => ({ entity_id: uid(name), name, subtype: 'urn:entity:brand', a_affinity: a, b_affinity: b, delta: +(a - b).toFixed(2) })),
    distinct_to_junior: [
      ['Chewy', 0.12, 0.94], ['Rover', 0.08, 0.81], ['Petco', 0.19, 0.88], ['BarkBox', 0.06, 0.79], ["Trader Joe's", 0.21, 0.71], ['Wild One', 0.04, 0.6],
    ].map(([name, a, b]) => ({ entity_id: uid(name), name, subtype: 'urn:entity:brand', a_affinity: a, b_affinity: b, delta: +(a - b).toFixed(2) })),
    used_proxy: true,
    notes: [
      'Junior side is a proxy: rank is the mean rank of 5 dog-toy comparator brands (KONG, Chuckit!, Nylabone, BarkBox, Petstages).',
      'Two comparator ranks (158, 227) lie beyond the 150-result page limit and are interpolated; excluding them gives a mean rank of 90 (p=0.70).',
    ],
  },
  bridging: {
    category_tag_ids: [TAG_PET],
    category_rank_among_senior_tags: 184,
    senior_tag_universe: 400,
    category_affinity: 0.21,
    percentile: 0.54,
    notes: ['The narrow pet-type tag filter returned nothing; position was taken from the wide category-tag query.'],
  },
  fame: {
    demographics: {
      age: { '24_and_younger': 0.12, '25_to_29': 0.31, '30_to_34': 0.34, '35_to_44': 0.22, '45_to_54': 0.05, '55_and_older': -0.14 },
      gender: { male: 0.28, female: -0.19 },
    },
    breadth_score: 0.8,
    skew_description: 'Skews 25–34 and male; positive in 5 of 6 age buckets',
    popularity_percentile: 0.987,
    heatmap_coverage: 0.61,
    notes: ['Demographics are age and gender only; Qloo reports no income, race or ethnicity.'],
  },
  zone: {
    points,
    concentration_index: 0.27,
    top_regions: [
      { label: 'Tennessee', share: 0.142 }, { label: 'Kentucky & Alabama', share: 0.081 }, { label: 'Texas', share: 0.079 },
      { label: 'Georgia & the Carolinas', share: 0.074 }, { label: 'Mississippi & Arkansas', share: 0.064 },
    ],
    junior_points,
    geographic_overlap: 0.58,
    notes: ['Heatmap values are rank-normalized within each query: they show relative concentration, not absolute reach.'],
  },
}

// ------------------------------------------------------------------------------- memo
const memo = {
  headline:
    "Jack Daniel's fans sit near the median for pet-supply brands, so the taste graph neither shows nor rules out shared purchasers; the mark's audience is broad across ages and both genders.",
  // Same rules as backend scoring/bottom_line.py synthesize_bottom_line (computed in code there).
  bottom_line:
    "Taste data is neutral on all 3 confusion factors but supports the senior mark on fame. It is silent on mark similarity, intent and actual confusion.",
  findings: [
    { factor: 'relatedness_of_goods', lean: 'neutral', confidence: 'low', finding: "Whiskey and dog toys are different goods; the taste graph places Pet Supplies at #184 of 400 of the senior brand's taste tags (percentile 0.54), close to the middle. Nothing here suggests consumers would expect the senior to make dog toys.", evidence_refs: ['Q11', 'bridging.percentile'] },
    { factor: 'channels_and_purchasers', lean: 'neutral', confidence: 'medium', finding: "Seeded by Jack Daniel's, the dog-toy comparators rank #131 of 300 pet-supply brands; seeded by the comparators, Jack Daniel's ranks #64 of 120 whiskey brands. A symmetric percentile of 0.52 is median overlap: shared purchasers exist but are not concentrated.", evidence_refs: ['Q5', 'Q6', 'Q7', 'Q8', 'overlap.symmetric_percentile'] },
    { factor: 'bridging_the_gap', lean: 'neutral', confidence: 'low', finding: "The senior brand's audience shows no particular pull toward pet supplies (category affinity 0.21). Licensed pet merchandise exists in the market generally, but the data does not show this audience leaning that way.", evidence_refs: ['Q11'] },
    { factor: 'fame', lean: 'favors_senior', confidence: 'high', finding: 'Affinity is positive in 5 of 6 age buckets and among men, with a breadth score of 0.80 and a popularity percentile of 0.99. That is the profile of a household mark rather than a niche one, which supports the fame threshold for dilution.', evidence_refs: ['Q12', 'Q13', 'fame.breadth_score'] },
    { factor: 'zone_of_reputation', lean: 'insufficient_data', confidence: 'low', finding: 'No priority dispute is pleaded. The heatmap concentrates in Tennessee and the South (Gini 0.27) but covers 61% of national cells above the median; it is reported as fame support only.', evidence_refs: ['Q13', 'Q14'] },
  ],
  sections: [
    {
      id: 'scope',
      title: 'Question presented and scope',
      markdown:
        "Jack Daniel's Properties alleges that VIP Products' **Bad Spaniels** squeaky toy infringes and tarnishes the JACK DANIEL'S marks and bottle trade dress. This memo addresses the consumer-facing questions the taste graph can speak to:\n\n1. Do the two brands share purchasers (relatedness, channels and class of purchasers)?\n2. Does the senior brand's audience lean toward the junior's product category (bridging the gap)?\n3. Is the senior mark famous with the general consuming public (dilution threshold)?\n\nIt does not address parody, expressive use or the *Rogers* question the Supreme Court resolved in 2023. Bad Spaniels is not in Qloo's graph; the junior side is measured through five category-leading dog-toy brands chosen from the menu returned for the goods phrase *\"dog toys\"* (Q3, Q4).",
    },
    {
      id: 'purchasers',
      title: 'Shared purchasers',
      markdown:
        "Ranks, not raw affinity, carry the finding because Qloo normalizes affinity within each query.\n\n| Direction | Rank | Universe | Percentile |\n| --- | ---: | ---: | ---: |\n| Seeded by Jack Daniel's → dog-toy comparators | #131 | 300 pet-supply brands | 0.57 |\n| Seeded by comparators → Jack Daniel's | #64 | 120 whiskey brands | 0.48 |\n| **Symmetric** | | | **0.52** |\n\nThe compare response (Q9) connects the two audiences through outdoor recreation, rural lifestyle and home ownership, while each side keeps distinct anchors: Harley-Davidson and Zippo for the senior, Chewy and Rover for the comparators. Two comparator ranks fall beyond the 150-result page limit; excluding them raises the percentile to 0.70, so the finding is sensitive to the proxy set.",
    },
    {
      id: 'fame',
      title: 'Fame and breadth of recognition',
      markdown:
        "The demographic response (Q12) is positive in every age bucket except 55 and older (−0.14) and among men (+0.28); women under-index slightly (−0.19). The breadth score is **0.80** on a 0–1 scale and the popularity percentile is **0.99**. The national heatmap (Q13) shows above-median affinity in **61%** of returned cells.\n\nFor comparison, a mark the Federal Circuit found *not* famous for dilution (Coach, 2012) is expected to show a narrower profile; see the showcase. Breadth is a proxy for recognition across the general consuming public, not a recognition survey.",
    },
    {
      id: 'geography',
      title: 'Geography',
      markdown:
        "Affinity concentrates in Tennessee (14% of total), Kentucky and Alabama, Texas, and the Southeast, with a concentration index of **0.27** (0 = uniform). The dog-toy comparators skew West and Mountain (Q14); the cosine overlap of the two maps is **0.58**.\n\nNo party pleads common-law priority, so the zone of reputation is not a live issue. The map is included to show national reach for the fame question.",
    },
  ],
  limitations: [
    'Affinity is not confusion. Taste overlap shows who likes what; it does not measure whether any consumer was or would be confused about source.',
    'No survey percentages. Scores are ranks within one query, never a share of consumers, and must not be read as one.',
    'Data reflects today, not the year of the dispute. Audiences in 2014 or 2023 may have looked different.',
    'Coverage gaps. Small brands are often missing from Qloo; proxy categories stand in for them and every proxied finding is flagged.',
    'Age and gender only. Qloo reports no income, ethnicity or region-level demographics, and heatmaps show relative concentration, not absolute reach.',
    'Case-specific: the junior side is measured through five comparator brands, and two of their ranks lie beyond the 150-result page limit.',
  ],
  appendix_queries: order.map((k) => Q[k]),
}

const extraction = {
  document_type: 'complaint',
  title: "Jack Daniel's Properties, Inc. v. VIP Products LLC",
  senior: {
    side: 'senior',
    name: "Jack Daniel's Properties, Inc.",
    marks: ["JACK DANIEL'S", 'OLD NO. 7', "Jack Daniel's bottle and label trade dress"],
    goods: ['Tennessee sour mash whiskey'],
    channels: ['liquor stores', 'bars and restaurants', 'licensed merchandise'],
    geography: ['Tennessee', 'nationwide'],
  },
  junior: {
    side: 'junior',
    name: 'VIP Products LLC',
    marks: ['BAD SPANIELS', 'Silly Squeakers'],
    goods: ['durable rubber squeaky chew toys for dogs', 'dog toys'],
    channels: ['pet supply stores', 'online retailers'],
    geography: ['Arizona', 'nationwide'],
  },
  claims: ['likelihood_of_confusion', 'dilution'],
  court_or_forum: 'U.S. District Court for the District of Arizona (on remand, 599 U.S. 140 (2023))',
  summary:
    "Jack Daniel's alleges that VIP's Bad Spaniels dog toy, shaped like its whiskey bottle and carrying a parody label, is likely to confuse consumers and dilutes its marks by tarnishment. VIP contends the toy is an expressive parody that no reasonable buyer would attribute to the distiller.",
  key_quotes: [
    'The Bad Spaniels toy is in the shape of a Jack Daniel\'s bottle and has an imitation label.',
    '"The Old No. 2 on your Tennessee Carpet."',
    '"43% POO BY VOL." and "100% SMELLY."',
  ],
}

const resolution = {
  senior: {
    side: 'senior',
    query: "Jack Daniel's",
    entity_id: JD,
    entity_name: "Jack Daniel's",
    popularity: 0.987,
    candidates_considered: ["Jack Daniel's", "Jack Daniel's Tennessee Honey", "Jack Daniel's Tennessee Fire", "Jack Daniel's Distillery", "Gentleman Jack"],
    disambiguation_note: 'Parent brand chosen over line extensions and the distillery (a place, not a brand).',
  },
  junior: {
    side: 'junior',
    query: 'Bad Spaniels',
    entity_id: null,
    entity_name: null,
    popularity: null,
    candidates_considered: [],
    disambiguation_note: 'No brand entity for "Bad Spaniels" or "VIP Products".',
  },
  senior_proxy: null,
  junior_proxy: {
    side: 'junior',
    goods_phrase: 'dog toys',
    tag_options: [
      { id: TAG_DOGTOY, name: 'Dog Toys', type: 'urn:tag:category' },
      { id: TAG_PET, name: 'Pet Supplies', type: 'urn:tag:category' },
      { id: 'urn:tag:category:qloo:toys_games', name: 'Toys & Games', type: 'urn:tag:category' },
      { id: 'urn:tag:keyword:qloo:dog_toy', name: 'dog toy', type: 'urn:tag:keyword' },
      { id: 'urn:tag:category:qloo:pet_food', name: 'Pet Food', type: 'urn:tag:category' },
      { id: 'urn:tag:genre:qloo:dog_breeds', name: 'Dog Breeds', type: 'urn:tag:genre' },
      { id: 'urn:tag:category:qloo:chew_toys', name: 'Chew Toys', type: 'urn:tag:category' },
      { id: 'urn:tag:keyword:qloo:squeaky', name: 'squeaky', type: 'urn:tag:keyword' },
    ],
    chosen_tag_ids: [TAG_DOGTOY, TAG_PET],
    comparator_brand_ids: comparatorIds,
    comparator_brand_names: comparators,
    rationale:
      'The goods are dog toys; Dog Toys is the exact match and Pet Supplies defines the peer universe. "Toys & Games" targets children and "Dog Breeds" is not a goods category.',
  },
  universes: [
    { side: 'junior', description: 'pet-supply brands', tag_ids: [TAG_PET], size: 300 },
    { side: 'senior', description: 'whiskey brands', tag_ids: [TAG_WHISKEY], size: 120 },
  ],
}

const result = {
  run_id: 'showcase-jack-daniels',
  status: 'finished',
  created_at: new Date(t0).toISOString(),
  mode: 'fixture',
  showcase_slug: 'jack-daniels-v-vip-products',
  input_excerpt:
    "COUNTERCLAIMS. Jack Daniel's Properties, Inc. (\"JDPI\") owns the trademarks JACK DANIEL'S and OLD NO. 7 and the distinctive trade dress of the Jack Daniel's Tennessee whiskey bottle and label. VIP Products LLC markets a dog toy called \"Bad Spaniels\" in the shape of a Jack Daniel's bottle bearing an imitation of its label…",
  extraction,
  routing: {
    analyses: ['overlap', 'bridging', 'fame', 'zone'],
    rationale: {
      overlap: 'Likelihood of confusion pleaded; channels and purchasers factor applies.',
      bridging: 'Confusion pleaded; asks whether whiskey drinkers already lean toward pet goods.',
      fame: 'Dilution by tarnishment pleaded; fame is a threshold element.',
      zone: 'No priority dispute; national heatmap supports the fame analysis only.',
    },
  },
  resolution,
  evidence,
  memo,
  trace,
  error: null,
}

writeFileSync(join(out, 'jack-daniels.json'), JSON.stringify(result, null, 2) + '\n')
console.log(`wrote jack-daniels.json · ${trace.length} events · ${memo.appendix_queries.length} queries · ${points.length}+${junior_points.length} points`)
