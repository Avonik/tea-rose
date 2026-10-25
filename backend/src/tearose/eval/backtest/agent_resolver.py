"""Harness v3 resolver: the PRODUCT's model-driven resolve node (agent/nodes/resolve.py) on the
pre-registered mapping, instead of the code-only name rule.

Per mapping row:
- an Extraction is built from the frozen mapping only: party name = mark = the side's query,
  goods = the side's goods phrase. Fields the mapping cannot provide get neutral defaults
  (document_type "unknown", claims ["other"], no channels, no quotes). No court label, factor
  column, outcome or inclusion flag is part of the input.
- the case name and year and the entity-type hint (senior_type / junior_type) reach the model
  through the node's instruction block (the channel the product uses for follow-up
  instructions). A non-brand side (e.g. "artist" for Aqua) is also searched as that type: the
  ToolContext gets a thin client adapter that adds `types=<hint>` to /search calls for that
  side's query. Everything else is the node unchanged (same prompt, tools, validation).
- per side the record carries the node's pick (entity id, name, popularity, disambiguation note,
  candidates), the name-rule guardrail result (match rule and similarity, as a note), the proxy
  (taxonomy nodes with fit, comparator ids/names) and the universe (tags, source), plus the
  rule's pick on the same cached /search results for comparison (`rule_pick`, `agrees_with_rule`).
- per case: the model name, `llm_calls` (chat-model invocations, counted by a callback),
  `tool_calls` (model tool calls in the node's loop) and `qloo_tool_calls` (incl. code
  fallbacks), plus `error` when the structured decision or the node failed. A failure never
  aborts the run: the node's code fallbacks apply, or the case is recorded as unresolved.
The same-entity guard (both sides on one entity -> junior miss) is the node's own guard.
Scoring arithmetic stays in code (score_step); a proxied side is seeded with the agent's
comparators, as the product's fetch node does (the node itself fills them by the shared code
rule, scoring/comparators.py, when the model kept fewer than 2; score_step applies the rule only
when the record still has none).
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from tearose.agent.llm import ModelFactory
from tearose.agent.nodes import resolve as resolve_node
from tearose.agent.nodes.base import RunContext
from tearose.agent.tools import ToolContext
from tearose.eval.backtest.common import DEFAULT_ENTITY_TYPE, Recorder, entity_urn
from tearose.qloo.client import BRAND
from tearose.qloo.fixtures import slugify
from tearose.qloo.models import Entity, Tag
from tearose.qloo.names import pick_by_name
from tearose.schemas import Extraction, Party, ProxyResolution, Resolution, TraceEvent

DECISION_FAILED = "Resolution decision failed"


class LLMCallCounter(AsyncCallbackHandler):
    """Counts chat-model invocations (tool-loop rounds, structured decision, JSON fallback)."""

    def __init__(self) -> None:
        self.count = 0

    async def on_chat_model_start(
        self, serialized: dict[str, Any], messages: Any, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self.count += 1

    async def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self.count += 1

    def take(self) -> int:
        n, self.count = self.count, 0
        return n


class TypeHintClient:
    """QlooClient adapter: /search for a hinted query uses the pre-registered entity type
    (brand otherwise). Every other call is delegated unchanged."""

    def __init__(self, client: Any, hints: dict[str, str]) -> None:
        self._client = client
        self._hints = hints  # slug(query) -> urn:entity:<type>

    async def search(self, query: str, *, types: str = BRAND, take: int = 10) -> Any:
        if types == BRAND:
            types = self._hints.get(slugify(query), types)
        return await self._client.search(query, types=types, take=take)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def side_type(row: dict[str, str], side: str) -> str:
    return (row.get(f"{side}_type") or DEFAULT_ENTITY_TYPE).strip() or DEFAULT_ENTITY_TYPE


def build_extraction(row: dict[str, str]) -> Extraction:
    """Extraction from the frozen mapping only (queries, goods phrases, case name/year)."""

    def party(side: str) -> Party:
        q = row[f"{side}_query"].strip()
        goods = row.get(f"{side}_goods_phrase", "").strip()
        return Party(side=side, name=q, marks=[q] if q else [], goods=[goods] if goods else [])  # type: ignore[arg-type]

    title = f"{row.get('case_name', '').strip()} ({row.get('year', '').strip()})"
    return Extraction(
        document_type="unknown",
        title=title,
        senior=party("senior"),
        junior=party("junior"),
        claims=["other"],
        summary=f"Back-test input built from the pre-registered mapping for {title}.",
    )


def instruction(row: dict[str, str]) -> str:
    """Context for the model: case name/year and entity-type hints. No labels, no factors."""
    parts = [
        f"Back-test context: {row.get('case_name', '').strip()} ({row.get('year', '').strip()}). "
        "Resolve each party exactly as named; the goods phrase is the category to match."
    ]
    for side in ("senior", "junior"):
        t = side_type(row, side)
        if t != DEFAULT_ENTITY_TYPE:
            parts.append(
                f"The {side} side ({row[f'{side}_query']!r}) is a Qloo {t}, not a brand: "
                f"qloo_search for it returns {t} entities; pick among those."
            )
    return " ".join(parts)


def _tag_names(tc: ToolContext, ids: list[str], extra: list[Tag] | None = None) -> list[str]:
    by_id = {n.tag_id: n.name for n in tc.taxonomy}
    for t in extra or []:
        by_id.setdefault(t.tag_id, t.name)
    out = []
    for tid in ids:
        name = by_id.get(tid) or (tc.tags[tid].name if tid in tc.tags else None)
        out.append(name or tid.rsplit(":", 1)[-1].replace("_", " "))
    return out


def _popularity(tc: ToolContext, entity_id: str) -> float | None:
    """From the /search store, else from any insights page (rule-filled comparators)."""
    if entity_id in tc.entities:
        return tc.entities[entity_id].popularity
    for pages in tc.pages.values():
        for ents in pages.values():
            for e in ents:
                if e.entity_id == entity_id:
                    return e.popularity
    return None


def _universe_event(events: list[TraceEvent], side: str) -> TraceEvent | None:
    hits = [
        e
        for e in events
        if e.type == "decision" and e.title.startswith(f"{side} universe:") and "source" in e.data
    ]
    return hits[-1] if hits else None


async def _rule_pick(rec: Recorder, query: str, type_: str, avoid: str | None) -> dict[str, Any]:
    """The v2 name rule on the same /search (memoised / cached), for comparison only."""
    results = list(await rec.search(query, take=10, types=entity_urn(type_))) if query else []
    if not results:
        ent, rule = None, "no results"
    else:
        ent, rule = pick_by_name(query, results)
    if ent is not None and avoid and ent.entity_id == avoid:
        ent, rule = None, "picked the other side's entity"
    return {
        "entity_id": ent.entity_id if ent else None,
        "entity_name": ent.name if ent else None,
        "pick_rule": rule,
    }


def _side_record(
    side: str,
    row: dict[str, str],
    party: Party,
    res: Resolution | None,
    tc: ToolContext,
    events: list[TraceEvent],
    rule_pick: dict[str, Any],
) -> dict[str, Any]:
    t = side_type(row, side)
    rec: dict[str, Any] = {
        "query": row[f"{side}_query"],
        "type": t,
        "type_urn": entity_urn(t),
        "goods_phrase": row.get(f"{side}_goods_phrase", ""),
        "pick_rule": "agent",
        "entity_id": None,
        "entity_name": None,
        "popularity": None,
        "disambiguation_note": None,
        "candidates_considered": [],
        "name_check": None,
        "proxy": None,
        "universe": None,
        "rule_pick": rule_pick,
        "agrees_with_rule": None,
        "status": "unresolved",
        "notes": [],
    }
    if res is None:
        rec["notes"].append("resolve node failed; side not resolved")
        return rec
    brand = res.senior if side == "senior" else res.junior
    proxy: ProxyResolution | None = res.senior_proxy if side == "senior" else res.junior_proxy
    rec.update(
        query=brand.query,
        entity_id=brand.entity_id,
        entity_name=brand.entity_name,
        popularity=brand.popularity,
        disambiguation_note=brand.disambiguation_note,
        candidates_considered=brand.candidates_considered,
    )
    entity: Entity | None = tc.entities.get(brand.entity_id) if brand.entity_id else None
    if entity is not None:
        rule, ratio = resolve_node._name_check(party, entity)
        rec["name_check"] = {
            "rule": rule,
            "similarity": round(ratio, 3),
            "note": f"name-rule guardrail: {entity.name!r} vs {party.name!r} -> {rule} "
            f"(similarity {ratio:.2f})",
        }
    rec["agrees_with_rule"] = brand.entity_id == rule_pick["entity_id"]

    uni = next((u for u in res.universes if u.side == side), None)
    if uni is not None:
        ev = _universe_event(events, side)
        rec["universe"] = {
            "tag_ids": list(uni.tag_ids),
            "tag_names": _tag_names(tc, uni.tag_ids, entity.tag_details if entity else None),
            "description": uni.description,
            "source": (ev.data.get("source") if ev else None) or "agent",
        }
    if brand.entity_id:
        rec["status"] = "resolved"
        if uni is None:
            rec["notes"].append("no category universe could be built")
        return rec
    if proxy is not None:
        rec["proxy"] = {
            "goods_phrase": proxy.goods_phrase,
            "tag_options": proxy.tag_options,
            "chosen_tag_ids": list(proxy.chosen_tag_ids),
            "chosen_tag_names": _tag_names(tc, proxy.chosen_tag_ids),
            "fit": proxy.fit,
            "fit_note": proxy.fit_note,
            "comparator_entity_ids": proxy.comparator_brand_ids,
            "comparator_entity_names": proxy.comparator_brand_names,
            "comparator_popularity": [_popularity(tc, c) for c in proxy.comparator_brand_ids],
            "comparator_source": proxy.comparator_source,
            "rationale": proxy.rationale,
            "rule": "agent (resolve node; with fewer than 2 kept, the node fills up to 3 by the "
            "shared code rule); score_step seeds with these comparators",
        }
        if proxy.chosen_tag_ids:
            rec["status"] = "proxy"
            if rec["universe"] is None:
                rec["universe"] = {
                    "tag_ids": list(proxy.chosen_tag_ids),
                    "tag_names": rec["proxy"]["chosen_tag_names"],
                    "source": "proxy tags",
                }
            return rec
    rec["notes"].append("no brand and no tags for the goods phrase")
    return rec


async def resolve_case_agent(
    rec: Recorder,
    row: dict[str, str],
    model_factory: ModelFactory,
    counter: LLMCallCounter,
    model_name: str | None = None,
) -> dict[str, Any]:
    events: list[TraceEvent] = []

    async def emit(e: TraceEvent) -> None:
        events.append(e)

    hints = {
        slugify(row[f"{s}_query"]): entity_urn(side_type(row, s))
        for s in ("senior", "junior")
        if side_type(row, s) != DEFAULT_ENTITY_TYPE
    }
    tc = ToolContext(TypeHintClient(rec.client, hints), emit)
    ctx = RunContext(client=rec.client, model_factory=model_factory, emit=emit, tools=tc)
    ex = build_extraction(row)
    state = {"extraction": ex, "instruction": instruction(row)}
    error: str | None = None
    res: Resolution | None = None
    counter.take()
    try:
        res = (await resolve_node.run(state, ctx))["resolution"]
    except Exception as exc:  # noqa: BLE001 - one failed case must not abort the run
        status = getattr(exc, "status", None)
        if status in (401, 403):
            raise
        error = f"resolve node failed: {exc!r}"[:400]
    llm_calls = counter.take()
    failed = [e for e in events if e.type == "warning" and e.title.startswith(DECISION_FAILED)]
    if failed and error is None:
        error = f"{DECISION_FAILED}: {failed[-1].detail or ''}"[:400]
    loop_notes = [e.title for e in events if e.type == "note"]
    note = next((m for t in loop_notes if (m := re.match(r"(\d+) model tool call", t))), None)

    s_rule = await _rule_pick(rec, row["senior_query"], side_type(row, "senior"), None)
    j_rule = await _rule_pick(
        rec, row["junior_query"], side_type(row, "junior"), s_rule["entity_id"]
    )
    senior = _side_record("senior", row, ex.senior, res, tc, events, s_rule)
    junior = _side_record("junior", row, ex.junior, res, tc, events, j_rule)
    queries = [
        {**q.model_dump(mode="json"), "call": "agent:" + q.endpoint} for q in tc.queries
    ] + rec.take_queries()
    notes = rec.take_notes() + [
        f"{e.title}" + (f" ({e.detail})" if e.detail else "") for e in events if e.type == "warning"
    ]
    return {
        "case_id": row["case_id"],
        "resolver": "agent",
        "model": model_name,
        "llm_calls": llm_calls,
        "tool_calls": int(note.group(1)) if note else None,
        "qloo_tool_calls": sum(e.type == "tool_call" for e in events),
        "error": error,
        "senior": senior,
        "junior": junior,
        "queries": queries,
        "notes": notes,
    }


def counted_factory(base: ModelFactory, counter: LLMCallCounter) -> ModelFactory:
    """The configured model with the call counter attached (instance callbacks propagate to
    bind_tools / with_structured_output runnables)."""

    def factory(strong: bool = False) -> Any:
        model = base(strong)
        cbs = list(model.callbacks) if isinstance(model.callbacks, list) else []
        if counter not in cbs:
            model.callbacks = [*cbs, counter]
        return model

    return factory
