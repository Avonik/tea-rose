"""Build the exact query-string parameters for each Qloo request.

Shared by LiveClient (sends them) and FixtureClient (records them as provenance), so the
QlooQuery stored in a memo is identical regardless of mode.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _csv(xs: Sequence[str] | None) -> str | None:
    return ",".join(xs) if xs else None


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None and v != "" and v is not False}


def search_params(query: str, types: str, take: int) -> dict[str, Any]:
    return _clean({"query": query, "types": types, "take": take})


def insights_entities_params(
    seed_entity_ids: list[str],
    result_type: str,
    filter_tags: list[str] | None,
    exclude_entity_ids: list[str] | None,
    signal_location_query: str | None,
    take: int,
    page: int,
    explainability: bool,
) -> dict[str, Any]:
    return _clean(
        {
            "filter.type": result_type,
            "signal.interests.entities": _csv(seed_entity_ids),
            "filter.tags": _csv(filter_tags),
            "filter.exclude.entities": _csv(exclude_entity_ids),
            "signal.location.query": signal_location_query,
            "take": take,
            "page": page if page > 1 else None,
            "feature.explainability": "true" if explainability else None,
        }
    )


def insights_tags_params(
    seed_entity_ids: list[str], take: int, tag_types: Sequence[str] | None = None
) -> dict[str, Any]:
    """Unrestricted taste tags are mostly noise; `filter.tag.types=urn:tag:genre:brand` turns
    them into a clean category list (live spike)."""
    return _clean(
        {
            "filter.type": "urn:tag",
            "filter.tag.types": _csv(tag_types),
            "signal.interests.entities": _csv(seed_entity_ids),
            "take": take,
        }
    )


def demographics_params(seed_entity_ids: list[str]) -> dict[str, Any]:
    return _clean(
        {"filter.type": "urn:demographics", "signal.interests.entities": _csv(seed_entity_ids)}
    )


def heatmap_params(
    seed_entity_ids: list[str], location_query: str | None, boundary: str | None, take: int
) -> dict[str, Any]:
    return _clean(
        {
            "filter.type": "urn:heatmap",
            "signal.interests.entities": _csv(seed_entity_ids),
            "filter.location.query": location_query,
            "output.heatmap.boundary": boundary,
            "take": take,
        }
    )


def tags_search_params(query: str, tag_types: Sequence[str] | None, take: int) -> dict[str, Any]:
    return _clean({"filter.query": query, "filter.tag.types": _csv(tag_types), "take": take})


def compare_params(a_ids: list[str], b_ids: list[str], take: int) -> dict[str, Any]:
    return _clean(
        {
            "a.signal.interests.entities": _csv(a_ids),
            "b.signal.interests.entities": _csv(b_ids),
            "take": take,
        }
    )
