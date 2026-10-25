"""Shared paths, JSON/CSV helpers and the recording Qloo wrapper used by resolve and score."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from tearose.config import BACKEND_DIR, REPO_DIR
from tearose.qloo.client import DEFAULT_INSIGHTS_TAG_TYPES, QlooClient
from tearose.qloo.models import QlooQuery

EVAL_DIR = BACKEND_DIR / "eval"
CASES_CSV = EVAL_DIR / "cases_candidates.csv"
MAPPING_CSV = EVAL_DIR / "mapping.csv"
FIXTURE_OUT_DIR = EVAL_DIR / "_fixture"  # fixture-mode outputs never mix with real results
FRONTEND_JSON = REPO_DIR / "frontend" / "src" / "content" / "backtest.json"
RESOLVED_NAME = "resolved.json"
SCORES_NAME = "scores.json"

LIVE_SLEEP_S = 0.25  # extra pause between uncached live calls (LiveClient also rate-limits)

# Qloo entity types a mapping side may be searched as (short names; "brand" is the default).
ENTITY_TYPES = ("brand", "artist", "movie", "book", "tv_show", "person", "place", "podcast")
DEFAULT_ENTITY_TYPE = "brand"


def entity_urn(short: str | None) -> str:
    """Short name -> URN (artist -> urn:entity:artist); empty/None -> brand (old mappings)."""
    t = (short or DEFAULT_ENTITY_TYPE).strip() or DEFAULT_ENTITY_TYPE
    if t not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type {t!r}; expected one of {ENTITY_TYPES}")
    return f"urn:entity:{t}"


def default_out_dir(mode: str) -> Path:
    """Where resolve/score/report write: backend/eval/ for live, backend/eval/_fixture/ else."""
    return EVAL_DIR if mode == "live" else FIXTURE_OUT_DIR


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class Recorder:
    """Wraps a QlooClient: sequential calls, per-process memo, provenance log, error capture.

    Every call is appended to `queries` (as a QlooQuery dump, with an `error` key when the call
    failed). Identical calls within one process are served from the memo and marked
    `memo_hit`, so a brand that appears in four rows is fetched once. Errors other than auth
    errors become empty results plus a note; 401/403 abort the run (wrong key or base URL).
    """

    def __init__(self, client: QlooClient, live: bool) -> None:
        self.client = client
        self.live = live
        self.queries: list[dict[str, Any]] = []
        self.notes: list[str] = []
        self._memo: dict[str, tuple[Any, dict[str, Any]]] = {}

    def take_queries(self) -> list[dict[str, Any]]:
        out, self.queries = self.queries, []
        return out

    def take_notes(self) -> list[str]:
        out, self.notes = self.notes, []
        return out

    async def call(
        self,
        name: str,
        empty: Any,
        fn: Callable[[], Awaitable[tuple[Any, QlooQuery]]],
        **key: Any,
    ) -> Any:
        memo_key = json.dumps([name, key], sort_keys=True, default=str)
        if memo_key in self._memo:
            data, q = self._memo[memo_key]
            self.queries.append({**q, "memo_hit": True})
            return data
        try:
            data, query = await fn()
            q = query.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - one failed call must not kill the run
            status = getattr(exc, "status", None)
            if status in (401, 403):
                raise
            data = empty
            q = {"endpoint": name, "params": key, "status": status, "error": repr(exc)[:300]}
            self.notes.append(f"{name} failed ({status}): {repr(exc)[:160]}")
        q["call"] = name
        self._memo[memo_key] = (data, q)
        self.queries.append(q)
        if self.live and not q.get("cache_hit"):
            await asyncio.sleep(LIVE_SLEEP_S)
        return data

    async def search(self, query: str, take: int = 10, types: str = "urn:entity:brand") -> Any:
        return await self.call(
            "search",
            [],
            lambda: self.client.search(query, types=types, take=take),
            query=query,
            types=types,
            take=take,
        )

    async def tags_search(self, query: str) -> Any:
        return await self.call(
            "tags_search", [], lambda: self.client.tags_search(query), query=query
        )

    async def insights_tags(
        self, seeds: list[str], take: int = 50, tag_types: tuple[str, ...] | None = None
    ) -> Any:
        """Brand-genre tags by default (filter.tag.types=urn:tag:genre:brand)."""
        types = list(tag_types or DEFAULT_INSIGHTS_TAG_TYPES)
        return await self.call(
            "insights_tags",
            [],
            lambda: self.client.insights_tags(seeds, take=take, tag_types=types),
            seeds=seeds,
            take=take,
            tag_types=types,
        )

    async def insights_entities(
        self,
        seeds: list[str],
        filter_tags: list[str] | None,
        page: int,
        take: int = 50,
        result_type: str = "urn:entity:brand",
    ) -> Any:
        return await self.call(
            "insights_entities",
            [],
            lambda: self.client.insights_entities(
                seeds, result_type=result_type, filter_tags=filter_tags, page=page, take=take
            ),
            seeds=seeds,
            result_type=result_type,
            filter_tags=filter_tags,
            page=page,
            take=take,
        )

    async def demographics(self, seeds: list[str]) -> Any:
        return await self.call(
            "demographics", None, lambda: self.client.demographics(seeds), seeds=seeds
        )

    async def heatmap(self, seeds: list[str], location_query: str | None) -> Any:
        return await self.call(
            "heatmap",
            [],
            lambda: self.client.heatmap(seeds, location_query=location_query),
            seeds=seeds,
            location_query=location_query,
        )
