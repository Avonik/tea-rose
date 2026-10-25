"""FixtureClient: serves doc-shaped synthetic JSON from backend/fixtures/qloo/.

Routing is by scenario slug, not by exact params, so the agent can be exercised end to end
without a key. Unknown requests return an empty result (which is also what the live API does
for unknown entities), so the agent's "thin data" paths get exercised too.

Fixture file naming (see fixtures/qloo/README.md):
  search_brand_<slug>.json                   search_<type>_<slug>.json (e.g. search_artist_aqua)
  insights_brand_seed_<slug>.json            insights_brand_seed_<slug>_filter_<tagslug>.json
  insights_tag_seed_<slug>.json
  insights_demographics_<slug>.json
  insights_heatmap_<slug>.json
  tags_search_<slug>.json
  compare_<slugA>_vs_<slugB>.json
  empty_results.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tearose.qloo import params as P
from tearose.qloo.client import BRAND, INSIGHTS_MAX_TAKE
from tearose.qloo.models import (
    CompareResult,
    Demographics,
    Entity,
    HeatmapPoint,
    QlooQuery,
    Tag,
)
from tearose.qloo.parse import (
    parse_compare,
    parse_demographics,
    parse_entities,
    parse_heatmap,
    parse_search,
    parse_tags,
)


def slugify(text: str) -> str:
    s = text.lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


class FixtureClient:
    def __init__(self, fixtures_dir: Path) -> None:
        self._dir = fixtures_dir
        self._id_to_slug: dict[str, str] = {}
        self._index_ids()

    # --- helpers --------------------------------------------------------------------

    def _index_ids(self) -> None:
        """Map synthetic entity ids to slugs by reading every search fixture."""
        for f in sorted(self._dir.glob("search_*.json")):
            kind = f.stem.removeprefix("search_").split("_", 1)[0]
            slug = f.stem.removeprefix(f"search_{kind}_")
            try:
                for e in parse_search(self._load(f)):
                    self._id_to_slug.setdefault(e.entity_id, slug)
            except Exception:  # noqa: BLE001 — a broken fixture must not kill startup
                continue

    def _load(self, path: Path) -> dict[str, Any]:
        body = json.loads(path.read_text(encoding="utf-8"))
        body.pop("_fixture", None)
        return body

    def _find(self, *candidates: str) -> tuple[dict[str, Any], str]:
        for name in candidates:
            p = self._dir / f"{name}.json"
            if p.exists():
                return self._load(p), p.name
        empty = self._dir / "empty_results.json"
        if empty.exists():
            return self._load(empty), empty.name
        return {"success": True, "results": {"entities": []}}, "<builtin-empty>"

    def _seed_slug(self, seed_entity_ids: list[str]) -> str:
        slugs = [self._id_to_slug.get(i, slugify(i)) for i in seed_entity_ids]
        return "_and_".join(slugs)

    def _query(self, endpoint: str, params: dict[str, Any], fixture: str, n: int) -> QlooQuery:
        return QlooQuery(
            endpoint=endpoint, params=params, status=200, fixture_file=fixture, result_count=n
        )

    # --- QlooClient protocol ----------------------------------------------------------

    async def search(self, query: str, *, types: str = BRAND, take: int = 10):
        params = P.search_params(query, types, take)
        kind = types.rsplit(":", 1)[-1]  # urn:entity:artist -> search_artist_<slug>.json
        body, fx = self._find(f"search_{kind}_{slugify(query)}")
        ents = parse_search(body)[:take]
        return ents, self._query("/search", params, fx, len(ents))

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
        params = P.insights_entities_params(
            seed_entity_ids,
            result_type,
            filter_tags,
            exclude_entity_ids,
            signal_location_query,
            take,
            page,
            explainability,
        )
        seed = self._seed_slug(seed_entity_ids)
        kind = result_type.rsplit(":", 1)[-1]
        candidates: list[str] = []
        if filter_tags:
            # Any pet-ish tag routes to the pet fixture; otherwise try the first tag's slug.
            tag_blob = " ".join(filter_tags).lower()
            if any(w in tag_blob for w in ("pet", "dog", "animal")):
                candidates.append(f"insights_{kind}_seed_{seed}_filter_pet_tags")
            candidates.append(f"insights_{kind}_seed_{seed}_filter_{slugify(filter_tags[0])}")
        candidates.append(f"insights_{kind}_seed_{seed}")
        body, fx = self._find(*candidates)
        ents = parse_entities(body)
        if exclude_entity_ids:
            ents = [e for e in ents if e.entity_id not in set(exclude_entity_ids)]
        start = (page - 1) * take
        page_ents = ents[start : start + take]
        return page_ents, self._query("/v2/insights", params, fx, len(page_ents))

    async def insights_tags(
        self, seed_entity_ids: list[str], *, take: int = INSIGHTS_MAX_TAKE
    ) -> tuple[list[Tag], QlooQuery]:
        params = P.insights_tags_params(seed_entity_ids, take)
        body, fx = self._find(f"insights_tag_seed_{self._seed_slug(seed_entity_ids)}")
        tags = parse_tags(body)[:take]
        return tags, self._query("/v2/insights", params, fx, len(tags))

    async def demographics(self, seed_entity_ids: list[str]) -> tuple[Demographics, QlooQuery]:
        params = P.demographics_params(seed_entity_ids)
        body, fx = self._find(f"insights_demographics_{self._seed_slug(seed_entity_ids)}")
        d = parse_demographics(body)
        return d, self._query("/v2/insights", params, fx, len(d.age) + len(d.gender))

    async def heatmap(
        self,
        seed_entity_ids: list[str],
        *,
        location_query: str | None = None,
        boundary: str | None = None,
        take: int = INSIGHTS_MAX_TAKE,
    ) -> tuple[list[HeatmapPoint], QlooQuery]:
        params = P.heatmap_params(seed_entity_ids, location_query, boundary, take)
        seed = self._seed_slug(seed_entity_ids)
        candidates = []
        if location_query:
            candidates.append(f"insights_heatmap_{seed}_{slugify(location_query)}")
        candidates.append(f"insights_heatmap_{seed}")
        body, fx = self._find(*candidates)
        pts = parse_heatmap(body)
        return pts, self._query("/v2/insights", params, fx, len(pts))

    async def tags_search(
        self, query: str, *, tag_types: list[str] | None = None, take: int = 20
    ) -> tuple[list[Tag], QlooQuery]:
        params = P.tags_search_params(query, tag_types, take)
        body, fx = self._find(f"tags_search_{slugify(query)}")
        tags = parse_tags(body)[:take]
        return tags, self._query("/v2/tags", params, fx, len(tags))

    async def compare(
        self, a_entity_ids: list[str], b_entity_ids: list[str], *, take: int = INSIGHTS_MAX_TAKE
    ) -> tuple[CompareResult, QlooQuery]:
        params = P.compare_params(a_entity_ids, b_entity_ids, take)
        a, b = self._seed_slug(a_entity_ids), self._seed_slug(b_entity_ids)
        body, fx = self._find(f"compare_{a}_vs_{b}", f"compare_{b}_vs_{a}")
        cmp = parse_compare(body)
        n = len(cmp.tags) + len(cmp.entities)
        return cmp, self._query("/v2/analysis/compare", params, fx, n)

    async def raw(self, endpoint: str, params: dict[str, Any]) -> tuple[dict[str, Any], QlooQuery]:
        body, fx = self._find("empty_results")
        return body, self._query(endpoint, params, fx, 0)

    async def aclose(self) -> None:
        return None
