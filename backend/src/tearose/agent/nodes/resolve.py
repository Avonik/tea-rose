"""resolve: parties -> Resolution (tool loop + mechanical validation in code).

The model searches, disambiguates and proposes; code enforces the rules:
- an entity id counts only if a /search call returned it; the model is the judge of hit vs
  miss (no entity id = miss = proxy path; code never takes "the first hit"). A pick whose name
  is not similar to the party's marks/name is kept but flagged (name check in the
  disambiguation note and the trace); the same entity on both sides makes the junior a miss;
- on the proxy path the model picks up to 3 nodes of Qloo's brand taxonomy
  (urn:tag:genre:brand, harvested once per client) with a fit label exact|partial|nearest; code
  validates the ids and, if none is valid, maps the goods phrase itself (map_goods_phrase). Only
  when the taxonomy is unavailable or nothing maps does the old free-text path run: the goods
  phrase VERBATIM to /v2/tags, one shorter phrase if empty, tags chosen from the returned menu;
- the stand-in (comparator) brands of a proxied side are chosen by the AGENT from a shortlist
  built in code (stand_in_shortlist: up to 10 brands of the chosen category, /v2/insights seeded
  by the other side's entity, or its stand-ins when it is proxied too, ordered by popularity,
  the other side's own brand removed by id and by normalised name). After the category decision
  the model gets the shortlist, picks 3 with a one-sentence `comparator_rationale`, and decides
  `measure_overlap` (is the category close enough to compare audiences at all) with a
  `fit_reason`. Code validates the picks against the shortlist and, with fewer than 2 valid
  picks, tops up by popularity (source "mixed"; "rule" when the model returned nothing usable).
  Code never overrules the measure_overlap call;
- universes use only tag ids that some Qloo response actually returned. A resolved brand's
  universe is its OWN category (scoring.universe.own_category_tags on the brand-genre tags of
  its /search result, source "entity own tags"); only a brand without such tags falls back to
  its top insights tags (source "insights tags (fallback)"), then to the model's choice and the
  goods phrase. Insights tags describe what the AUDIENCE likes, not what the brand is.
"""

from __future__ import annotations

import re
from typing import Any, Literal

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
from tearose.agent.tools import GENRE_BRAND_PREFIX, MAX_PAGES, ToolContext, make_tools
from tearose.qloo.client import GENRE_BRAND, INSIGHTS_MAX_TAKE
from tearose.qloo.fixtures import slugify
from tearose.qloo.models import Entity, Tag
from tearose.qloo.names import match_rule, name_ratio
from tearose.qloo.taxonomy import (
    NEAREST_NOTE,
    best_fit,
    load_brand_taxonomy,
    map_goods_phrase,
    taxonomy_menu,
)
from tearose.schemas import (
    Extraction,
    Party,
    ProxyResolution,
    Resolution,
    ResolvedBrand,
    Side,
    Universe,
)
from tearose.scoring.comparators import COMPARATOR_COUNT, rule_comparators
from tearose.scoring.universe import (
    INSIGHTS_FALLBACK_SOURCE,
    OWN_TAGS_SOURCE,
    build_universe_description,
    insights_universe_tags,
    own_category_tags,
    pick_category_tags,
)

MAX_CALLS = 16
SHORTLIST_SIZE = 10
MIN_AGENT_PICKS = 2  # fewer valid picks -> code tops up from the shortlist by popularity
MAX_PROXY_NODES = 3
LOW_NAME_SIMILARITY = 0.6
UNIVERSE_NOMINAL = MAX_PAGES * INSIGHTS_MAX_TAKE  # ranks considered per direction
RESOLVE_TOOLS = ("qloo_search", "qloo_tags_search", "qloo_insights_entities", "qloo_insights_tags")


class TaxonomyChoice(BaseModel):
    tag_id: str = Field(description="full urn:tag:genre:brand:... id of a taxonomy node")
    fit: Literal["exact", "partial", "nearest"] = Field(
        description="exact: the node names the goods; partial: related or broader; nearest: "
        "no node fits, this is the closest stand-in"
    )


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
    proxy_taxonomy_choices: list[TaxonomyChoice] = Field(
        default_factory=list, description="proxy path: up to 3 brand-taxonomy nodes with fit"
    )
    proxy_chosen_tag_ids: list[str] = Field(
        default_factory=list, description="only for the free-text tags fallback"
    )
    universe_description: str | None = None
    universe_tag_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class ResolveDecision(BaseModel):
    senior: SideDecision
    junior: SideDecision


class StandInDecision(BaseModel):
    """The agent's stand-in choice for one proxied side, made from the code-built shortlist."""

    picks: list[str] = Field(
        default_factory=list,
        description="entity_id of exactly 3 shortlist brands (fewer only if the list is shorter)",
    )
    comparator_rationale: str = Field(
        default="", description="one sentence: why these brands stand in for the party"
    )
    measure_overlap: bool = Field(
        default=True,
        description="false when the stand-in category is too far from the party's goods to "
        "compare audiences at all",
    )
    fit_reason: str | None = Field(
        default=None, description="one sentence on the category fit; required when false"
    )


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
    ids = set(tc.tags) | {n.tag_id for n in tc.taxonomy}
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


async def _taxonomy_choice(
    side: Side, phrase: str, d: SideDecision, tc: ToolContext, ev: NodeEvents
) -> tuple[dict[str, dict[str, Any]], list[str], str | None, str]:
    """Taxonomy path: (options, chosen ids, fit, how). Empty chosen = no taxonomy match."""
    by_id = {n.tag_id: n for n in tc.taxonomy}
    suggested = map_goods_phrase(phrase, tc.taxonomy)
    options: dict[str, dict[str, Any]] = {m.node.tag_id: m.as_dict() for m in suggested}
    fits: dict[str, str] = {}
    rejected: list[str] = []
    for c in d.proxy_taxonomy_choices:
        if c.tag_id in by_id and c.tag_id not in fits and len(fits) < MAX_PROXY_NODES:
            fits[c.tag_id] = c.fit
        elif c.tag_id not in by_id:
            rejected.append(c.tag_id)
    if rejected:
        await ev.warning(
            f"{side}: chosen categories not in Qloo's brand taxonomy were dropped",
            ", ".join(rejected),
        )
    how = "agent choice from the brand taxonomy"
    if not fits and suggested:
        fits = {m.node.tag_id: m.fit for m in suggested}
        how = "code mapping (map_goods_phrase); the model chose no valid taxonomy node"
        await ev.warning(
            f"{side}: no valid taxonomy choice from the model; code mapped the goods phrase",
            ", ".join(f"{options[t]['name']} ({f})" for t, f in fits.items()),
        )
    elif fits and suggested and not set(fits) & set(options):
        await ev.warning(
            f"{side}: taxonomy choice differs completely from the code mapping",
            f"agent: {list(fits)}; code: {list(options)}",
        )
    for tid, f in fits.items():
        n = by_id[tid]
        options.setdefault(tid, {"id": tid, "name": n.name, "path": n.path_label, "fit": f})
        options[tid] = {**options[tid], "fit": f}
        tc.tags.setdefault(tid, Tag(tag_id=tid, name=n.name, tag_type=GENRE_BRAND))
    return options, list(fits), best_fit(list(fits.values())), how


async def _free_text_choice(
    side: Side, phrase: str, d: SideDecision, tc: ToolContext, ev: NodeEvents
) -> tuple[dict[str, dict[str, Any]], list[str], str | None, str]:
    """Last resort: verbatim phrase to free-text /v2/tags (then one shorter phrase)."""

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
    menu: dict[str, Tag] = {}
    for _, tags in related:
        for t in tags:
            menu.setdefault(t.tag_id, t)
    chosen = [t for t in _dedupe(d.proxy_chosen_tag_ids) if t in menu]
    rejected = [t for t in d.proxy_chosen_tag_ids if t not in menu]
    if rejected:
        await ev.warning(
            f"{side}: chosen tags not on the returned menu were dropped", ", ".join(rejected)
        )
    heuristic = [t.tag_id for t in pick_category_tags(list(menu.values()), phrase)]
    if not chosen and menu:
        chosen = heuristic or [next(iter(menu))]
        await ev.warning(
            f"{side}: no valid tag choice from the model; code picked", ", ".join(chosen)
        )
    elif chosen and heuristic and not set(chosen) & set(heuristic):
        await ev.warning(
            f"{side}: tag choice differs completely from the keyword heuristic",
            f"agent: {chosen}; heuristic: {heuristic}",
        )
    fit = None
    if chosen:
        fit = "partial" if set(chosen) & set(heuristic) else "nearest"
    tried = "; ".join(
        f"{q!r} → {len(tags)} tag(s)" for q, tags in tc.tag_searches if (q, tags) in related
    )
    options = {
        t.tag_id: {"id": t.tag_id, "name": t.name, "type": t.tag_type} for t in menu.values()
    }
    return options, chosen, fit, f"free-text tag searches: {tried}" if tried else "free-text"


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

    options: dict[str, dict[str, Any]] = {}
    chosen: list[str] = []
    fit: str | None = None
    how = ""
    if tc.taxonomy:
        options, chosen, fit, how = await _taxonomy_choice(side, phrase, d, tc, ev)
        if not chosen:
            await ev.warning(
                f"{side}: goods phrase maps to no brand-taxonomy node; "
                "falling back to free-text /v2/tags",
                repr(phrase),
            )
    if not chosen:
        options, chosen, fit, how = await _free_text_choice(side, phrase, d, tc, ev)

    fit_note = NEAREST_NOTE if fit == "nearest" else None
    names = ", ".join(str(options[t]["name"]) for t in chosen if t in options)
    rationale = " ".join(
        x
        for x in (
            d.rationale.strip(),
            f"Category: {names} ({fit}; {how})." if chosen else f"No category ({how}).",
            f"Fit: {fit_note}." if fit_note else "",
        )
        if x
    )
    proxy = ProxyResolution(
        side=side,
        goods_phrase=phrase,
        tag_options=list(options.values()),
        chosen_tag_ids=chosen,
        fit=fit,  # type: ignore[arg-type]
        fit_note=fit_note,
        rationale=rationale or "Proxy path: brand not found in Qloo.",
    )
    await ev.decision(
        f"{side}: proxy via {len(chosen)} categor{'y' if len(chosen) == 1 else 'ies'} "
        f"({fit or 'no fit'}); the agent picks stand-ins from a shortlist next",
        fit_note or f"options: {', '.join(str(o['name']) for o in options.values()) or 'none'}",
        goods_phrase=phrase,
        tag_options=proxy.tag_options,
        chosen_tag_ids=chosen,
        fit=fit,
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
    code_tags: list[Tag] = []  # universe built in code: its description comes from these
    if proxy is not None:
        tag_ids, source = list(proxy.chosen_tag_ids), "proxy tags"
    else:
        own = own_category_tags(entity.tag_details) if entity is not None else []
        if not own and entity is not None:
            seed_tags = tc.seed_tags.get((entity.entity_id,))
            if seed_tags is None:
                try:
                    seed_tags, _ = await tc.insights_tags([entity.entity_id])
                except Exception as exc:  # noqa: BLE001 — later fallbacks still apply
                    await ev.warning(f"{side}: insights tags for the universe failed", repr(exc))
                    seed_tags = []
            own = insights_universe_tags(seed_tags)
            source = INSIGHTS_FALLBACK_SOURCE
        else:
            source = OWN_TAGS_SOURCE
        code_tags = own
        tag_ids = [t.tag_id for t in own]
        if own and d.universe_tag_ids and set(d.universe_tag_ids) != set(tag_ids):
            await ev.note(
                f"{side}: universe from {source}; the model's universe choice is not used",
                f"model: {d.universe_tag_ids}; code: {tag_ids}",
            )
        if not tag_ids:
            known = _known_tag_ids(tc)
            tag_ids = [t for t in _dedupe(d.universe_tag_ids) if t in known]
            unknown = [t for t in d.universe_tag_ids if t not in known]
            if unknown:
                await ev.warning(
                    f"{side}: universe tags never returned by Qloo were dropped", ", ".join(unknown)
                )
            source = "agent choice"
        if not tag_ids and party.goods and tc.taxonomy:
            mapped = map_goods_phrase(party.goods[0], tc.taxonomy)
            tag_ids = [m.node.tag_id for m in mapped]
            source = "code fallback (goods phrase → brand taxonomy)"
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
    if code_tags:
        desc = build_universe_description(code_tags)
    else:
        tags = [_tag_obj(tc, t) for t in tag_ids]
        desc = (d.universe_description or "").strip() or build_universe_description(tags)
    await ev.decision(
        f"{side} universe: {desc}",
        f"{len(tag_ids)} tag(s) from {source}",
        tag_ids=tag_ids,
        source=source,
    )
    return Universe(side=side, description=desc, tag_ids=tag_ids, size=UNIVERSE_NOMINAL)


def _other_names(other: ResolvedBrand, other_party: Party | None) -> list[str]:
    return [
        x
        for x in (
            other.entity_name,
            *((other_party.name, *other_party.marks) if other_party is not None else ()),
        )
        if x
    ]


def candidate_brief(e: Entity, tc: ToolContext) -> dict[str, Any]:
    """One shortlist row as the model and the records see it."""
    d: dict[str, Any] = {"entity_id": e.entity_id, "name": e.name, "popularity": e.popularity}
    desc = (e.properties or {}).get("description")
    if isinstance(desc, str) and desc.strip():
        d["description"] = desc.strip()[:200]
    if e.disambiguation:
        d["disambiguation"] = e.disambiguation
    cats = [tc._tag_label(t) for t in e.tags if t.startswith(GENRE_BRAND_PREFIX)]
    if cats:
        d["categories"] = cats[:6]
    return d


async def stand_in_shortlist(
    proxy: ProxyResolution,
    other: ResolvedBrand,
    other_proxy: ProxyResolution | None,
    other_party: Party | None,
    tc: ToolContext,
) -> tuple[list[Entity], list[str], list[str]]:
    """(shortlist, seeds, notes): up to SHORTLIST_SIZE brands of the proxied side's chosen
    category, /v2/insights filter.type=brand seeded by the other side's entity (or its
    stand-ins when it is proxied too), ordered by popularity. The other side's own brand (its
    entity id, and any brand whose normalised name equals its name or marks) is removed here,
    before the model sees the list. Nothing resolved on the other side gives ([], [], note)."""
    if other.entity_id:
        seeds = [other.entity_id]
    else:
        seeds = list(other_proxy.comparator_brand_ids) if other_proxy else []

    async def fetch(s: list[str], tags: list[str]) -> list[Entity]:
        return (await tc.insights_entities(s, tags, 1))[0]

    picked, notes = await rule_comparators(
        fetch,
        seeds,
        list(proxy.chosen_tag_ids),
        exclude=[other.entity_id] if other.entity_id else [],
        n=SHORTLIST_SIZE,
        exclude_names=_other_names(other, other_party),
    )
    return picked, seeds, notes


async def _choose_stand_ins(
    side: Side,
    party: Party,
    proxy: ProxyResolution,
    shortlist: list[Entity],
    seeds: list[str],
    ex: Extraction,
    model: Any,
    tc: ToolContext,
    ev: NodeEvents,
) -> StandInDecision | None:
    """The agent's pick from the shortlist plus its overlap-fit call (None when it failed)."""
    cats = ", ".join(
        str(o.get("name")) for o in proxy.tag_options if o.get("id") in proxy.chosen_tag_ids
    )
    payload = {
        "side": side,
        "party": party.name,
        "marks": party.marks,
        "goods_phrase": proxy.goods_phrase,
        "chosen_category": cats or proxy.chosen_tag_ids,
        "category_fit_label": proxy.fit,
        "shortlist_seeded_by": [tc.names.get(s, s) for s in seeds],
        "shortlist": [candidate_brief(e, tc) for e in shortlist],
    }
    messages = [
        SystemMessage(load_prompt("resolve")),
        HumanMessage(
            f"PARTIES:\n{_payload(ex)}\n\nSTAND-IN SHORTLIST (step 3; built in code, the other "
            f"side already removed):\n{to_json(payload)}\n\nPick exactly "
            f"{min(COMPARATOR_COUNT, len(shortlist))} stand-ins by `entity_id` from this list "
            "with one sentence of `comparator_rationale`, and decide `measure_overlap` with a "
            "one-sentence `fit_reason`."
        ),
    ]
    try:
        return await ainvoke_structured(model, StandInDecision, messages)
    except Exception as exc:  # noqa: BLE001 — code picks by popularity instead
        await ev.warning(f"{side}: stand-in choice failed; code picks by popularity", repr(exc))
        return None


_SOURCE_TEXT = {
    "agent": "chosen by the agent",
    "mixed": "chosen by the agent, topped up by code by popularity",
    "rule": "picked by code by popularity (the agent returned no usable pick)",
}


async def _stand_ins(
    side: Side,
    party: Party,
    proxy: ProxyResolution,
    other: ResolvedBrand,
    other_proxy: ProxyResolution | None,
    other_party: Party | None,
    ex: Extraction,
    model: Any,
    tc: ToolContext,
    ev: NodeEvents,
) -> ProxyResolution:
    """Shortlist in code -> the agent picks 3 with a reason and decides measure_overlap ->
    code validates (picks must be on the shortlist; fewer than 2 valid picks are topped up by
    popularity) and records everything on the ProxyResolution. Code never overrules the
    agent's measure_overlap call."""
    if not proxy.chosen_tag_ids:
        await ev.warning(f"{side}: no usable comparator brands; this side cannot seed queries")
        return proxy
    try:
        shortlist, seeds, notes = await stand_in_shortlist(
            proxy, other, other_proxy, other_party, tc
        )
    except Exception as exc:  # noqa: BLE001 — the side stays without stand-ins
        shortlist, seeds, notes = [], [], [f"comparators: shortlist query failed ({exc!r})."]
    briefs = [candidate_brief(e, tc) for e in shortlist]
    await ev.decision(
        f"{side}: stand-in shortlist of {len(shortlist)} brand(s)",
        " ".join(notes) or ", ".join(e.name for e in shortlist) or None,
        shortlist=briefs,
        seeds=seeds,
        filter_tags=list(proxy.chosen_tag_ids),
    )
    if not shortlist:
        detail = " ".join(notes) or "the shortlist query returned no brands"
        await ev.warning(
            f"{side}: no usable comparator brands; this side cannot seed queries", detail
        )
        return proxy.model_copy(update={"stand_in_candidates": briefs})

    decision = await _choose_stand_ins(side, party, proxy, shortlist, seeds, ex, model, tc, ev)
    by_id = {e.entity_id: e for e in shortlist}
    raw_picks = list(decision.picks) if decision else []
    valid = [p for p in _dedupe(raw_picks) if p in by_id][:COMPARATOR_COUNT]
    invalid = [p for p in raw_picks if p not in by_id]
    if invalid:
        await ev.warning(
            f"{side}: stand-in picks not on the shortlist were dropped", ", ".join(invalid)
        )
    picked = [by_id[p] for p in valid]
    topped: list[Entity] = []
    if len(valid) < MIN_AGENT_PICKS:
        rest = [e for e in shortlist if e.entity_id not in valid]  # already by popularity
        topped = rest[: COMPARATOR_COUNT - len(valid)]
        picked += topped
    source: Literal["agent", "rule", "mixed"] = (
        "rule" if not valid else ("mixed" if topped else "agent")
    )
    reason = ((decision.comparator_rationale if decision else "") or "").strip()
    if topped:
        await ev.note(
            f"{side}: {len(valid)} valid stand-in pick(s) from the agent; code topped up by "
            f"popularity: {', '.join(e.name for e in topped)}"
        )
    measure = decision.measure_overlap if decision else True
    fit_reason = ((decision.fit_reason if decision else None) or "").strip() or None
    if not measure and not fit_reason:
        fit_reason = (
            f"the agent judged the stand-in category too far from {party.name}'s goods "
            f"({proxy.goods_phrase!r}) to compare audiences"
        )
    names = ", ".join(e.name for e in picked)
    who = _SOURCE_TEXT[source]
    await ev.decision(
        f"{side}: stand-ins {names} ({who})",
        reason or None,
        comparators=[e.name for e in picked],
        comparator_ids=[e.entity_id for e in picked],
        popularity=[e.popularity for e in picked],
        comparator_source=source,
        comparator_rationale=reason or None,
        measure_overlap=measure,
        fit_reason=fit_reason,
    )
    if not measure:
        await ev.decision(
            f"{side}: the agent judged the stand-in category too far; overlap is skipped",
            fit_reason,
            measure_overlap=False,
        )
    extra = f" Stand-ins {who}: {names}" + (f" ({reason})." if reason else ".")
    if not measure:
        extra += f" Overlap not measured: {fit_reason}"
    return proxy.model_copy(
        update={
            "comparator_brand_ids": [e.entity_id for e in picked],
            "comparator_brand_names": [e.name for e in picked],
            "comparator_source": source,
            "stand_in_candidates": briefs,
            "comparator_rationale": reason or None,
            "measure_overlap": measure,
            "fit_reason": fit_reason,
            "rationale": f"{proxy.rationale}{extra}",
        }
    )


def _name_check(party: Party, entity: Entity) -> tuple[str, float]:
    """(best rule, best difflib ratio) of the entity name against the party's marks and name."""
    names = [x for x in [*party.marks, party.name] if x and x.strip()]
    rules = [match_rule(n, entity.name) for n in names]
    rule = next((r for r in rules if r == "exact"), None) or next(
        (r for r in rules if r.startswith("fuzzy")), "miss"
    )
    ratio = max((name_ratio(n, entity.name) for n in names), default=0.0)
    return rule, ratio


async def _finalize_side(
    side: Side,
    party: Party,
    d: SideDecision,
    tc: ToolContext,
    ev: NodeEvents,
    avoid_entity_id: str | None = None,
) -> tuple[ResolvedBrand, ProxyResolution | None, Universe | None]:
    await _ensure_search(side, party, tc, ev)
    keys = {slugify(x) for x in [*party.marks, party.name] if x}
    side_searches = [(q, ents) for q, ents in tc.searches if slugify(q) in keys]
    candidates = _dedupe(
        [e.name for _, ents in side_searches for e in ents] + d.candidates_considered
    )

    entity: Entity | None = None
    note = d.disambiguation_note
    if d.entity_id:
        entity = tc.entities.get(d.entity_id)
        if entity is None:
            await ev.warning(
                f"{side}: entity {d.entity_id} was not returned by any search; ignored"
            )
    if entity is not None and avoid_entity_id and entity.entity_id == avoid_entity_id:
        await ev.warning(
            f"{side}: picked the other side's entity ({entity.name}); treated as not found"
        )
        entity = None
    name_rule: str | None = None
    if entity is not None:
        name_rule, ratio = _name_check(party, entity)
        if name_rule == "miss":
            flag = (
                f"Name check: {entity.name!r} is not a name match for "
                f"{(party.marks or [party.name])[0]!r} (similarity {ratio:.2f}); "
                "kept as the model's judgement."
            )
            note = f"{note} {flag}".strip() if note else flag
            if ratio < LOW_NAME_SIMILARITY:
                await ev.warning(f"{side}: low name similarity for the chosen entity", flag)

    query = d.query or (side_searches[0][0] if side_searches else (party.marks or [party.name])[0])
    brand = ResolvedBrand(
        side=side,
        query=query,
        entity_id=entity.entity_id if entity else None,
        entity_name=entity.name if entity else None,
        popularity=entity.popularity if entity else None,
        candidates_considered=candidates,
        disambiguation_note=note,
    )
    if entity is not None:
        await ev.decision(
            f"{side}: {party.name} → {entity.name}",
            note,
            entity_id=entity.entity_id,
            candidates_considered=candidates,
            name_match=name_rule,
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


def _taxonomy_block(ex: Extraction, tc: ToolContext) -> str:
    """Brand taxonomy (path = name, one per line) plus code's suggestions per goods phrase."""
    if not tc.taxonomy:
        return (
            "\n\nBRAND TAXONOMY: unavailable this run; on the proxy path use qloo_tags_search "
            "with the goods phrase verbatim."
        )
    sugg: dict[str, Any] = {}
    for p in (ex.senior, ex.junior):
        if p.goods:
            sugg[p.side] = [
                {"tag_id": m.node.tag_id, "path": m.node.path_label, "fit": m.fit}
                for m in map_goods_phrase(p.goods[0], tc.taxonomy)
            ]
    lines = "\n".join(taxonomy_menu(tc.taxonomy))
    return (
        f"\n\nBRAND TAXONOMY ({len(tc.taxonomy)} nodes; tag_id = {GENRE_BRAND}:"
        "<path with ':' instead of '/'>):\n"
        f"{lines}\n\nCODE SUGGESTIONS (keyword mapping of goods[0]; you decide):\n"
        f"{to_json(sugg)}"
    )


async def _load_taxonomy(ctx: RunContext, ev: NodeEvents) -> None:
    tc = ctx.tools
    if tc.taxonomy:
        return
    try:
        tc.taxonomy = await load_brand_taxonomy(ctx.client)
    except Exception as exc:  # noqa: BLE001 — the free-text tags path still works
        await ev.warning("Brand taxonomy unavailable; proxy path falls back to /v2/tags", repr(exc))
        return
    if tc.taxonomy:
        await ev.note(
            f"Brand taxonomy loaded: {len(tc.taxonomy)} urn:tag:genre:brand nodes",
            "26 letter queries to /v2/tags (cached), memoised per process",
        )


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "resolve")
    ex: Extraction = state["extraction"]
    tc = ctx.tools
    model = ctx.model()
    await _load_taxonomy(ctx, ev)
    messages = [
        SystemMessage(load_prompt("resolve")),
        HumanMessage(
            f"PARTIES:\n{_payload(ex)}{_taxonomy_block(ex, tc)}{instruction_block(state)}"
        ),
    ]
    calls = await run_tool_loop(
        model, make_tools(tc, RESOLVE_TOOLS), messages, max_calls=MAX_CALLS, ev=ev
    )
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

    s_brand, s_proxy, s_uni = await _finalize_side("senior", ex.senior, decision.senior, tc, ev)
    j_brand, j_proxy, j_uni = await _finalize_side(
        "junior", ex.junior, decision.junior, tc, ev, avoid_entity_id=s_brand.entity_id
    )
    if s_proxy is not None:
        s_proxy = await _stand_ins(
            "senior", ex.senior, s_proxy, j_brand, j_proxy, ex.junior, ex, model, tc, ev
        )
    if j_proxy is not None:
        j_proxy = await _stand_ins(
            "junior", ex.junior, j_proxy, s_brand, s_proxy, ex.senior, ex, model, tc, ev
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
