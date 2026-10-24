"""resolve: parties -> Resolution (tool loop + mechanical validation in code).

The model searches, disambiguates and proposes; code enforces the rules:
- an entity id counts only if a /search call returned it;
- on the proxy path the goods phrase goes to /v2/tags VERBATIM (code runs it if the model
  did not), a shortened phrase is tried only when the verbatim one is empty, chosen tags must
  come from the returned menu, and every option is recorded;
- comparators must resolve via /search and share a chosen tag (when Qloo returns tags);
- universes use only tag ids that some Qloo response actually returned.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from tearose.agent.llm import ainvoke_structured
from tearose.agent.nodes.base import (
    NodeEvents,
    RunContext,
    instruction_block,
    load_prompt,
    run_tool_loop,
    to_json,
)
from tearose.agent.tools import MAX_PAGES, ToolContext, make_tools
from tearose.qloo.client import INSIGHTS_MAX_TAKE
from tearose.qloo.fixtures import slugify
from tearose.qloo.models import Entity, Tag
from tearose.schemas import (
    Extraction,
    Party,
    ProxyResolution,
    Resolution,
    ResolvedBrand,
    Side,
    Universe,
)
from tearose.scoring.universe import build_universe_description, pick_category_tags

MAX_CALLS = 12
MAX_COMPARATORS = 5
UNIVERSE_NOMINAL = MAX_PAGES * INSIGHTS_MAX_TAKE  # ranks considered per direction
RESOLVE_TOOLS = ("qloo_search", "qloo_tags_search", "qloo_insights_entities", "qloo_insights_tags")


class SideDecision(BaseModel):
    query: str | None = Field(default=None, description="the search string that found the brand")
    entity_id: str | None = Field(
        default=None, description="chosen Qloo entity id, or null when no candidate fits"
    )
    candidates_considered: list[str] = Field(default_factory=list)
    disambiguation_note: str | None = None
    proxy_goods_phrase: str | None = Field(
        default=None, description="proxy path only: goods phrase sent verbatim to tags search"
    )
    proxy_chosen_tag_ids: list[str] = Field(default_factory=list)
    comparator_entity_ids: list[str] = Field(default_factory=list)
    universe_description: str | None = None
    universe_tag_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class ResolveDecision(BaseModel):
    senior: SideDecision
    junior: SideDecision


def shorten_phrase(phrase: str) -> str | None:
    """A shorter parent phrase for an empty /v2/tags lookup: first clause, last two words."""
    p = re.sub(r"\(.*?\)", " ", phrase)
    first = re.split(r"[;,:]|\band\b|\bor\b|\bnamely\b", p, flags=re.I)[0]
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", first)
    short = " ".join(words[-2:]) if words else ""
    if not short or short.casefold() == phrase.strip().casefold():
        return None
    return short


def _dedupe(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in xs if x and not (x in seen or seen.add(x))]


def _tag_obj(tc: ToolContext, tag_id: str) -> Tag:
    return tc.tags.get(tag_id) or Tag(
        tag_id=tag_id, name=tag_id.rsplit(":", 1)[-1].replace("_", " ")
    )


def _known_tag_ids(tc: ToolContext) -> set[str]:
    ids = set(tc.tags)
    for e in tc.entities.values():
        ids.update(e.tags)
    for pages in tc.pages.values():
        for ents in pages.values():
            for e in ents:
                ids.update(e.tags)
    return ids


async def _ensure_search(side: Side, party: Party, tc: ToolContext, ev: NodeEvents) -> None:
    keys = {slugify(x) for x in [*party.marks, party.name] if x}
    if any(slugify(q) in keys for q, _ in tc.searches):
        return
    q = party.marks[0] if party.marks else party.name
    await ev.warning(f"{side}: the model did not search the mark; code searched {q!r}")
    await tc.search(q)


async def _proxy(
    side: Side, party: Party, d: SideDecision, tc: ToolContext, ev: NodeEvents
) -> ProxyResolution:
    goods = [g for g in party.goods if g.strip()]
    folded = {g.casefold(): g for g in goods}
    phrase = folded.get((d.proxy_goods_phrase or "").casefold()) or (
        goods[0] if goods else (d.proxy_goods_phrase or "")
    )
    if not phrase:
        await ev.warning(f"{side}: no goods phrase in the document; proxy path impossible")
        return ProxyResolution(
            side=side, goods_phrase="", tag_options=[], chosen_tag_ids=[],
            rationale="No goods/services phrase was extracted, so no tag lookup was possible.",
        )  # fmt: skip

    def searched(q: str) -> list[Tag] | None:
        hits = [tags for qq, tags in tc.tag_searches if qq.casefold() == q.casefold()]
        return hits[-1] if hits else None

    if searched(phrase) is None:
        await ev.warning(
            f"{side}: goods phrase not queried verbatim by the model; code queried it",
            repr(phrase),
        )
        await tc.tags_search(phrase)
    short: str | None = None
    if not searched(phrase):
        related_hit = any(tags for q, tags in tc.tag_searches if q.casefold() in phrase.casefold())
        short = shorten_phrase(phrase)
        if not related_hit and short and searched(short) is None:
            await ev.decision(
                f"{side}: verbatim phrase returned no tags; trying shorter phrase",
                f"{phrase!r} → {short!r}",
                goods_phrase=phrase,
                shortened_phrase=short,
            )
            await tc.tags_search(short)

    chosen_req = set(d.proxy_chosen_tag_ids)
    related = [
        (q, tags)
        for q, tags in tc.tag_searches
        if q.casefold() == phrase.casefold()
        or q.casefold() in phrase.casefold()
        or (short and q.casefold() == short.casefold())
        or chosen_req & {t.tag_id for t in tags}
    ]
    options: dict[str, Tag] = {}
    for _, tags in related:
        for t in tags:
            options.setdefault(t.tag_id, t)
    chosen = [t for t in _dedupe(d.proxy_chosen_tag_ids) if t in options]
    rejected = [t for t in d.proxy_chosen_tag_ids if t not in options]
    if rejected:
        await ev.warning(
            f"{side}: chosen tags not on the returned menu were dropped", ", ".join(rejected)
        )
    heuristic = [t.tag_id for t in pick_category_tags(list(options.values()), phrase)]
    if not chosen and options:
        chosen = heuristic or [next(iter(options))]
        await ev.warning(
            f"{side}: no valid tag choice from the model; code picked", ", ".join(chosen)
        )
    elif chosen and heuristic and not set(chosen) & set(heuristic):
        await ev.warning(
            f"{side}: tag choice differs completely from the keyword heuristic",
            f"agent: {chosen}; heuristic: {heuristic}",
        )

    kept: list[Entity] = []
    notes: list[str] = []
    for cid in _dedupe(d.comparator_entity_ids):
        e = tc.entities.get(cid)
        if e is None:
            notes.append(f"dropped {cid}: not returned by any brand search")
        elif e.tags and not set(e.tags) & set(chosen):
            notes.append(f"dropped {e.name}: shares no chosen category tag")
        else:
            if not e.tags:
                notes.append(f"{e.name}: /search returned no tags, category not verifiable")
            kept.append(e)
        if len(kept) >= MAX_COMPARATORS:
            break
    for n in notes:
        if n.startswith("dropped"):
            await ev.warning(f"{side}: comparator {n}")
    if not kept:
        await ev.warning(f"{side}: no usable comparator brands; this side cannot seed queries")

    tried = "; ".join(
        f"{q!r} → {len(tags)} tag(s)" for q, tags in tc.tag_searches if (q, tags) in related
    )
    rationale = " ".join(
        x
        for x in (
            d.rationale.strip(),
            f"Tag searches: {tried}." if tried else "",
            f"Comparators: {'; '.join(notes)}." if notes else "",
        )
        if x
    )
    proxy = ProxyResolution(
        side=side,
        goods_phrase=phrase,
        tag_options=[
            {"id": t.tag_id, "name": t.name, "type": t.tag_type} for t in options.values()
        ],
        chosen_tag_ids=chosen,
        comparator_brand_ids=[e.entity_id for e in kept],
        comparator_brand_names=[e.name for e in kept],
        rationale=rationale or "Proxy path: brand not found in Qloo.",
    )
    await ev.decision(
        f"{side}: proxy via {len(chosen)} tag(s), {len(kept)} comparator(s)",
        f"options: {', '.join(t.name for t in options.values()) or 'none'}",
        goods_phrase=phrase,
        tag_options=proxy.tag_options,
        chosen_tag_ids=chosen,
        comparators=proxy.comparator_brand_names,
    )
    return proxy


async def _universe(
    side: Side,
    party: Party,
    d: SideDecision,
    entity: Entity | None,
    proxy: ProxyResolution | None,
    tc: ToolContext,
    ev: NodeEvents,
) -> Universe | None:
    if proxy is not None:
        tag_ids, source = list(proxy.chosen_tag_ids), "proxy tags"
    else:
        known = _known_tag_ids(tc)
        tag_ids = [t for t in _dedupe(d.universe_tag_ids) if t in known]
        unknown = [t for t in d.universe_tag_ids if t not in known]
        if unknown:
            await ev.warning(
                f"{side}: universe tags never returned by Qloo were dropped", ", ".join(unknown)
            )
        source = "agent choice"
        if not tag_ids and entity is not None and entity.tags:
            tag_ids, source = entity.tags[:3], "the brand's own tags"
        if not tag_ids and party.goods:
            phrase = party.goods[0]
            results = next(
                (t for q, t in tc.tag_searches if q.casefold() == phrase.casefold()), None
            )
            if results is None:
                results, _ = await tc.tags_search(phrase)
            if not results and (short := shorten_phrase(phrase)):
                results, _ = await tc.tags_search(short)
            tag_ids = [t.tag_id for t in pick_category_tags(results, phrase)] or [
                t.tag_id for t in results[:1]
            ]
            source = "code fallback (goods phrase → tags → keyword heuristic)"
    if not tag_ids:
        await ev.warning(f"{side}: no category universe could be built")
        return None
    tags = [_tag_obj(tc, t) for t in tag_ids]
    desc = (d.universe_description or "").strip() or build_universe_description(tags)
    await ev.decision(
        f"{side} universe: {desc}",
        f"{len(tag_ids)} tag(s) from {source}",
        tag_ids=tag_ids,
        source=source,
    )
    return Universe(side=side, description=desc, tag_ids=tag_ids, size=UNIVERSE_NOMINAL)


async def _finalize_side(
    side: Side, party: Party, d: SideDecision, tc: ToolContext, ev: NodeEvents, fallback: bool
) -> tuple[ResolvedBrand, ProxyResolution | None, Universe | None]:
    await _ensure_search(side, party, tc, ev)
    keys = {slugify(x) for x in [*party.marks, party.name] if x}
    side_searches = [(q, ents) for q, ents in tc.searches if slugify(q) in keys]
    candidates = _dedupe(
        [e.name for _, ents in side_searches for e in ents] + d.candidates_considered
    )

    entity: Entity | None = None
    if d.entity_id:
        entity = tc.entities.get(d.entity_id)
        if entity is None:
            await ev.warning(
                f"{side}: entity {d.entity_id} was not returned by any search; ignored"
            )
    elif fallback:
        first = next((ents[0] for _, ents in side_searches if ents), None)
        if first is not None:
            entity = first
            await ev.warning(
                f"{side}: no model decision; code took the first search hit", first.name
            )

    query = d.query or (side_searches[0][0] if side_searches else (party.marks or [party.name])[0])
    brand = ResolvedBrand(
        side=side,
        query=query,
        entity_id=entity.entity_id if entity else None,
        entity_name=entity.name if entity else None,
        popularity=entity.popularity if entity else None,
        candidates_considered=candidates,
        disambiguation_note=d.disambiguation_note,
    )
    if entity is not None:
        await ev.decision(
            f"{side}: {party.name} → {entity.name}",
            d.disambiguation_note,
            entity_id=entity.entity_id,
            candidates_considered=candidates,
        )
        proxy = None
    else:
        await ev.decision(
            f"{side}: {party.name} not found in Qloo → proxy path",
            f"candidates considered: {', '.join(candidates) or 'none'}",
            candidates_considered=candidates,
        )
        proxy = await _proxy(side, party, d, tc, ev)
    universe = await _universe(side, party, d, entity, proxy, tc, ev)
    return brand, proxy, universe


def _payload(ex: Extraction) -> str:
    def side(p: Party) -> dict[str, Any]:
        return {"name": p.name, "marks": p.marks, "goods": p.goods, "channels": p.channels}

    return to_json({"senior": side(ex.senior), "junior": side(ex.junior)})


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "resolve")
    ex: Extraction = state["extraction"]
    tc = ctx.tools
    model = ctx.model()
    messages = [
        SystemMessage(load_prompt("resolve")),
        HumanMessage(f"PARTIES:\n{_payload(ex)}{instruction_block(state)}"),
    ]
    calls = await run_tool_loop(
        model, make_tools(tc, RESOLVE_TOOLS), messages, max_calls=MAX_CALLS, ev=ev
    )
    fallback = False
    try:
        decision = await ainvoke_structured(
            model,
            ResolveDecision,
            [
                *messages,
                HumanMessage(
                    "Tool phase over. Return your final resolution for both sides. Use only "
                    "entity and tag ids that appeared in tool results above."
                ),
            ],
        )
    except Exception as exc:  # noqa: BLE001 — code fallbacks below still produce a Resolution
        await ev.warning("Resolution decision failed; code fallbacks apply", repr(exc))
        decision = ResolveDecision(senior=SideDecision(), junior=SideDecision())
        fallback = True

    s_brand, s_proxy, s_uni = await _finalize_side(
        "senior", ex.senior, decision.senior, tc, ev, fallback
    )
    j_brand, j_proxy, j_uni = await _finalize_side(
        "junior", ex.junior, decision.junior, tc, ev, fallback
    )
    resolution = Resolution(
        senior=s_brand,
        junior=j_brand,
        senior_proxy=s_proxy,
        junior_proxy=j_proxy,
        universes=[u for u in (s_uni, j_uni) if u is not None],
    )
    await ev.note(f"{calls} model tool call(s), {len(tc.queries)} Qloo queries so far")
    return {"resolution": resolution}
