/**
 * TypeScript mirror of backend/src/tearose/schemas.py and qloo/models.py.
 * Keep field names identical to the Pydantic models; datetimes arrive as ISO strings.
 */

// ---------------------------------------------------------------- qloo/models.py

export const AGE_BUCKETS = [
  '24_and_younger',
  '25_to_29',
  '30_to_34',
  '35_to_44',
  '45_to_54',
  '55_and_older',
] as const
export type AgeBucket = (typeof AGE_BUCKETS)[number]

export const GENDERS = ['male', 'female'] as const
export type Gender = (typeof GENDERS)[number]

export interface QlooQuery {
  endpoint: string
  params: Record<string, unknown>
  cache_hit: boolean
  status: number | null
  elapsed_ms: number | null
  result_count: number | null
  fixture_file: string | null
}

export interface HeatmapPoint {
  latitude: number
  longitude: number
  geohash?: string | null
  affinity?: number | null
  affinity_rank?: number | null
  popularity?: number | null
  label?: string | null
}

export interface Demographics {
  age: Record<string, number>
  gender: Record<string, number>
}

// ---------------------------------------------------------------- extraction

export type Claim = 'likelihood_of_confusion' | 'dilution' | 'common_law_priority' | 'other'
export type Side = 'senior' | 'junior'

export interface Party {
  side: Side
  name: string
  marks: string[]
  goods: string[]
  channels: string[]
  geography: string[]
}

export type DocumentType =
  | 'complaint'
  | 'cease_and_desist'
  | 'opinion'
  | 'petition'
  | 'notes'
  | 'unknown'

export interface Extraction {
  document_type: DocumentType
  title: string
  senior: Party
  junior: Party
  claims: Claim[]
  court_or_forum: string | null
  summary: string
  key_quotes: string[]
}

// ---------------------------------------------------------------- routing

export type Analysis = 'overlap' | 'bridging' | 'fame' | 'zone'

export interface RoutingDecision {
  analyses: Analysis[]
  rationale: Record<string, string>
}

// ---------------------------------------------------------------- resolution

export interface ResolvedBrand {
  side: Side
  query: string
  entity_id: string | null
  entity_name: string | null
  popularity: number | null
  candidates_considered: string[]
  disambiguation_note: string | null
}

/** One option from the raw /v2/tags menu. Raw API shape, so every key is optional. */
export interface TagOption {
  id?: string
  tag_id?: string
  name?: string
  type?: string
  [k: string]: unknown
}

export interface ProxyResolution {
  side: Side
  goods_phrase: string
  tag_options: TagOption[]
  chosen_tag_ids: string[]
  /** How well the chosen brand-taxonomy category matches the goods. */
  fit?: 'exact' | 'partial' | 'nearest' | null
  /** e.g. "nearest category, no exact match in Qloo's brand taxonomy" */
  fit_note?: string | null
  comparator_brand_ids: string[]
  comparator_brand_names: string[]
  rationale: string
}

export interface Universe {
  side: Side
  description: string
  tag_ids: string[]
  size: number
}

export interface Resolution {
  senior: ResolvedBrand
  junior: ResolvedBrand
  senior_proxy: ProxyResolution | null
  junior_proxy: ProxyResolution | null
  universes: Universe[]
}

// ---------------------------------------------------------------- evidence

export interface RankedPeer {
  entity_id: string
  name: string
  rank: number
  affinity: number | null
}

/**
 * Rows from /v2/analysis/compare (dicts in the schema). Either entity rows (CompareEntity keys)
 * or audience-tag rows {tag_id, name, type, score}: Qloo's compare returns audience traits.
 */
export interface CompareRow {
  tag_id?: string
  type?: string
  score?: number | null
  entity_id?: string
  name?: string
  subtype?: string | null
  a_affinity?: number | null
  b_affinity?: number | null
  delta?: number | null
  [k: string]: unknown
}

export interface OverlapEvidence {
  senior_to_junior_rank: number | null
  senior_to_junior_universe: number | null
  junior_to_senior_rank: number | null
  junior_to_senior_universe: number | null
  symmetric_percentile: number | null
  senior_to_junior_percentile?: number | null
  junior_to_senior_percentile?: number | null
  // harness v2: a rank beyond the scanned depth is censored (rank/percentile null); the
  // affinity ratio = target affinity / affinity of the top-ranked brand (0..1)
  senior_to_junior_censored?: boolean
  senior_to_junior_depth_scanned?: number | null
  senior_to_junior_target_affinity?: number | null
  senior_to_junior_top1_affinity?: number | null
  senior_to_junior_last_scanned_affinity?: number | null
  senior_to_junior_affinity_ratio?: number | null
  junior_to_senior_censored?: boolean
  junior_to_senior_depth_scanned?: number | null
  junior_to_senior_target_affinity?: number | null
  junior_to_senior_top1_affinity?: number | null
  junior_to_senior_last_scanned_affinity?: number | null
  junior_to_senior_affinity_ratio?: number | null
  symmetric_affinity_ratio?: number | null
  top_peers_senior_seed: RankedPeer[]
  top_peers_junior_seed: RankedPeer[]
  shared_affinities: CompareRow[]
  distinct_to_senior: CompareRow[]
  distinct_to_junior: CompareRow[]
  used_proxy: boolean
  notes: string[]
}

export interface BridgingEvidence {
  category_tag_ids: string[]
  category_rank_among_senior_tags: number | null
  senior_tag_universe: number | null
  category_affinity: number | null
  matched_tag_id?: string | null
  matched_tag_name?: string | null
  ancestor_levels?: number
  percentile: number | null
  notes: string[]
}

export interface FameEvidence {
  demographics: Demographics
  breadth_score: number | null
  breadth_age?: number | null
  breadth_gender?: number | null
  skew_description: string
  popularity_percentile: number | null
  heatmap_coverage: number | null
  fame_score?: number | null
  notes: string[]
}

export interface TopRegion {
  label?: string
  share?: number
  [k: string]: unknown
}

export interface ZoneEvidence {
  points: HeatmapPoint[]
  concentration_index: number | null
  top_regions: TopRegion[]
  junior_points: HeatmapPoint[]
  geographic_overlap: number | null
  notes: string[]
}

export interface Evidence {
  overlap: OverlapEvidence | null
  bridging: BridgingEvidence | null
  fame: FameEvidence | null
  zone: ZoneEvidence | null
}

// ---------------------------------------------------------------- memo

export type FactorLean = 'favors_senior' | 'neutral' | 'favors_junior' | 'insufficient_data'
export type Confidence = 'high' | 'medium' | 'low'

export interface FactorFinding {
  factor: string
  lean: FactorLean
  confidence: Confidence
  finding: string
  evidence_refs: string[]
}

export interface MemoSection {
  id: string
  title: string
  markdown: string
}

export interface Memo {
  headline: string
  /** Computed in code from the factor leans, never by the model. "" on runs stored before it existed. */
  bottom_line: string
  findings: FactorFinding[]
  sections: MemoSection[]
  limitations: string[]
  appendix_queries: QlooQuery[]
}

// ---------------------------------------------------------------- trace

export type EventType =
  | 'run_started'
  | 'node_started'
  | 'node_finished'
  | 'tool_call'
  | 'tool_result'
  | 'decision'
  | 'note'
  | 'warning'
  | 'run_finished'
  | 'run_failed'

export const EVENT_TYPES: readonly EventType[] = [
  'run_started',
  'node_started',
  'node_finished',
  'tool_call',
  'tool_result',
  'decision',
  'note',
  'warning',
  'run_finished',
  'run_failed',
]

export type NodeName =
  | 'extract'
  | 'route'
  | 'resolve'
  | 'fetch'
  | 'score'
  | 'interpret'
  | 'memo'
  | 'followup'

export const PIPELINE: readonly NodeName[] = [
  'extract',
  'route',
  'resolve',
  'fetch',
  'score',
  'interpret',
  'memo',
]

export interface TraceEvent {
  ts: string
  seq: number
  node: string
  type: EventType
  title: string
  detail: string | null
  data: Record<string, unknown>
}

// ---------------------------------------------------------------- result

export type RunStatus = 'queued' | 'running' | 'finished' | 'failed'

export interface AnalysisResult {
  run_id: string
  status: RunStatus
  created_at: string
  mode: 'fixture' | 'live'
  showcase_slug: string | null
  input_excerpt: string
  extraction: Extraction | null
  routing: RoutingDecision | null
  resolution: Resolution | null
  evidence: Evidence | null
  memo: Memo | null
  trace: TraceEvent[]
  error: string | null
}

export interface ShowcaseSummary {
  slug: string
  title: string
  parties: string
  year: number | null
  one_liner: string
  tags: string[]
}

// ---------------------------------------------------------------- API envelopes (docs/ARCHITECTURE.md)

export interface AuthMe {
  authenticated: boolean
  runs_left_today: number | null
  runs_left_session: number | null
}

export interface Limits {
  daily_cap: number | null
  daily_used: number | null
  session_cap: number | null
  live_mode_enabled: boolean
}

/** Final SSE message (`event: done`). */
export interface StreamDone {
  status: RunStatus
  error: string | null
}

export interface RunCreated {
  run_id: string
}

export interface SampleRef {
  name: string
  title?: string
  bytes?: number
}
