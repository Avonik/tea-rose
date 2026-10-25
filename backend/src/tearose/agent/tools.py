"""LangChain tools over an injected QlooClient, plus the per-run ToolContext.

The model sees compact JSON summaries (ids, names, ranks, counts — never 50 full objects);
the ToolContext keeps every parsed result and every QlooQuery so code can assemble
Resolution / RawData without trusting the model to copy numbers. Each call emits a
`tool_call` and a `tool_result` TraceEvent through the run's emitter.

Retry policy (code, not model): an empty first page from insights_entities with several
filter tags is retried once with the single broadest tag; if that is empty too (or there was
only one tag), the combination is marked as given up and a note is recorded.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from tearose.qloo.client import INSIGHTS_MAX_TAKE, QlooClient
from tearose.qloo.models import (
    CompareResult,
    Demographics,
    Entity,
    HeatmapPoint,
    QlooQuery,
    Tag,
)
from tearose.qloo.taxonomy import TaxonomyNode
from tearose.schemas import TraceEvent

Emit = Callable[[TraceEvent], Awaitable[Any]]
Key = tuple[tuple[str, ...], tuple[str, ...]]  # (seed ids, filter tag ids)

MAX_PAGES = 3
GENRE_BRAND_PREFIX = "urn:tag:genre:brand:"
NATIONAL = "United States"
NATIONAL_FALLBACK = "USA"


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 3)


def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)


def broadest_tag(tag_ids: list[str] | tuple[str, ...]) -> str:
    """Fewest path segments wins (urn:tag:genre:brand:pet_supplies beats …:dog_toys)."""
    return min(tag_ids, key=lambda t: (t.count(":"), len(t)))


class ToolContext:
    """Per-run store of everything the Qloo tools returned, plus provenance."""

    def __init__(self, client: QlooClient, emit: Emit, query_offset: int = 0) -> None:
        self.client = client
        self.emit = emit
        self.node = "resolve"
        self.query_offset = query_offset
        self.queries: list[QlooQuery] = []
        self._drained = 0
        self.notes: list[str] = []
        self.calls_by_node: Counter[str] = Counter()
        self.targets: dict[str, str] = {}  # entity id -> label, highlighted in summaries
        # stores
        self.searches: list[tuple[str, list[Entity]]] = []
        self.entities: dict[str, Entity] = {}  # every entity returned by /search
        self.names: dict[str, str] = {}  # entity id -> name from any response
        self.tag_searches: list[tuple[str, list[Tag]]] = []
        self.tags: dict[str, Tag] = {}  # every tag seen anywhere
        self.pages: dict[Key, dict[int, list[Entity]]] = {}
        self.filter_alias: dict[Key, tuple[str, ...]] = {}  # original filter -> retried filter
        self.gave_up: set[Key] = set()
        self.seed_tags: dict[tuple[str, ...], list[Tag]] = {}
        self.demos: dict[tuple[str, ...], Demographics] = {}
        self.heatmaps: dict[tuple[tuple[str, ...], str | None], list[HeatmapPoint]] = {}
        self.compares: dict[tuple[tuple[str, ...], tuple[str, ...]], CompareResult] = {}
        self.taxonomy: list[TaxonomyNode] = []  # brand-genre tree, loaded by resolve

    # --- provenance ------------------------------------------------------------------

    def _record(self, q: QlooQuery) -> str:
        self.queries.append(q)
        q.id = f"Q{self.query_offset + len(self.queries)}"
        return q.id

    def drain_queries(self) -> list[QlooQuery]:
        new = self.queries[self._drained :]
        self._drained = len(self.queries)
        return new

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    async def _event(self, type_: str, title: str, detail: str | None = None, **data: Any):
        ref = data.get("query_id") or data.get("ref")
        await self.emit(
            TraceEvent(node=self.node, type=type_, title=title, detail=detail, ref=ref, data=data)
        )

    async def _call(
        self, tool: str, label: str, args: dict[str, Any], fn: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, str]:
        self.calls_by_node[self.node] += 1
        await self._event("tool_call", f"{tool}({label})", tool=tool, params=args)
        t0 = time.perf_counter()
        try:
            data, q = await fn()
        except Exception as exc:
            await self._event(
                "warning", f"{tool} failed", f"{type(exc).__name__}: {exc}", tool=tool
            )
            raise
        ref = self._record(q)
        if isinstance(data, CompareResult):  # compare answers with tags, not entities
            n: int | None = len(data.tags) + len(data.entities)
        elif q.result_count is not None:
            n = q.result_count
        else:
            n = len(data) if hasattr(data, "__len__") else None
        await self._event(
            "tool_result",
            f"{tool} → {n if n is not None else '?'} result(s)",
            tool=tool,
            ref=ref,
            query_id=ref,
            endpoint=q.endpoint,
            params=q.params,
            count=n,
            result_count=n,
            cache_hit=q.cache_hit,
            fixture_file=q.fixture_file,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            query=q.model_dump(mode="json"),
        )
        return data, ref

    def _see_entities(self, ents: list[Entity]) -> None:
        for e in ents:
            self.names.setdefault(e.entity_id, e.name)

    def _see_tags(self, tags: list[Tag]) -> None:
        for t in tags:
            self.tags.setdefault(t.tag_id, t)

    # --- client wrappers (used by tools and by code fallbacks) -----------------------

    async def search(self, query: str) -> tuple[list[Entity], str]:
        ents, ref = await self._call(
            "qloo_search", repr(query), {"query": query}, lambda: self.client.search(query)
        )
        self.searches.append((query, ents))
        for e in ents:
            self.entities.setdefault(e.entity_id, e)
        self._see_entities(ents)
        return ents, ref

    async def tags_search(self, query: str) -> tuple[list[Tag], str]:
        tags, ref = await self._call(
            "qloo_tags_search",
            repr(query),
            {"query": query},
            lambda: self.client.tags_search(query),
        )
        self.tag_searches.append((query, tags))
        self._see_tags(tags)
        return tags, ref

    def resolve_filter(self, seeds: list[str], filter_tags: list[str] | None) -> Key:
        orig: Key = (tuple(seeds), tuple(filter_tags or ()))
        return (orig[0], self.filter_alias.get(orig, orig[1]))

    async def insights_entities(
        self,
        seeds: list[str],
        filter_tags: list[str] | None = None,
        page: int = 1,
        *,
        retry: bool = True,
    ) -> tuple[list[Entity], str | None]:
        orig: Key = (tuple(seeds), tuple(filter_tags or ()))
        key = self.resolve_filter(seeds, filter_tags)
        if orig in self.gave_up or key in self.gave_up:
            return [], None
        filt = list(key[1]) or None
        ents, ref = await self._call(
            "qloo_insights_entities",
            f"seed={len(seeds)}, filter={len(key[1])} tag(s), page={page}",
            {"seed_entity_ids": seeds, "filter_tags": filt, "page": page},
            lambda: self.client.insights_entities(
                seeds, filter_tags=filt, page=page, take=INSIGHTS_MAX_TAKE
            ),
        )
        self.pages.setdefault(key, {})[page] = ents
        self._see_entities(ents)
        if ents or page != 1 or not retry:
            return ents, ref
        seed_names = ", ".join(self.names.get(s, s) for s in seeds)
        if len(key[1]) > 1:
            broad = broadest_tag(key[1])
            await self._event(
                "warning",
                "Empty result; retrying with the broadest tag",
                f"{seed_names}: {len(key[1])} filter tags → {broad}",
                tags=list(key[1]),
                retry_tag=broad,
            )
            self.filter_alias[orig] = (broad,)
            ents2, ref2 = await self.insights_entities(seeds, [broad], 1, retry=False)
            if ents2:
                self.note(
                    f"Brands seeded by {seed_names} filtered to {list(key[1])} returned nothing; "
                    f"widened to the single broadest tag {broad}."
                )
                return ents2, ref2
            self.gave_up.add((tuple(seeds), (broad,)))
            filt_desc = f"{list(key[1])} and then {broad}"
        else:
            filt_desc = str(list(key[1])) if key[1] else "no tag filter"
        self.gave_up.add(orig)
        self.note(f"Gave up: brands seeded by {seed_names} with {filt_desc} returned no results.")
        await self._event("warning", "Gave up on an empty query", self.notes[-1])
        return [], ref

    def concat_pages(self, key: Key) -> tuple[list[Entity], int, bool]:
        """Contiguous pages from 1, re-ranked overall. Returns (entities, pages, exhausted)."""
        pages = self.pages.get(key, {})
        out: list[Entity] = []
        n = 0
        exhausted = False
        for p in range(1, MAX_PAGES + 1):
            if p not in pages:
                break
            n = p
            out.extend(pages[p])
            if len(pages[p]) < INSIGHTS_MAX_TAKE:
                exhausted = True
                break
        ranked = [e.model_copy(update={"rank": i + 1}) for i, e in enumerate(out)]
        return ranked, n, exhausted

    async def insights_tags(self, seeds: list[str]) -> tuple[list[Tag], str]:
        tags, ref = await self._call(
            "qloo_insights_tags",
            f"seed={len(seeds)}",
            {"seed_entity_ids": seeds},
            lambda: self.client.insights_tags(seeds),
        )
        self.seed_tags[tuple(seeds)] = tags
        self._see_tags(tags)
        return tags, ref

    async def demographics(self, seeds: list[str]) -> tuple[Demographics, str]:
        d, ref = await self._call(
            "qloo_demographics",
            f"seed={len(seeds)}",
            {"seed_entity_ids": seeds},
            lambda: self.client.demographics(seeds),
        )
        self.demos[tuple(seeds)] = d
        return d, ref

    async def heatmap(
        self, seeds: list[str], location_query: str | None = None
    ) -> tuple[list[HeatmapPoint], str]:
        """Qloo heatmaps need a signal AND a location: no location means national."""
        loc = location_query or NATIONAL
        pts, ref = await self._call(
            "qloo_heatmap",
            f"seed={len(seeds)}, location={loc!r}",
            {"seed_entity_ids": seeds, "location_query": loc},
            lambda: self.client.heatmap(seeds, location_query=loc),
        )
        if not pts and loc == NATIONAL:
            await self._event("warning", "Empty national heatmap; retrying with 'USA'")
            pts, ref = await self._call(
                "qloo_heatmap",
                f"seed={len(seeds)}, location={NATIONAL_FALLBACK!r}",
                {"seed_entity_ids": seeds, "location_query": NATIONAL_FALLBACK},
                lambda: self.client.heatmap(seeds, location_query=NATIONAL_FALLBACK),
            )
        key_loc = None if loc == NATIONAL else location_query
        self.heatmaps[(tuple(seeds), key_loc)] = pts
        return pts, ref

    async def compare(self, a: list[str], b: list[str]) -> tuple[CompareResult, str]:
        cmp, ref = await self._call(
            "qloo_compare",
            f"a={len(a)}, b={len(b)}",
            {"a_entity_ids": a, "b_entity_ids": b},
            lambda: self.client.compare(a, b),
        )
        self.compares[(tuple(a), tuple(b))] = cmp
        self._see_tags(cmp.tags)
        return cmp, ref

    # --- summaries the model sees ----------------------------------------------------

    def _ent_brief(self, e: Entity, with_tags: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {"id": e.entity_id, "name": e.name}
        if e.popularity is not None:
            d["popularity"] = _r(e.popularity)
        if e.disambiguation:
            d["disambiguation"] = e.disambiguation
        if with_tags and e.tags:
            d["tags"] = e.tags[:6]
            cats = [self._tag_label(t) for t in e.tags if t.startswith(GENRE_BRAND_PREFIX)]
            if cats:
                d["categories"] = cats[:4]
        desc = (e.properties or {}).get("description")
        if with_tags and isinstance(desc, str):
            d["description"] = desc[:140]
        comp = (e.properties or {}).get("competitive_set")
        if with_tags and comp:
            d["competitive_set"] = comp[:8] if isinstance(comp, list) else comp
        return d

    def _tag_label(self, tag_id: str) -> str:
        t = self.tags.get(tag_id)
        if t is not None and t.name:
            return t.name
        return tag_id.rsplit(":", 1)[-1].replace("_", " ")

    @staticmethod
    def _tag_brief(t: Tag) -> dict[str, Any]:
        d: dict[str, Any] = {"id": t.tag_id, "name": t.name}
        if t.tag_type:
            d["type"] = t.tag_type
        if t.rank is not None:
            d["rank"] = t.rank
        return d


class _SearchArgs(BaseModel):
    query: str = Field(description="Brand or company name, as written")


class _TagsArgs(BaseModel):
    query: str = Field(description="Goods/services phrase (verbatim from the document first)")


class _InsightsArgs(BaseModel):
    seed_entity_ids: list[str]
    filter_tags: list[str] = Field(default_factory=list, description="Universe tag ids")
    page: int = Field(default=1, ge=1, le=MAX_PAGES)


class _SeedArgs(BaseModel):
    seed_entity_ids: list[str]


class _HeatmapArgs(BaseModel):
    seed_entity_ids: list[str]
    location_query: str | None = Field(
        default=None, description="Omit for the national (United States) map"
    )


class _CompareArgs(BaseModel):
    a_entity_ids: list[str]
    b_entity_ids: list[str]


ALL_TOOLS = (
    "qloo_search",
    "qloo_tags_search",
    "qloo_insights_entities",
    "qloo_insights_tags",
    "qloo_demographics",
    "qloo_heatmap",
    "qloo_compare",
)


def make_tools(ctx: ToolContext, names: tuple[str, ...] = ALL_TOOLS) -> list[BaseTool]:
    """LangChain tools bound to `ctx`. Each returns a compact JSON string."""

    async def qloo_search(query: str) -> str:
        ents, ref = await ctx.search(query)
        return dumps(
            {
                "ref": ref,
                "query": query,
                "count": len(ents),
                "results": [ctx._ent_brief(e, with_tags=True) for e in ents[:10]],
            }
        )

    async def qloo_tags_search(query: str) -> str:
        tags, ref = await ctx.tags_search(query)
        return dumps(
            {
                "ref": ref,
                "query": query,
                "count": len(tags),
                "tags": [ctx._tag_brief(t) for t in tags[:20]],
            }
        )

    async def qloo_insights_entities(
        seed_entity_ids: list[str], filter_tags: list[str] | None = None, page: int = 1
    ) -> str:
        ents, ref = await ctx.insights_entities(seed_entity_ids, filter_tags or None, page)
        key = ctx.resolve_filter(seed_entity_ids, filter_tags)
        all_ents, pages, exhausted = ctx.concat_pages(key)
        found = [
            {"id": e.entity_id, "name": e.name, "rank": e.rank}
            for e in all_ents
            if e.entity_id in ctx.targets
        ]
        out: dict[str, Any] = {
            "ref": ref,
            "page": page,
            "count": len(ents),
            "filter_tags_used": list(key[1]),
            "top": [
                {"rank": (page - 1) * INSIGHTS_MAX_TAKE + i + 1, "id": e.entity_id, "name": e.name}
                for i, e in enumerate(ents[:10])
            ],
            "pages_so_far": pages,
            "exhausted": exhausted,
        }
        if ctx.targets:
            out["targets_found"] = found
        if key in ctx.gave_up:
            out["gave_up"] = True
        return dumps(out)

    async def qloo_insights_tags(seed_entity_ids: list[str]) -> str:
        tags, ref = await ctx.insights_tags(seed_entity_ids)
        return dumps(
            {"ref": ref, "count": len(tags), "tags": [ctx._tag_brief(t) for t in tags[:15]]}
        )

    async def qloo_demographics(seed_entity_ids: list[str]) -> str:
        d, ref = await ctx.demographics(seed_entity_ids)
        return dumps(
            {
                "ref": ref,
                "age": {k: _r(v) for k, v in d.age.items()},
                "gender": {k: _r(v) for k, v in d.gender.items()},
            }
        )

    async def qloo_heatmap(seed_entity_ids: list[str], location_query: str | None = None) -> str:
        pts, ref = await ctx.heatmap(seed_entity_ids, location_query)
        top = sorted(pts, key=lambda p: p.affinity or 0.0, reverse=True)[:5]
        return dumps(
            {
                "ref": ref,
                "location": location_query or NATIONAL,
                "count": len(pts),
                "top_cells": [
                    {
                        "label": p.label or f"{p.latitude:.1f},{p.longitude:.1f}",
                        "affinity": _r(p.affinity),
                    }
                    for p in top
                ],
            }
        )

    async def qloo_compare(a_entity_ids: list[str], b_entity_ids: list[str]) -> str:
        cmp, ref = await ctx.compare(a_entity_ids, b_entity_ids)
        return dumps(
            {
                "ref": ref,
                "tags": len(cmp.tags),
                "top_tags": [
                    {"name": t.name, "score": _r(t.score if t.score is not None else t.affinity)}
                    for t in cmp.tags[:8]
                ],
                "entities": len(cmp.entities),
                "insufficient_data": cmp.insufficient_data,
            }
        )

    specs: dict[str, tuple[Callable[..., Awaitable[str]], type[BaseModel], str]] = {
        "qloo_search": (
            qloo_search,
            _SearchArgs,
            "Resolve a brand/company name to Qloo brand entities (id, name, popularity, tags).",
        ),
        "qloo_tags_search": (
            qloo_tags_search,
            _TagsArgs,
            "Find Qloo tag ids for a goods/category phrase. Pass the document's phrase verbatim "
            "first; only shorten it if the verbatim phrase returns nothing.",
        ),
        "qloo_insights_entities": (
            qloo_insights_entities,
            _InsightsArgs,
            "Brands ranked by affinity for a seed set, optionally restricted to universe tags. "
            "50 per page, pages 1-3. Reports where tracked target brands appear.",
        ),
        "qloo_insights_tags": (
            qloo_insights_tags,
            _SeedArgs,
            "Taste tags that characterize a seed set's audience, ranked.",
        ),
        "qloo_demographics": (
            qloo_demographics,
            _SeedArgs,
            "Age and gender affinity (-1..+1) of a seed set's audience.",
        ),
        "qloo_heatmap": (
            qloo_heatmap,
            _HeatmapArgs,
            "Geographic affinity of a seed set's audience. No location = national map.",
        ),
        "qloo_compare": (
            qloo_compare,
            _CompareArgs,
            "Tags that characterize how audience A and audience B differ.",
        ),
    }
    tools: list[BaseTool] = []
    for name in names:
        fn, schema, desc = specs[name]
        tools.append(
            StructuredTool.from_function(
                coroutine=fn, name=name, description=desc, args_schema=schema
            )
        )
    return tools
