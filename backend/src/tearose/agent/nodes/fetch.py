"""fetch: resolution + routing -> RawData. The agentic core, fenced in by code.

The model decides order and when to stop (tool loop, max 20 calls). Code then runs a
completeness check (`missing()`) and feeds the gaps back to the model up to 2 times; anything
still missing is fetched by code directly, so the scoring input never depends on the model
being diligent. The empty-result retry policy lives in ToolContext.insights_entities.

Per overlap direction the plan also holds one direct affinity lookup per target
(filter.results.entities, same seeds and filter): code-only, run after the paging, so the
scorer can report a censored rank together with the target's affinity ratio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from tearose.agent.nodes.base import (
    NodeEvents,
    RunContext,
    instruction_block,
    load_prompt,
    run_tool_loop,
    to_json,
)
from tearose.agent.tools import MAX_PAGES, ToolContext, make_tools
from tearose.schemas import (
    ProxyResolution,
    Resolution,
    ResolvedBrand,
    RoutingDecision,
    Universe,
)
from tearose.scoring.raw import DirectionalPeers, RawData

MAX_CALLS = 20
FEEDBACK_ROUNDS = 2
MAX_CODE_CALLS = 16


@dataclass
class Need:
    key: str
    text: str
    tool: str
    args: dict[str, Any]
    code_only: bool = False  # no model tool for it: code runs it after the model's loop


@dataclass
class Plan:
    analyses: set[str]
    senior_seeds: list[str] = field(default_factory=list)
    junior_seeds: list[str] = field(default_factory=list)
    senior_universe: Universe | None = None
    junior_universe: Universe | None = None


def seeds_for(brand: ResolvedBrand, proxy: ProxyResolution | None) -> list[str]:
    if brand.entity_id:
        return [brand.entity_id]
    return list(proxy.comparator_brand_ids) if proxy else []


def make_plan(resolution: Resolution, routing: RoutingDecision) -> Plan:
    unis = {u.side: u for u in resolution.universes}
    return Plan(
        analyses=set(routing.analyses),
        senior_seeds=seeds_for(resolution.senior, resolution.senior_proxy),
        junior_seeds=seeds_for(resolution.junior, resolution.junior_proxy),
        senior_universe=unis.get("senior"),
        junior_universe=unis.get("junior"),
    )


def _directions(plan: Plan) -> list[tuple[str, list[str], Universe | None, list[str]]]:
    """(label, seeds, other side's universe, targets) for both overlap directions."""
    return [
        ("senior→junior", plan.senior_seeds, plan.junior_universe, plan.junior_seeds),
        ("junior→senior", plan.junior_seeds, plan.senior_universe, plan.senior_seeds),
    ]


def _pending_affinities(
    tc: ToolContext, seeds: list[str], uni: Universe, targets: list[str]
) -> list[str]:
    """Targets whose direct affinity lookup is still missing for this direction (none once the
    paging came back empty: without a top-ranked brand there is no ratio to compute)."""
    key = tc.resolve_filter(seeds, uni.tag_ids)
    if key in tc.gave_up or (tuple(seeds), tuple(uni.tag_ids)) in tc.gave_up:
        return []
    ents, pages, _ = tc.concat_pages(key)
    if pages and not ents:
        return []
    done = {t for (s, f, t) in tc.target_affs if s == key[0] and f == key[1]}
    return [t for t in dict.fromkeys(targets) if t and t not in done]


def missing(plan: Plan, tc: ToolContext) -> list[Need]:
    """Everything the routed analyses still need, as concrete tool calls. Code-only needs
    (direct target affinities) come last so the paging they depend on runs first."""
    needs: list[Need] = []
    late: list[Need] = []
    s, j = plan.senior_seeds, plan.junior_seeds
    if "overlap" in plan.analyses:
        for label, seeds, uni, targets in _directions(plan):
            if not seeds or uni is None:
                continue
            key = tc.resolve_filter(seeds, uni.tag_ids)
            if key in tc.gave_up or (tuple(seeds), tuple(uni.tag_ids)) in tc.gave_up:
                continue
            ents, pages, exhausted = tc.concat_pages(key)
            found = bool(targets) and all(t in {e.entity_id for e in ents} for t in targets)
            if pages == 0 or (not found and not exhausted and pages < MAX_PAGES):
                page = pages + 1
                needs.append(
                    Need(
                        f"overlap:{label}",
                        f"Overlap {label}: page {page} of brands in the {uni.description} "
                        f"universe" + (" (targets not found yet)" if pages else ""),
                        "qloo_insights_entities",
                        {"seed_entity_ids": seeds, "filter_tags": uni.tag_ids, "page": page},
                    )
                )
            pending = _pending_affinities(tc, seeds, uni, targets)
            if pending:
                late.append(
                    Need(
                        f"affinity:{label}",
                        f"Overlap {label}: direct affinity of {len(pending)} target(s) to the "
                        "seed audience (works beyond the paged depth)",
                        "qloo_target_affinity",
                        {
                            "seed_entity_ids": seeds,
                            "target_entity_ids": pending,
                            "filter_tags": uni.tag_ids,
                        },
                        code_only=True,
                    )  # fmt: skip
                )
        if s and j and (tuple(s), tuple(j)) not in tc.compares:
            needs.append(
                Need(
                    "compare",
                    "Compare senior vs junior audiences",
                    "qloo_compare",
                    {"a_entity_ids": s, "b_entity_ids": j},
                )  # fmt: skip
            )
    if "bridging" in plan.analyses and s and tuple(s) not in tc.seed_tags:
        needs.append(
            Need(
                "bridging",
                "Senior audience taste tags (bridging)",
                "qloo_insights_tags",
                {"seed_entity_ids": s},
            )  # fmt: skip
        )
    if "fame" in plan.analyses:
        if s and tuple(s) not in tc.demos:
            needs.append(Need("demo:senior", "Senior demographics", "qloo_demographics",
                              {"seed_entity_ids": s}))  # fmt: skip
        if j and tuple(j) not in tc.demos:
            needs.append(Need("demo:junior", "Junior demographics", "qloo_demographics",
                              {"seed_entity_ids": j}))  # fmt: skip
    heat_sides = []
    if "fame" in plan.analyses or "zone" in plan.analyses:
        heat_sides.append(("senior", s))
    if "zone" in plan.analyses:
        heat_sides.append(("junior", j))
    for side, seeds in heat_sides:
        if seeds and (tuple(seeds), None) not in tc.heatmaps:
            needs.append(Need(f"heatmap:{side}", f"{side.capitalize()} national heatmap",
                              "qloo_heatmap", {"seed_entity_ids": seeds}))  # fmt: skip
    return needs + late


def for_model(needs: list[Need]) -> list[Need]:
    return [n for n in needs if not n.code_only]


async def execute(tc: ToolContext, need: Need) -> None:
    a = need.args
    if need.tool == "qloo_insights_entities":
        await tc.insights_entities(a["seed_entity_ids"], a["filter_tags"], a["page"])
    elif need.tool == "qloo_compare":
        await tc.compare(a["a_entity_ids"], a["b_entity_ids"])
    elif need.tool == "qloo_insights_tags":
        await tc.insights_tags(a["seed_entity_ids"])
    elif need.tool == "qloo_demographics":
        await tc.demographics(a["seed_entity_ids"])
    elif need.tool == "qloo_heatmap":
        await tc.heatmap(a["seed_entity_ids"])
    elif need.tool == "qloo_target_affinity":
        key = tc.resolve_filter(a["seed_entity_ids"], a["filter_tags"])  # after any widening
        for t in a["target_entity_ids"]:
            await tc.target_affinity(a["seed_entity_ids"], t, list(key[1]))
    else:  # pragma: no cover — missing() only emits the tools above
        raise ValueError(need.tool)


def _peers(
    tc: ToolContext, seeds: list[str], uni: Universe | None, targets: list[str]
) -> DirectionalPeers | None:
    if not seeds or uni is None:
        return None
    key = tc.resolve_filter(seeds, uni.tag_ids)
    ents, pages, exhausted = tc.concat_pages(key)
    if pages == 0:
        return None
    desc = uni.description
    if list(key[1]) != list(uni.tag_ids):
        desc += f" (widened to {key[1][0]} after an empty result)"
    gave_up = key in tc.gave_up or (tuple(seeds), tuple(uni.tag_ids)) in tc.gave_up
    return DirectionalPeers(
        seed_entity_ids=list(seeds),
        universe_tag_ids=list(uni.tag_ids),
        universe_description=desc,
        entities=ents,
        pages_fetched=pages,
        exhausted=exhausted,
        gave_up=gave_up,
        filter_tag_ids_used=list(key[1]),
        target_affinities={
            t: tc.target_affs[(key[0], key[1], t)]
            for t in targets
            if (key[0], key[1], t) in tc.target_affs
        },
    )


def assemble(plan: Plan, resolution: Resolution, tc: ToolContext) -> RawData:
    s, j = plan.senior_seeds, plan.junior_seeds
    raw = RawData(
        used_proxy_senior=resolution.senior.entity_id is None,
        used_proxy_junior=resolution.junior.entity_id is None,
    )
    notes: list[str] = []
    if "overlap" in plan.analyses:
        raw.senior_seed_junior_universe = _peers(tc, s, plan.junior_universe, j)
        raw.junior_seed_senior_universe = _peers(tc, j, plan.senior_universe, s)
        raw.junior_target_entity_ids = list(j)
        raw.senior_target_entity_ids = list(s)
        raw.compare = tc.compares.get((tuple(s), tuple(j)))
        for label, seeds, uni, _ in _directions(plan):
            if not seeds:
                notes.append(f"Overlap {label} not computable: no seed brand on that side.")
            elif uni is None:
                notes.append(f"Overlap {label} not computable: no category universe.")
    if "bridging" in plan.analyses:
        raw.senior_tags = list(tc.seed_tags.get(tuple(s), []))
        raw.junior_category_tag_ids = (
            list(plan.junior_universe.tag_ids) if plan.junior_universe else []
        )
    if "fame" in plan.analyses:
        raw.senior_demographics = tc.demos.get(tuple(s))
        raw.junior_demographics = tc.demos.get(tuple(j))
        raw.senior_popularity = resolution.senior.popularity
        raw.junior_popularity = resolution.junior.popularity
        raw.senior_heatmap_national = list(tc.heatmaps.get((tuple(s), None), []))
    if "zone" in plan.analyses:
        raw.senior_heatmap = list(tc.heatmaps.get((tuple(s), None), []))
        raw.junior_heatmap = list(tc.heatmaps.get((tuple(j), None), []))
    raw.notes = [*tc.notes, *notes]
    return raw


def _sized_universes(resolution: Resolution, raw: RawData) -> Resolution:
    """When a direction exhausted the universe, its true size is the number of brands seen."""
    by_side = {
        "junior": raw.senior_seed_junior_universe,
        "senior": raw.junior_seed_senior_universe,
    }
    unis = []
    for u in resolution.universes:
        peers = by_side.get(u.side)
        if peers is not None and peers.exhausted and peers.entities:
            u = u.model_copy(update={"size": len(peers.entities)})
        unis.append(u)
    return resolution.model_copy(update={"universes": unis})


def _payload(plan: Plan, tc: ToolContext, needs: list[Need]) -> str:
    def named(ids: list[str]) -> list[dict[str, str]]:
        return [{"id": i, "name": tc.names.get(i, i)} for i in ids]

    return to_json(
        {
            "analyses": sorted(plan.analyses),
            "senior_seeds": named(plan.senior_seeds),
            "junior_seeds": named(plan.junior_seeds),
            "senior_universe": plan.senior_universe.model_dump() if plan.senior_universe else None,
            "junior_universe": plan.junior_universe.model_dump() if plan.junior_universe else None,
            "checklist": [
                {"item": n.text, "tool": n.tool, "args": n.args} for n in for_model(needs)
            ],
        }
    )


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "fetch")
    tc = ctx.tools
    resolution: Resolution = state["resolution"]
    plan = make_plan(resolution, state["routing"])
    tc.targets = {i: "junior" for i in plan.junior_seeds} | {i: "senior" for i in plan.senior_seeds}
    needs = missing(plan, tc)
    await ev.decision(
        f"Data plan: {len(needs)} item(s) for {', '.join(sorted(plan.analyses))}",
        None,
        checklist=[n.text for n in needs],
    )

    tools = make_tools(tc)
    model = ctx.model()
    messages = [
        SystemMessage(load_prompt("fetch")),
        HumanMessage(f"PLAN:\n{_payload(plan, tc, needs)}{instruction_block(state)}"),
    ]
    calls = await run_tool_loop(model, tools, messages, max_calls=MAX_CALLS, ev=ev)
    for rnd in range(1, FEEDBACK_ROUNDS + 1):
        needs = for_model(missing(plan, tc))
        if not needs or calls >= MAX_CALLS:
            break
        await ev.note(
            f"Completeness check {rnd}: {len(needs)} item(s) still missing",
            "; ".join(n.text for n in needs),
        )
        messages.append(
            HumanMessage(
                "Completeness check — still missing:\n"
                + "\n".join(f"- {n.text}: {n.tool} {to_json(n.args)}" for n in needs)
                + "\nFetch these now, then stop."
            )
        )
        calls = await run_tool_loop(model, tools, messages, max_calls=MAX_CALLS, ev=ev, used=calls)

    for _ in range(MAX_CODE_CALLS):
        needs = missing(plan, tc)
        if not needs:
            break
        need = needs[0]
        await ev.decision(f"Code fallback: {need.text}", None, tool=need.tool, args=need.args)
        await execute(tc, need)
    else:
        if missing(plan, tc):
            tc.note("Fetch stopped at the code-fallback cap with items still missing.")

    raw = assemble(plan, resolution, tc)
    resolution = _sized_universes(resolution, raw)
    for n in raw.notes:
        await ev.note("Data note", n)
    await ev.decision(
        f"Fetched {len(tc.queries)} Qloo queries this run ({calls} by the model)",
        None,
        model_calls=calls,
        notes=raw.notes,
    )
    return {"raw": raw, "resolution": resolution}
