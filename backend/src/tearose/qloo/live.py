"""LiveClient: real HTTP calls to the hackathon API, with caching, retries, rate limiting
and raw-response recording (to pin down shapes on Monday)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from tearose.config import Settings
from tearose.qloo import params as P
from tearose.qloo.cache import ResponseCache, cache_key
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


class QlooHTTPError(RuntimeError):
    def __init__(self, status: int, endpoint: str, body: str) -> None:
        super().__init__(f"Qloo {status} on {endpoint}: {body[:300]}")
        self.status = status
        self.endpoint = endpoint
        self.body = body


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, QlooHTTPError) and (exc.status == 429 or exc.status >= 500)


class _TokenBucket:
    def __init__(self, rate_per_s: float, burst: int = 4) -> None:
        self.rate = max(rate_per_s, 0.1)
        self.capacity = burst
        self.tokens = float(burst)
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def take(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
            else:
                self.tokens -= 1


class LiveClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.qloo_api_key:
            raise RuntimeError("QLOO_API_KEY is empty but qloo_mode=live")
        self._s = settings
        self._http = httpx.AsyncClient(
            base_url=settings.qloo_base_url,
            headers={"X-Api-Key": settings.qloo_api_key, "Accept": "application/json"},
            timeout=settings.qloo_timeout_s,
        )
        self._cache = ResponseCache(settings.qloo_cache_path)
        self._bucket = _TokenBucket(settings.qloo_max_rps)
        self._record_dir: Path | None = settings.qloo_record_raw_dir
        if self._record_dir:
            self._record_dir.mkdir(parents=True, exist_ok=True)

    # --- transport ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception(_retryable),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=0.5, max=8),
        reraise=True,
    )
    async def _fetch(self, endpoint: str, params: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        await self._bucket.take()
        resp = await self._http.get(endpoint, params=params)
        if resp.status_code >= 400:
            raise QlooHTTPError(resp.status_code, endpoint, resp.text)
        try:
            return resp.status_code, resp.json()
        except json.JSONDecodeError as e:
            raise QlooHTTPError(resp.status_code, endpoint, resp.text) from e

    async def _get(self, endpoint: str, params: dict[str, Any]) -> tuple[dict[str, Any], QlooQuery]:
        q = QlooQuery(endpoint=endpoint, params=params)
        cached = self._cache.get(endpoint, params)
        if cached is not None:
            q.cache_hit, q.status = True, cached[0]
            return cached[1], q
        t0 = time.perf_counter()
        status, body = await self._fetch(endpoint, params)
        q.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        q.status = status
        self._cache.put(endpoint, params, status, body)
        self._record(endpoint, params, body)
        return body, q

    def _record(self, endpoint: str, params: dict[str, Any], body: dict[str, Any]) -> None:
        if not self._record_dir:
            return
        name = f"{endpoint.strip('/').replace('/', '_')}_{cache_key(endpoint, params)[:12]}.json"
        (self._record_dir / name).write_text(
            json.dumps({"endpoint": endpoint, "params": params, "body": body}, indent=2),
            encoding="utf-8",
        )

    # --- QlooClient protocol ----------------------------------------------------------

    async def search(self, query: str, *, types: str = BRAND, take: int = 10):
        body, q = await self._get("/search", P.search_params(query, types, take))
        ents = parse_search(body)
        q.result_count = len(ents)
        return ents, q

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
        body, q = await self._get("/v2/insights", params)
        ents = parse_entities(body)
        q.result_count = len(ents)
        return ents, q

    async def insights_tags(
        self, seed_entity_ids: list[str], *, take: int = INSIGHTS_MAX_TAKE
    ) -> tuple[list[Tag], QlooQuery]:
        body, q = await self._get("/v2/insights", P.insights_tags_params(seed_entity_ids, take))
        tags = parse_tags(body)
        q.result_count = len(tags)
        return tags, q

    async def demographics(self, seed_entity_ids: list[str]) -> tuple[Demographics, QlooQuery]:
        body, q = await self._get("/v2/insights", P.demographics_params(seed_entity_ids))
        d = parse_demographics(body)
        q.result_count = len(d.age) + len(d.gender)
        return d, q

    async def heatmap(
        self,
        seed_entity_ids: list[str],
        *,
        location_query: str | None = None,
        boundary: str | None = None,
        take: int = INSIGHTS_MAX_TAKE,
    ) -> tuple[list[HeatmapPoint], QlooQuery]:
        params = P.heatmap_params(seed_entity_ids, location_query, boundary, take)
        body, q = await self._get("/v2/insights", params)
        pts = parse_heatmap(body)
        q.result_count = len(pts)
        return pts, q

    async def tags_search(
        self, query: str, *, tag_types: list[str] | None = None, take: int = 20
    ) -> tuple[list[Tag], QlooQuery]:
        body, q = await self._get("/v2/tags", P.tags_search_params(query, tag_types, take))
        tags = parse_tags(body)
        q.result_count = len(tags)
        return tags, q

    async def compare(
        self, a_entity_ids: list[str], b_entity_ids: list[str], *, take: int = INSIGHTS_MAX_TAKE
    ) -> tuple[CompareResult, QlooQuery]:
        body, q = await self._get(
            "/v2/analysis/compare", P.compare_params(a_entity_ids, b_entity_ids, take)
        )
        cmp = parse_compare(body)
        q.result_count = len(cmp.entities)
        return cmp, q

    async def raw(self, endpoint: str, params: dict[str, Any]) -> tuple[dict[str, Any], QlooQuery]:
        return await self._get(endpoint, params)

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()
