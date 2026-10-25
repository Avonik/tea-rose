"""The QlooClient protocol: the only surface the rest of the app talks to.

Two implementations: FixtureClient (today) and LiveClient (from Monday). Both return
(parsed data, QlooQuery provenance) pairs so every number in a memo can cite its query.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from tearose.qloo.models import (
    CompareResult,
    Demographics,
    Entity,
    HeatmapPoint,
    QlooQuery,
    Tag,
)

BRAND = "urn:entity:brand"
HEATMAP = "urn:heatmap"
DEMOGRAPHICS = "urn:demographics"
TAG = "urn:tag"
GENRE_BRAND = "urn:tag:genre:brand"  # the brand-category taxonomy (~177 nodes, 27 families)
DEFAULT_INSIGHTS_TAG_TYPES: tuple[str, ...] = (GENRE_BRAND,)
INSIGHTS_MAX_TAKE = 50


@runtime_checkable
class QlooClient(Protocol):
    async def search(
        self, query: str, *, types: str = BRAND, take: int = 10
    ) -> tuple[list[Entity], QlooQuery]:
        """GET /search — resolve a name to candidate entities."""

    async def insights_entities(
        self,
        seed_entity_ids: list[str],
        *,
        result_type: str = BRAND,
        filter_tags: list[str] | None = None,
        exclude_entity_ids: list[str] | None = None,
        signal_location_query: str | None = None,
        take: int = INSIGHTS_MAX_TAKE,
        page: int = 1,
        explainability: bool = True,
    ) -> tuple[list[Entity], QlooQuery]:
        """GET /v2/insights filter.type=<entity type> — ranked entities for a seed set."""

    async def insights_tags(
        self,
        seed_entity_ids: list[str],
        *,
        take: int = INSIGHTS_MAX_TAKE,
        tag_types: Sequence[str] | None = DEFAULT_INSIGHTS_TAG_TYPES,
    ) -> tuple[list[Tag], QlooQuery]:
        """GET /v2/insights filter.type=urn:tag — taste tags describing a seed set.
        `tag_types` -> filter.tag.types (default: brand genres only; None = unrestricted)."""

    async def demographics(self, seed_entity_ids: list[str]) -> tuple[Demographics, QlooQuery]:
        """GET /v2/insights filter.type=urn:demographics — age/gender affinity."""

    async def heatmap(
        self,
        seed_entity_ids: list[str],
        *,
        location_query: str | None = None,
        boundary: str | None = None,
        take: int = INSIGHTS_MAX_TAKE,
    ) -> tuple[list[HeatmapPoint], QlooQuery]:
        """GET /v2/insights filter.type=urn:heatmap — geographic affinity."""

    async def tags_search(
        self, query: str, *, tag_types: Sequence[str] | None = None, take: int = 20
    ) -> tuple[list[Tag], QlooQuery]:
        """GET /v2/tags — find tag ids for a free-text category phrase."""

    async def compare(
        self, a_entity_ids: list[str], b_entity_ids: list[str], *, take: int = INSIGHTS_MAX_TAKE
    ) -> tuple[CompareResult, QlooQuery]:
        """GET /v2/analysis/compare — how two seed groups differ."""

    async def raw(self, endpoint: str, params: dict[str, Any]) -> tuple[dict[str, Any], QlooQuery]:
        """Escape hatch for the live spike and debugging. Returns unparsed JSON."""

    async def aclose(self) -> None: ...


def get_qloo_client() -> QlooClient:
    """Factory chosen by settings.qloo_mode."""
    from tearose.config import get_settings

    s = get_settings()
    if s.qloo_mode == "live":
        from tearose.qloo.live import LiveClient

        return LiveClient(s)
    from tearose.qloo.fixtures import FixtureClient

    return FixtureClient(s.fixtures_dir)
