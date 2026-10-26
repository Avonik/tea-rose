"""Shared result and event schemas: the contract between agent, scoring, API and frontend.

Everything the UI renders is one AnalysisResult. Everything the live trace shows is a stream
of TraceEvent. Keep these stable; the frontend is generated from them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from tearose.qloo.models import Demographics, HeatmapPoint, QlooQuery

# --------------------------------------------------------------------------------------
# Intake / extraction
# --------------------------------------------------------------------------------------

Claim = Literal["likelihood_of_confusion", "dilution", "common_law_priority", "other"]
Side = Literal["senior", "junior"]


class Party(BaseModel):
    side: Side
    name: str  # party or company name as written in the document
    marks: list[str] = Field(default_factory=list)  # the word marks at issue
    goods: list[str] = Field(default_factory=list)  # goods/services phrases, verbatim
    channels: list[str] = Field(default_factory=list)  # trade channels mentioned, verbatim
    geography: list[str] = Field(default_factory=list)  # states/regions mentioned


class Extraction(BaseModel):
    # "pleadings" is set in code (extract.py) when the input bundles the complaint with the
    # defendant's answer or motion ("===== DOCUMENT 2" banner); the model never picks it.
    document_type: Literal[
        "complaint", "pleadings", "cease_and_desist", "opinion", "petition", "notes", "unknown"
    ]
    title: str
    senior: Party
    junior: Party
    claims: list[Claim]
    court_or_forum: str | None = None
    summary: str  # 2-3 sentences, neutral
    key_quotes: list[str] = Field(default_factory=list)  # verbatim passages that drove extraction


# --------------------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------------------

Analysis = Literal["overlap", "bridging", "fame", "zone"]


class RoutingDecision(BaseModel):
    analyses: list[Analysis]
    rationale: dict[str, str]  # analysis -> one sentence why it is (not) run
    # analyses run only because a full-coverage run forced them (analyses_override), not
    # because the pleading calls for them: context, not a live factor
    context_only: list[Analysis] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Entity resolution (incl. proxy path)
# --------------------------------------------------------------------------------------


class ResolvedBrand(BaseModel):
    side: Side
    query: str  # what we searched for
    entity_id: str | None = None  # None when the brand is not in Qloo
    entity_name: str | None = None
    popularity: float | None = None
    candidates_considered: list[str] = Field(default_factory=list)  # names from /search
    disambiguation_note: str | None = None


class ProxyResolution(BaseModel):
    """Used when a party's brand is not in Qloo. The goods phrase is mapped onto Qloo's brand
    taxonomy (urn:tag:genre:brand); the agent may only pick taxonomy nodes (or, as a last
    resort, tags a free-text /v2/tags lookup returned), and every option is recorded.

    `fit` says how well the chosen category matches the goods: "exact", "partial", or
    "nearest" (no exact match in Qloo's brand taxonomy; the category is an approximation)."""

    side: Side
    goods_phrase: str
    tag_options: list[dict[str, Any]]  # menu shown/considered (id, name, type|path, fit)
    chosen_tag_ids: list[str]
    fit: Literal["exact", "partial", "nearest"] | None = None
    fit_note: str | None = None  # e.g. "nearest category, no exact match in Qloo's ..."
    comparator_brand_ids: list[str] = Field(default_factory=list)  # category-leading brands
    comparator_brand_names: list[str] = Field(default_factory=list)
    # who picked the stand-ins from the code-built shortlist: the model ("agent"), the model
    # topped up by code by popularity ("mixed", fewer than 2 valid picks), or code alone
    # ("rule", the model returned nothing usable)
    comparator_source: Literal["agent", "rule", "mixed"] | None = None
    # the shortlist the agent picked from (up to 10 brands of the chosen category seeded by the
    # other side, opponent removed by code): entity_id, name, popularity, description, ...
    stand_in_candidates: list[dict[str, Any]] = Field(default_factory=list)
    comparator_rationale: str | None = None  # the agent's one-sentence reason for its picks
    # the agent's call whether the stand-in category is close enough to compare audiences at
    # all; False skips the overlap analysis for the run (bridging and fame still run)
    measure_overlap: bool = True
    fit_reason: str | None = None  # why (not); carried verbatim into the limitations
    rationale: str


class Universe(BaseModel):
    """The comparison set that makes a rank meaningful."""

    side: Side  # whose peers these are
    description: str  # "pet-supply brands" / "whiskey brands"
    tag_ids: list[str]
    size: int  # informational: planned depth (3 pages × 50) or the real count once exhausted;
    # scoring takes the authoritative size from DirectionalPeers


class Resolution(BaseModel):
    senior: ResolvedBrand
    junior: ResolvedBrand
    senior_proxy: ProxyResolution | None = None
    junior_proxy: ProxyResolution | None = None
    universes: list[Universe] = Field(default_factory=list)

    def overlap_blocked(self) -> list[ProxyResolution]:
        """Proxied sides whose stand-in category the agent judged too far to measure audience
        overlap (measure_overlap False): the overlap analysis is skipped for the run."""
        return [
            p
            for p, b in ((self.senior_proxy, self.senior), (self.junior_proxy, self.junior))
            if p is not None and not b.entity_id and not p.measure_overlap
        ]


# --------------------------------------------------------------------------------------
# Evidence (outputs of score.py — deterministic, no model in the path)
# --------------------------------------------------------------------------------------


class RankedPeer(BaseModel):
    entity_id: str
    name: str
    rank: int
    affinity: float | None


class OverlapEvidence(BaseModel):
    """Shared-purchaser evidence. Rank-based because Qloo normalizes affinity per query."""

    senior_to_junior_rank: int | None  # junior's rank among junior's peers when seeded by senior
    senior_to_junior_universe: int | None
    senior_to_junior_percentile: float | None = None  # 0..1, 1 = strongest overlap
    junior_to_senior_rank: int | None
    junior_to_senior_universe: int | None
    junior_to_senior_percentile: float | None = None
    symmetric_percentile: float | None  # 0..1, 1 = strongest overlap; mean of both directions
    # --- harness v2: censoring + direct target affinity (defaults keep old runs loadable) ---
    # a target beyond the scanned depth has rank/percentile None and censored=True; the
    # affinity_ratio = target affinity / affinity of the top-ranked brand (0..1) is always
    # available when the direct lookup succeeds. For proxied sides: mean over comparators.
    senior_to_junior_censored: bool = False
    senior_to_junior_depth_scanned: int | None = None
    senior_to_junior_target_affinity: float | None = None
    senior_to_junior_top1_affinity: float | None = None
    senior_to_junior_last_scanned_affinity: float | None = None
    senior_to_junior_affinity_ratio: float | None = None
    junior_to_senior_censored: bool = False
    junior_to_senior_depth_scanned: int | None = None
    junior_to_senior_target_affinity: float | None = None
    junior_to_senior_top1_affinity: float | None = None
    junior_to_senior_last_scanned_affinity: float | None = None
    junior_to_senior_affinity_ratio: float | None = None
    symmetric_affinity_ratio: float | None = None  # mean of the available direction ratios
    top_peers_senior_seed: list[RankedPeer] = Field(default_factory=list)
    top_peers_junior_seed: list[RankedPeer] = Field(default_factory=list)
    shared_affinities: list[dict[str, Any]] = Field(default_factory=list)  # from compare
    distinct_to_senior: list[dict[str, Any]] = Field(default_factory=list)
    distinct_to_junior: list[dict[str, Any]] = Field(default_factory=list)
    used_proxy: bool = False
    notes: list[str] = Field(default_factory=list)


class BridgingEvidence(BaseModel):
    """Does the senior brand's audience already lean toward the junior's product category?"""

    category_tag_ids: list[str]
    category_rank_among_senior_tags: int | None  # where the junior's category tag ranks in the
    senior_tag_universe: int | None  # senior brand's taste-tag list
    category_affinity: float | None
    percentile: float | None  # 0..1
    # the tag actually found: the junior's leaf, or (when the leaf is absent) its nearest
    # taxonomy ancestor among the senior's tags; ancestor_levels = segments climbed (0 = leaf)
    matched_tag_id: str | None = None
    matched_tag_name: str | None = None
    ancestor_levels: int = 0
    notes: list[str] = Field(default_factory=list)


class FameEvidence(BaseModel):
    demographics: Demographics
    breadth_score: float | None  # 0..1 evenness, see ARCHITECTURE.md "Fame breadth"
    breadth_age: float | None = None  # same evenness over the 6 age buckets only
    breadth_gender: float | None = None  # same evenness over the 2 gender values only
    skew_description: str  # e.g. "skews 25-34, male"
    popularity_percentile: float | None
    heatmap_coverage: float | None  # 0..1 share of national cells with above-median affinity
    fame_score: float | None = None  # mean(breadth, popularity, coverage); None unless all 3
    notes: list[str] = Field(default_factory=list)


class ZoneEvidence(BaseModel):
    points: list[HeatmapPoint]
    concentration_index: float | None  # 0..1, Gini-like: 1 = all affinity in few cells
    # [{"label", "share"}]; label falls back to a "lat, lon" bin string
    top_regions: list[dict[str, Any]] = Field(default_factory=list)
    junior_points: list[HeatmapPoint] = Field(default_factory=list)
    geographic_overlap: float | None = None  # 0..1 when both sides have maps
    notes: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    overlap: OverlapEvidence | None = None
    bridging: BridgingEvidence | None = None
    fame: FameEvidence | None = None
    zone: ZoneEvidence | None = None


# --------------------------------------------------------------------------------------
# Interpretation + memo
# --------------------------------------------------------------------------------------

FactorLean = Literal["favors_senior", "neutral", "favors_junior", "insufficient_data"]
Confidence = Literal["high", "medium", "low"]


class FactorFinding(BaseModel):
    # relatedness_of_goods | channels_and_purchasers | bridging_the_gap | fame | zone_of_reputation
    factor: str
    lean: FactorLean
    confidence: Confidence
    finding: str  # 2-4 sentences in lawyer language
    evidence_refs: list[str] = Field(default_factory=list)  # query ids / evidence field names


class MemoSection(BaseModel):
    id: str
    title: str
    markdown: str


# The factors taste data cannot see, read from the document by the `assess` node
READ_FACTORS: tuple[str, ...] = (
    "similarity_of_marks",
    "intent",
    "actual_confusion",
    "buyer_care",
    "protectability",  # registration, distinctiveness, secondary meaning, functionality
    "mark_strength",  # conceptual and commercial strength of the asserted mark
    "defences",
    "other",
)
NOT_A_PREDICTION = (
    "A preliminary read on the pleading and the audience data, not a prediction or a "
    "probability; a court weighs the factors, it does not count them."
)
ReadLean = Literal["older_brand", "newcomer", "too_close_to_call"]


class ReadFactor(BaseModel):
    """One factor the taste data cannot see, assessed from the document alone."""

    # similarity_of_marks | intent | actual_confusion | buyer_care | protectability |
    # mark_strength | defences | other
    factor: str
    lean: FactorLean
    confidence: Confidence
    basis: Literal["document", "data"]
    # 1-2 sentences with a short quote or cite of the supporting passage; "Not alleged." when
    # the document is silent. defences: name the defence (parody, expressive use, fair use, ...)
    finding: str


class PreliminaryRead(BaseModel):
    """How a court would likely come out, read from the pleading plus the data-backed findings.
    Never a prediction or a probability (see NOT_A_PREDICTION)."""

    lean: ReadLean  # older_brand = the senior mark's side; newcomer = the junior user's side
    confidence: Confidence
    turns_on: str  # one sentence: what the case most likely turns on
    rationale: str  # 3-6 sentences; the data half and the reading half clearly separated
    flip_risks: list[str] = Field(default_factory=list)  # one sentence each: what could flip it
    # 1-2 sentences: the strongest defence the facts allow, even if none has been filed, and
    # (when an answer/counterclaim is in the record) the document it comes from. "" = older runs
    best_defence: str = ""
    # True when the input is only the plaintiff's pleading (no answer, counterclaim or
    # defendant statement): confidence is capped at low and the rationale says so in code.
    # Default False only so runs stored before the field existed load unchanged.
    one_sided_input: bool = False
    read_factors: list[ReadFactor] = Field(default_factory=list)
    data_factors_used: list[str] = Field(default_factory=list)  # factor ids of interpret findings
    not_a_prediction: str = NOT_A_PREDICTION  # fixed; code resets it


class Memo(BaseModel):
    headline: str  # one sentence
    # Computed in code from the factor leans (scoring/bottom_line.py), never by the model.
    # Default "" only so runs stored before the field existed still load.
    bottom_line: str = ""
    # One sentence computed in code from `preliminary_read` (scoring/read_line.py); "" when
    # there is no read (older runs, or the assess step failed).
    read_line: str = ""
    preliminary_read: PreliminaryRead | None = None
    findings: list[FactorFinding]
    sections: list[MemoSection]
    limitations: list[str]  # the fixed "what this cannot tell you" plus case-specific items
    appendix_queries: list[QlooQuery]


# --------------------------------------------------------------------------------------
# Trace events (streamed over SSE while the agent runs)
# --------------------------------------------------------------------------------------

EventType = Literal[
    "run_started",
    "node_started",
    "node_finished",
    "tool_call",
    "tool_result",
    "decision",
    "note",
    "warning",
    "run_finished",
    "run_failed",
]


class TraceEvent(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    seq: int = 0
    node: str  # extract | route | resolve | fetch | score | interpret | assess | memo | followup
    type: EventType
    title: str  # one line for the UI
    detail: str | None = None  # optional second line
    ref: str | None = None  # query id ("q7") for tool events, links to the appendix row
    data: dict[str, Any] = Field(default_factory=dict)  # e.g. the QlooQuery, counts, choices


# --------------------------------------------------------------------------------------
# The result
# --------------------------------------------------------------------------------------

RunStatus = Literal["queued", "running", "finished", "failed"]


class AnalysisResult(BaseModel):
    run_id: str
    status: RunStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: Literal["fixture", "live"]
    showcase_slug: str | None = None
    input_excerpt: str  # first ~600 chars of the input, for display
    extraction: Extraction | None = None
    routing: RoutingDecision | None = None
    resolution: Resolution | None = None
    evidence: Evidence | None = None
    memo: Memo | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    error: str | None = None


class ShowcaseSummary(BaseModel):
    slug: str
    title: str
    parties: str  # "Jack Daniel's v. VIP Products"
    year: int | None = None
    one_liner: str  # the headline finding
    tags: list[str] = Field(default_factory=list)  # e.g. ["parody", "dilution", "proxy path"]
    read_line: str = ""  # the memo's computed preliminary-read sentence
