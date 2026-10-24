"""Normalized Qloo data types.

The raw API shapes are only partially documented and will be confirmed against the live
API on Monday. Everything downstream (scoring, agent, UI) depends on THESE types, never on
raw JSON, so a shape change on Monday is absorbed in `parse.py` alone.

Affinity semantics (from the docs): 0..1 (sometimes 0..100), normalized PER QUERY. Compare
ranks within one response; never compare raw affinities across responses.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

AGE_BUCKETS: tuple[str, ...] = (
    "24_and_younger",
    "25_to_29",
    "30_to_34",
    "35_to_44",
    "45_to_54",
    "55_and_older",
)
GENDERS: tuple[str, ...] = ("male", "female")


class QlooQuery(BaseModel):
    """Provenance record for one API call. Every number in a memo traces back to one of these."""

    id: str | None = None  # "q7": stable reference used by evidence_refs and trace events
    endpoint: str
    params: dict[str, Any]
    cache_hit: bool = False
    status: int | None = None
    elapsed_ms: int | None = None
    result_count: int | None = None
    fixture_file: str | None = None  # set when served from fixtures

    def url(self, base_url: str) -> str:
        from urllib.parse import urlencode

        return f"{base_url.rstrip('/')}{self.endpoint}?{urlencode(sorted(self.params.items()))}"


class Entity(BaseModel):
    entity_id: str
    name: str
    subtype: str | None = None  # e.g. "urn:entity:brand"
    popularity: float | None = None  # percentile 0..1 when provided
    affinity: float | None = None  # query.affinity for this result, normalized per query
    rank: int | None = None  # 1-based position in the response list
    explainability: dict[str, float] = Field(default_factory=dict)  # seed entity_id -> share
    tags: list[str] = Field(default_factory=list)  # tag ids attached to the entity
    properties: dict[str, Any] = Field(default_factory=dict)
    disambiguation: str | None = None

    @property
    def is_brand(self) -> bool:
        return (self.subtype or "").endswith("brand")


class Tag(BaseModel):
    tag_id: str
    name: str
    tag_type: str | None = None  # e.g. "urn:tag:category:brand" (UNVERIFIED naming)
    affinity: float | None = None
    rank: int | None = None


class HeatmapPoint(BaseModel):
    latitude: float
    longitude: float
    geohash: str | None = None
    affinity: float | None = None
    affinity_rank: float | None = None
    popularity: float | None = None
    label: str | None = None  # city/neighborhood name when a boundary is requested


class Demographics(BaseModel):
    """Age and gender affinity for one seed set. Values roughly -1..+1 (over/under-index)."""

    age: dict[str, float] = Field(default_factory=dict)
    gender: dict[str, float] = Field(default_factory=dict)

    def age_vector(self) -> list[float]:
        return [self.age.get(b, 0.0) for b in AGE_BUCKETS]

    def gender_vector(self) -> list[float]:
        return [self.gender.get(g, 0.0) for g in GENDERS]


class CompareEntity(BaseModel):
    entity_id: str
    name: str
    subtype: str | None = None
    a_affinity: float | None = None
    b_affinity: float | None = None
    delta: float | None = None  # a - b when both present


class CompareResult(BaseModel):
    """Output of /v2/analysis/compare: how two seed groups differ in taste."""

    entities: list[CompareEntity] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)

    def shared(self, top_n: int = 10) -> list[CompareEntity]:
        both = [e for e in self.entities if e.a_affinity is not None and e.b_affinity is not None]
        both.sort(key=lambda e: min(e.a_affinity or 0, e.b_affinity or 0), reverse=True)
        return both[:top_n]

    def distinct_to_a(self, top_n: int = 10) -> list[CompareEntity]:
        xs = [e for e in self.entities if e.delta is not None]
        xs.sort(key=lambda e: e.delta or 0, reverse=True)
        return xs[:top_n]

    def distinct_to_b(self, top_n: int = 10) -> list[CompareEntity]:
        xs = [e for e in self.entities if e.delta is not None]
        xs.sort(key=lambda e: e.delta or 0)
        return xs[:top_n]


class QlooResponse[T](BaseModel):
    """A parsed result together with the query that produced it."""

    query: QlooQuery
    data: T
