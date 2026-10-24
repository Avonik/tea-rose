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
    document_type: Literal[
        "complaint", "cease_and_desist", "opinion", "petition", "notes", "unknown"
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
    """Used when a party's brand is not in Qloo. The goods phrase goes to /v2/tags verbatim;
    the agent may only pick among the returned tags, and every option is recorded."""

    side: Side
    goods_phrase: str
    tag_options: list[dict[str, Any]]  # the raw menu returned by /v2/tags (id, name, type)
    chosen_tag_ids: list[str]
    comparator_brand_ids: list[str] = Field(default_factory=list)  # category-leading brands
    comparator_brand_names: list[str] = Field(default_factory=list)
    rationale: str


class Universe(BaseModel):
    """The comparison set that makes a rank meaningful."""

    side: Side  # whose peers these are
    description: str  # "pet-supply brands" / "whiskey brands"
    tag_ids: list[str]
    size: int


class Resolution(BaseModel):
    senior: ResolvedBrand
    junior: ResolvedBrand
    senior_proxy: ProxyResolution | None = None
    junior_proxy: ProxyResolution | None = None
    universes: list[Universe] = Field(default_factory=list)


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
    notes: list[str] = Field(default_factory=list)


class FameEvidence(BaseModel):
    demographics: Demographics
    breadth_score: float | None  # 0..1, see ARCHITECTURE.md "Fame breadth"
    skew_description: str  # e.g. "skews 25-34, male"
    popularity_percentile: float | None
    heatmap_coverage: float | None  # 0..1 share of national cells with above-median affinity
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


class FactorFinding(BaseModel):
    # relatedness_of_goods | channels_and_purchasers | bridging_the_gap | fame | zone_of_reputation
    factor: str
    lean: FactorLean
    confidence: Literal["high", "medium", "low"]
    finding: str  # 2-4 sentences in lawyer language
    evidence_refs: list[str] = Field(default_factory=list)  # query ids / evidence field names


class MemoSection(BaseModel):
    id: str
    title: str
    markdown: str


class Memo(BaseModel):
    headline: str  # one sentence
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
    node: str  # extract | route | resolve | fetch | score | interpret | memo | followup
    type: EventType
    title: str  # one line for the UI
    detail: str | None = None  # optional second line
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
