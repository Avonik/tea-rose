"""RawData: the bundle of normalized Qloo results the agent's fetch loop hands to scoring.

The fetch node fills whatever the routing asked for; everything is optional so scoring stays
total (missing input ⇒ None evidence fields + a note, never an exception).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from tearose.qloo.models import CompareResult, Demographics, Entity, HeatmapPoint, Tag


class DirectionalPeers(BaseModel):
    """Brands returned when seeding with `seed_entity_ids` and filtering to `universe_tag_ids`.
    Pages are concatenated in order; `rank` on each Entity is its 1-based position overall."""

    seed_entity_ids: list[str]
    universe_tag_ids: list[str]
    universe_description: str
    entities: list[Entity] = Field(default_factory=list)
    pages_fetched: int = 0
    exhausted: bool = False  # True when the API returned fewer than `take` on the last page
    gave_up: bool = False  # True when results stayed empty after the widened-filter retry
    filter_tag_ids_used: list[str] = Field(default_factory=list)  # actual filter after widening


class RawData(BaseModel):
    # --- overlap (both directions) -------------------------------------------------
    senior_seed_junior_universe: DirectionalPeers | None = None
    junior_seed_senior_universe: DirectionalPeers | None = None
    junior_target_entity_ids: list[str] = Field(default_factory=list)  # junior id, or comparators
    senior_target_entity_ids: list[str] = Field(default_factory=list)  # senior id, or comparators
    compare: CompareResult | None = None

    # --- bridging -------------------------------------------------------------------
    senior_tags: list[Tag] = Field(default_factory=list)  # taste tags for the senior seed
    junior_category_tag_ids: list[str] = Field(default_factory=list)

    # --- fame -----------------------------------------------------------------------
    senior_demographics: Demographics | None = None
    junior_demographics: Demographics | None = None
    senior_popularity: float | None = None
    junior_popularity: float | None = None
    senior_heatmap_national: list[HeatmapPoint] = Field(default_factory=list)

    # --- zone -----------------------------------------------------------------------
    senior_heatmap: list[HeatmapPoint] = Field(default_factory=list)
    junior_heatmap: list[HeatmapPoint] = Field(default_factory=list)

    # --- bookkeeping ----------------------------------------------------------------
    used_proxy_senior: bool = False
    used_proxy_junior: bool = False
    notes: list[str] = Field(default_factory=list)  # give-ups, retries, thin-data remarks
