"""Step 3, `score`: resolved.json -> scores.json. Qloo: insights only; numbers from scoring/.

Per case with at least one side resolved (the other resolved or proxied):

- Seeds: a resolved side seeds with its entity id. A proxied side resolved by the agent resolver
  (harness v3) seeds with the comparators the product's resolve node chose, as the product's
  fetch node does (`comparator_source` "agent"). Otherwise (rule resolver, or the agent kept
  none; `comparator_source` "rule") a proxied side seeds with COMPARATORS: the
  brands returned by insights entities seeded by the OTHER side's entity and filtered to the
  proxy tags (page 1, take 50), top 3 by POPULARITY (ties by rank), excluding the seed itself.
  Deviation from "top 3 by rank", on purpose: picking the brands that rank highest for the
  senior would make the senior->junior rank 1-3 by construction (percentile ~0.95 for every
  proxy case). Popularity is a property of the brand, not of the senior's audience, so it
  measures "category leaders" without peeking at the outcome. Proxy cases are still reported
  separately from the primary metric.
- Overlap, both directions, exactly as the agent's fetch node: seed = one side's seeds,
  filter_tags = the other side's universe tags, filter.type = the TARGET side's entity type
  (resolved.json `type`, default brand; e.g. Mattel -> Aqua ranks Aqua among artists),
  take 50, page until every target is found or 3 pages; an empty first page with several tags
  is retried once with the broadest tag (fewest path segments). Targets = the other side's
  entity id or its comparators.
  `overlap_evidence(raw, resolution)` turns that into percentiles.
- Harness v2: after paging, each target's affinity is looked up directly (one /v2/insights call
  per target with filter.results.entities=<target>, same seeds, filter.tags and filter.type).
  A target beyond the scanned depth is reported as CENSORED (rank and rank percentile None, v1
  counted it as percentile 0); the second signal, affinity_ratio = target affinity / affinity
  of the top-ranked brand, is available whenever the lookup succeeds.
- Fame (senior only, and only when the senior is a resolved brand): demographics + national
  heatmap (location_query "United States"; empty -> no coverage) -> `fame_evidence(raw)`.
"""

from __future__ import annotations

from typing import Any

from tearose.eval.backtest import HARNESS_VERSION
from tearose.eval.backtest.common import DEFAULT_ENTITY_TYPE, Recorder, entity_urn
from tearose.qloo.client import INSIGHTS_MAX_TAKE
from tearose.qloo.models import Demographics, Entity
from tearose.schemas import ProxyResolution, Resolution, ResolvedBrand
from tearose.scoring.raw import DirectionalPeers, RawData
from tearose.scoring.score import fame_evidence, overlap_evidence

MAX_PAGES = 3
COMPARATORS = 3
HEATMAP_LOCATION = "United States"
COMPARATOR_RULE = (
    "top 3 by popularity (ties by rank) among brands seeded by the other side's entity and "
    "filtered to the proxy tags; not by rank, to avoid a built-in senior->junior overlap"
)


def broadest_tag(tag_ids: list[str]) -> str:
    """Fewest path segments wins (same rule as the agent's ToolContext)."""
    return min(tag_ids, key=lambda t: (t.count(":"), len(t)))


async def fetch_direction(
    rec: Recorder,
    seeds: list[str],
    filter_tags: list[str],
    targets: list[str],
    label: str,
    result_type: str = "urn:entity:brand",
) -> tuple[DirectionalPeers | None, list[str]]:
    notes: list[str] = []
    if not seeds:
        return None, [f"{label}: no seed ids."]
    if not filter_tags:
        return None, [f"{label}: the other side has no universe tags; direction skipped."]
    used = list(filter_tags)
    ents: list[Entity] = []
    pages = 0
    exhausted = False
    gave_up = False
    for page in range(1, MAX_PAGES + 1):
        batch: list[Entity] = list(
            await rec.insights_entities(seeds, used, page, result_type=result_type)
        )
        if page == 1 and not batch and len(used) > 1:
            broad = broadest_tag(used)
            notes.append(f"{label}: empty with {len(used)} tags; retried with {broad}.")
            used = [broad]
            batch = list(await rec.insights_entities(seeds, used, page, result_type=result_type))
        pages = page
        ents.extend(batch)
        if page == 1 and not batch:
            gave_up = True
            notes.append(f"{label}: no brands returned for the filter; gave up.")
        if len(batch) < INSIGHTS_MAX_TAKE:
            exhausted = True
            break
        found = {e.entity_id for e in ents}
        if targets and all(t in found for t in targets):
            break
    ranked = [e.model_copy(update={"rank": i + 1}) for i, e in enumerate(ents)]
    target_affs: dict[str, float | None] = {}
    if ranked:  # no ranking, no top-1 affinity: a lookup could not be turned into a ratio
        for t in dict.fromkeys(targets):
            target_affs[t] = await rec.target_affinity(seeds, t, used, result_type)
    peers = DirectionalPeers(
        seed_entity_ids=list(seeds),
        universe_tag_ids=list(filter_tags),
        universe_description=", ".join(filter_tags),
        entities=ranked,
        pages_fetched=pages,
        exhausted=exhausted,
        gave_up=gave_up,
        filter_tag_ids_used=used,
        target_affinities=target_affs,
    )
    return peers, notes


async def comparators_for(
    rec: Recorder, other_entity_id: str, proxy_tags: list[str]
) -> tuple[list[Entity], list[str]]:
    batch: list[Entity] = list(await rec.insights_entities([other_entity_id], proxy_tags, 1))
    notes: list[str] = []
    if not batch and len(proxy_tags) > 1:
        broad = broadest_tag(proxy_tags)
        notes.append(f"comparators: empty with {len(proxy_tags)} tags; retried with {broad}.")
        batch = list(await rec.insights_entities([other_entity_id], [broad], 1))
    pool = [
        (e.popularity if e.popularity is not None else -1.0, i, e)
        for i, e in enumerate(batch)
        if e.entity_id != other_entity_id
    ]
    pool.sort(key=lambda t: (-t[0], t[1]))
    return [e for _, _, e in pool[:COMPARATORS]], notes


async def _add_fame_inputs(
    rec: Recorder, raw: RawData, senior_seeds: list[str], notes: list[str]
) -> None:
    demo: Demographics | None = await rec.demographics(senior_seeds)
    raw.senior_demographics = demo
    raw.senior_heatmap_national = list(await rec.heatmap(senior_seeds, HEATMAP_LOCATION))
    if not raw.senior_heatmap_national:
        notes.append("national heatmap empty: no coverage.")


def _apply_fame(
    out: dict[str, Any], raw: RawData, resolution: Resolution | None, notes: list[str]
) -> None:
    fame = fame_evidence(raw, resolution)
    out["breadth_score"] = fame.breadth_score
    out["heatmap_coverage"] = fame.heatmap_coverage
    out["senior_popularity"] = fame.popularity_percentile
    notes.extend(fame.notes)


def _side_brand(side: str, s: dict[str, Any]) -> ResolvedBrand:
    return ResolvedBrand(
        side=side,  # type: ignore[arg-type]
        query=s["query"],
        entity_id=s["entity_id"],
        entity_name=s["entity_name"],
        popularity=s["popularity"],
        candidates_considered=s["candidates_considered"],
    )


def _type_urn(s: dict[str, Any]) -> str:
    """filter.type when this side is the target: its resolved entity type (older resolved.json
    files: brand). A proxied side is represented by comparator BRANDS (proxy path unchanged),
    so its targets are brands whatever the pre-registered type."""
    if s.get("status") != "resolved":
        return entity_urn(DEFAULT_ENTITY_TYPE)
    return entity_urn(s.get("type") or DEFAULT_ENTITY_TYPE)


def _uni_tags(s: dict[str, Any]) -> list[str]:
    return list((s.get("universe") or {}).get("tag_ids") or [])


AGENT_COMPARATOR_RULE = (
    "the comparators the product's resolve node chose and validated (agent resolver), as the "
    "product's fetch node uses them"
)


def agent_comparators(case: dict[str, Any], s: dict[str, Any]) -> list[Entity]:
    """Agent resolver only: the node's comparator brands for a proxied side (empty otherwise)."""
    if case.get("resolver") != "agent":
        return []
    p = s.get("proxy") or {}
    ids = list(p.get("comparator_entity_ids") or [])
    names = list(p.get("comparator_entity_names") or [])
    pops = list(p.get("comparator_popularity") or [])
    return [
        Entity(
            entity_id=eid,
            name=names[i] if i < len(names) else eid,
            popularity=pops[i] if i < len(pops) else None,
        )
        for i, eid in enumerate(ids)
    ]


def pick_comparison(case: dict[str, Any]) -> dict[str, Any]:
    """Agent resolver only: per side, the agent's pick next to the name rule's pick."""
    if case.get("resolver") != "agent":
        return {}
    out: dict[str, Any] = {}
    for side in ("senior", "junior"):
        s = case[side]
        rp = s.get("rule_pick") or {}
        out[side] = {
            "agent": s.get("entity_name"),
            "rule": rp.get("entity_name"),
            "differs": s.get("agrees_with_rule") is False,
        }
    return {"pick_vs_rule": out, "resolver_error": case.get("error")}


async def score_case(rec: Recorder, case: dict[str, Any]) -> dict[str, Any]:
    sen, jun = case["senior"], case["junior"]
    out: dict[str, Any] = {
        "case_id": case["case_id"],
        "status": "unresolved",
        "symmetric_percentile": None,
        "symmetric_affinity_ratio": None,
        "senior_to_junior": None,
        "junior_to_senior": None,
        "breadth_score": None,
        "senior_popularity": sen.get("popularity"),
        "junior_popularity": jun.get("popularity"),
        "heatmap_coverage": None,
        "used_proxy": False,
        "proxy_sides": [],
        "comparators": {},
        "comparator_source": {},
        "notes": [],
        "queries": [],
        **pick_comparison(case),
    }
    notes: list[str] = out["notes"]
    statuses = (sen["status"], jun["status"])
    if "unresolved" in statuses or "resolved" not in statuses:
        notes.append(f"overlap not scorable: senior {statuses[0]}, junior {statuses[1]}.")
        if sen["status"] == "resolved":  # fame needs only the senior
            raw = RawData(senior_popularity=sen.get("popularity"))
            await _add_fame_inputs(rec, raw, [sen["entity_id"]], notes)
            _apply_fame(out, raw, None, notes)
        notes.extend(rec.take_notes())
        out["queries"] = rec.take_queries()
        return out

    seeds: dict[str, list[str]] = {}
    proxies: dict[str, ProxyResolution] = {}
    for side, s, other in (("senior", sen, jun), ("junior", jun, sen)):
        if s["status"] == "resolved":
            seeds[side] = [s["entity_id"]]
            continue
        comps, source = agent_comparators(case, s), "agent"
        rule_text = AGENT_COMPARATOR_RULE
        if not comps:
            comps, cnotes = await comparators_for(rec, other["entity_id"], _uni_tags(s))
            notes.extend(f"{side} {n}" for n in cnotes)
            source, rule_text = "rule", COMPARATOR_RULE
            if case.get("resolver") == "agent":
                notes.append(f"{side}: the agent kept no comparators; code rule used.")
        seeds[side] = [c.entity_id for c in comps]
        out["proxy_sides"].append(side)
        out["comparator_source"][side] = source
        out["comparators"][side] = {
            "source": source,
            "rule": rule_text,
            "ids": [c.entity_id for c in comps],
            "names": [c.name for c in comps],
            "popularity": [c.popularity for c in comps],
        }
        proxies[side] = ProxyResolution(
            side=side,  # type: ignore[arg-type]
            goods_phrase=s["proxy"]["goods_phrase"],
            tag_options=s["proxy"]["tag_options"],
            chosen_tag_ids=s["proxy"]["chosen_tag_ids"],
            comparator_brand_ids=[c.entity_id for c in comps],
            comparator_brand_names=[c.name for c in comps],
            rationale=f"Back-test proxy: {rule_text}.",
        )
        if comps:
            notes.append(
                f"{side} proxied by comparators: {', '.join(c.name for c in comps)} "
                f"(tags {', '.join(s['proxy']['chosen_tag_names'])})."
            )
        else:
            notes.append(f"{side} proxy found no comparator brands.")
    out["used_proxy"] = bool(proxies)

    s2j, n1 = await fetch_direction(
        rec, seeds["senior"], _uni_tags(jun), seeds["junior"], "senior->junior", _type_urn(jun)
    )
    j2s, n2 = await fetch_direction(
        rec, seeds["junior"], _uni_tags(sen), seeds["senior"], "junior->senior", _type_urn(sen)
    )
    notes.extend(n1 + n2)

    raw = RawData(
        senior_seed_junior_universe=s2j,
        junior_seed_senior_universe=j2s,
        junior_target_entity_ids=seeds["junior"],
        senior_target_entity_ids=seeds["senior"],
        senior_popularity=sen.get("popularity"),
        junior_popularity=jun.get("popularity"),
        used_proxy_senior="senior" in proxies,
        used_proxy_junior="junior" in proxies,
    )
    if sen["status"] == "resolved":
        await _add_fame_inputs(rec, raw, seeds["senior"], notes)
    resolution = Resolution(
        senior=_side_brand("senior", sen),
        junior=_side_brand("junior", jun),
        senior_proxy=proxies.get("senior"),
        junior_proxy=proxies.get("junior"),
    )
    ov = overlap_evidence(raw, resolution)
    notes.extend(ov.notes)
    out["symmetric_percentile"] = ov.symmetric_percentile
    out["symmetric_affinity_ratio"] = ov.symmetric_affinity_ratio
    for key, peers in (("senior_to_junior", s2j), ("junior_to_senior", j2s)):
        out[key] = {
            "rank": getattr(ov, f"{key}_rank"),
            "universe": getattr(ov, f"{key}_universe"),
            "percentile": getattr(ov, f"{key}_percentile"),
            "censored": getattr(ov, f"{key}_censored"),
            "depth_scanned": getattr(ov, f"{key}_depth_scanned"),
            "target_affinity": getattr(ov, f"{key}_target_affinity"),
            "top1_affinity": getattr(ov, f"{key}_top1_affinity"),
            "last_scanned_affinity": getattr(ov, f"{key}_last_scanned_affinity"),
            "affinity_ratio": getattr(ov, f"{key}_affinity_ratio"),
            "pages": peers.pages_fetched if peers else 0,
            "exhausted": peers.exhausted if peers else None,
            "filter_tags_used": peers.filter_tag_ids_used if peers else [],
            "returned": len(peers.entities) if peers else 0,
        }
    if sen["status"] == "resolved":
        _apply_fame(out, raw, resolution, notes)
    has_signal = ov.symmetric_percentile is not None or ov.symmetric_affinity_ratio is not None
    out["status"] = "scored" if has_signal else "no_overlap"
    notes.extend(rec.take_notes())
    out["queries"] = rec.take_queries()
    return out


async def run(rec: Recorder, resolved: dict[str, Any]) -> dict[str, Any]:
    cases = [await score_case(rec, c) for c in resolved["cases"]]
    return {
        "harness_version": HARNESS_VERSION,
        "resolver": resolved.get("resolver", "rule"),
        "model": resolved.get("model"),
        "qloo_mode": resolved.get("qloo_mode"),
        "mapping_sha256": resolved.get("mapping_sha256"),
        "comparator_rule": (
            f"agent resolver: {AGENT_COMPARATOR_RULE}; when the agent kept none: {COMPARATOR_RULE}"
            if resolved.get("resolver") == "agent"
            else COMPARATOR_RULE
        ),
        "cases": cases,
    }


def summarize(doc: dict[str, Any]) -> dict[str, Any]:
    cs = doc["cases"]
    return {
        "cases": len(cs),
        "scored": sum(c["status"] == "scored" for c in cs),
        "scored_with_proxy": sum(c["status"] == "scored" and c["used_proxy"] for c in cs),
        "with_rank_percentile": sum(c["symmetric_percentile"] is not None for c in cs),
        "with_affinity_ratio": sum(c.get("symmetric_affinity_ratio") is not None for c in cs),
        "unresolved": sum(c["status"] == "unresolved" for c in cs),
        "no_overlap": sum(c["status"] == "no_overlap" for c in cs),
        "with_breadth": sum(c["breadth_score"] is not None for c in cs),
        "queries": sum(len(c["queries"]) for c in cs),
    }
