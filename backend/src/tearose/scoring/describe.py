"""Plain-English fact sentences for the evidence, written in code (no model call).

The interpret and memo prompts receive these sentences as their only source for numbers, so
who-is-ranked-among-whom, universe sizes and percentile formatting are fixed here once and
cannot be re-described by a model. Percentiles are ordinals ("86th percentile"); every other
number has at most 2 decimals.
"""

from __future__ import annotations

from tearose.schemas import (
    BridgingEvidence,
    Evidence,
    FameEvidence,
    OverlapEvidence,
    ProxyResolution,
    Resolution,
    ZoneEvidence,
)

SMALL_UNIVERSE = 20  # below this many brands a rank is coarse
TOP_REGIONS_IN_FACTS = 3


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def pct_text(p: float) -> str:
    """0.8636 -> '86th percentile' (clipped to 0..100)."""
    return f"{ordinal(max(0, min(100, round(p * 100))))} percentile"


def num(x: float) -> str:
    return f"{x:.2f}"


def poss(name: str) -> str:
    """Possessive: "Acme" -> "Acme's", "Acme Spirits" -> "Acme Spirits'", "Joe's" unchanged."""
    if name.endswith(("'s", "’s")):
        return name
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _join(names: list[str]) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


class _Parties:
    """Display names, proxies and universe descriptions for both sides."""

    def __init__(self, resolution: Resolution | None, names: dict[str, str] | None = None) -> None:
        self.res = resolution
        self.names = names or {}

    def name(self, side: str) -> str:
        if self.names.get(side):
            return self.names[side]
        if self.res is not None:
            b = getattr(self.res, side)
            if b.entity_name or b.query:
                return b.entity_name or b.query
        return f"the {side} brand"

    def proxy(self, side: str) -> ProxyResolution | None:
        if self.res is None:
            return None
        brand = getattr(self.res, side)
        proxy = getattr(self.res, f"{side}_proxy")
        if brand.entity_id or proxy is None or not proxy.comparator_brand_names:
            return None
        return proxy

    def universe(self, side: str) -> str:
        if self.res is not None:
            for u in self.res.universes:
                if u.side == side and u.description:
                    return u.description
        return f"brands in the {side}'s category"

    def stand_in(self, side: str) -> str:
        """'the comparator brands A and B (standing in for X, which is not in Qloo)'."""
        proxy = self.proxy(side)
        assert proxy is not None
        names = proxy.comparator_brand_names
        noun = "comparator brand" if len(names) == 1 else "comparator brands"
        return f"the {noun} {_join(names)} (standing in for {self.name(side)}, not in Qloo)"


def _small(size: int | None) -> list[str]:
    if size is not None and 0 < size < SMALL_UNIVERSE:
        return [f"Small category ({size} brands), rank is coarse."]
    return []


# --------------------------------------------------------------------------------------
# overlap
# --------------------------------------------------------------------------------------


def _ratio_clause(aff: float | None, ratio: float | None) -> str:
    return (
        f"{num(aff)}, {num(ratio)} of the strongest brand in the category"
        if (aff is not None and ratio is not None)
        else ""
    )


def _direction(p: _Parties, seed: str, target: str, ev: OverlapEvidence) -> list[str]:
    """Seed = whose audience; target = who is ranked, among the TARGET side's category.

    Two signals: the rank percentile (censored when the target lies beyond the scanned depth)
    and the direct affinity, also as a ratio to the strongest brand of the same ranking."""
    key = f"{seed}_to_{target}"
    rank: int | None = getattr(ev, f"{key}_rank")
    size: int | None = getattr(ev, f"{key}_universe")
    pct: float | None = getattr(ev, f"{key}_percentile")
    censored: bool = getattr(ev, f"{key}_censored")
    depth: int | None = getattr(ev, f"{key}_depth_scanned")
    aff: float | None = getattr(ev, f"{key}_target_affinity")
    ratio: float | None = getattr(ev, f"{key}_affinity_ratio")
    universe = p.universe(target)
    seed_txt = f"{poss(p.name(seed))} audience"
    if p.proxy(seed) is not None:
        seed_txt = f"the audience of {p.stand_in(seed)}"
    plural = p.proxy(target) is not None
    who = p.stand_in(target) if plural else p.name(target)
    ratio_txt = _ratio_clause(aff, ratio)

    if censored:
        beyond = f"beyond the {depth} strongest" if depth else "not among the brands returned"
        if aff is not None and ratio is not None:
            mean = "mean affinity" if plural else "affinity"
            return [
                f"{who[0].upper() + who[1:]}: {mean} {num(aff)} to {seed_txt}, {num(ratio)} of "
                f"the strongest brand in the category ({universe}), {beyond} (rank censored, "
                "no rank percentile)."
            ]
        return [
            f"Among {universe}, ranked by affinity to {seed_txt}, {who} "
            f"{'are' if plural else 'is'} {beyond} (rank censored, no rank percentile; no "
            "direct affinity available)."
        ]
    if rank is None or size is None or pct is None:
        return [
            f"Overlap seeded by {poss(p.name(seed))} audience, ranking {p.name(target)} among "
            f"{universe}: no data."
        ]
    verb, how = (
        ("rank", f"{rank} of {size} on average") if plural else ("ranks", f"{rank} of {size}")
    )
    if pct <= 0:  # harness v1 records: a missing target was counted as last
        out = (
            f"Among {size} {universe}, ranked by affinity to {seed_txt}, {who} did not appear "
            f"in the results and {'are' if plural else 'is'} counted as last "
            f"({pct_text(pct)})."
        )
    else:
        out = (
            f"Among {size} {universe}, ranked by affinity to {seed_txt}, {who} {verb} {how} "
            f"({pct_text(pct)})."
        )
    if ratio_txt:
        out += f" {'Mean affinity' if plural else 'Affinity'} {ratio_txt}."
    return [out, *_small(size)]


def describe_overlap(ev: OverlapEvidence | None, p: _Parties) -> list[str]:
    if ev is None:
        return ["Overlap: not measured in this run."]
    out = _direction(p, "senior", "junior", ev)
    out += _direction(p, "junior", "senior", ev)
    both = [
        x for x in (ev.senior_to_junior_percentile, ev.junior_to_senior_percentile)
        if x is not None
    ]  # fmt: skip
    ratios = [
        x for x in (ev.senior_to_junior_affinity_ratio, ev.junior_to_senior_affinity_ratio)
        if x is not None
    ]  # fmt: skip
    if ev.symmetric_percentile is None and ev.symmetric_affinity_ratio is None:
        out.append("Overlap: no data in either direction.")
    elif ev.symmetric_percentile is None:
        out.append("No rank percentile in either direction (censored or missing).")
    elif len(both) == 2:
        out.append(
            f"Averaged over both directions, audience overlap is at the "
            f"{pct_text(ev.symmetric_percentile)}."
        )
    else:
        out.append(
            "Only one direction has a rank percentile; audience overlap is at the "
            f"{pct_text(ev.symmetric_percentile)}."
        )
    if ev.symmetric_affinity_ratio is not None:
        scope = (
            "Averaged over both directions"
            if len(ratios) == 2
            else "In the one direction available"
        )
        out.append(
            f"{scope}, the target's affinity is {num(ev.symmetric_affinity_ratio)} of the "
            "strongest brand in its category (affinity ratio, 0-1)."
        )
    if any("Compare: insufficient data" in n for n in ev.notes):
        out.append(
            "The direct audience comparison returned insufficient data (typical for a thin "
            "brand); this is not evidence of zero overlap."
        )
    return out


# --------------------------------------------------------------------------------------
# bridging
# --------------------------------------------------------------------------------------


def _junior_category(ev: BridgingEvidence, p: _Parties) -> str:
    proxy = p.res.junior_proxy if p.res is not None else None
    if proxy is not None:
        names = [
            str(o.get("name")) for o in proxy.tag_options
            if o.get("id") in ev.category_tag_ids and o.get("name")
        ]  # fmt: skip
        if names:
            return _join(list(dict.fromkeys(names)))
    return f"the junior's category ({p.universe('junior')})"


def describe_bridging(ev: BridgingEvidence | None, p: _Parties) -> list[str]:
    if ev is None:
        return ["Bridging: not measured in this run."]
    senior = p.name("senior")
    n = ev.senior_tag_universe
    if ev.percentile is None or n is None:
        reason = ev.notes[0] if ev.notes else ""
        return [f"Bridging: no data. {reason}".strip()]
    pool = f"the {n} brand-category tags most associated with {poss(senior)} audience"
    cat = _junior_category(ev, p)
    k = ev.category_rank_among_senior_tags
    if k is None:
        return [
            f"Neither {cat} nor any parent category appears among {pool} "
            f"({pct_text(ev.percentile)})."
        ]
    if ev.ancestor_levels:
        levels = ev.ancestor_levels
        lv = "level" if levels == 1 else "levels"
        return [
            f"{cat[0].upper() + cat[1:]} is not among {pool}; its parent category "
            f"{ev.matched_tag_name} is, at rank {k} of {n}.",
            f"Bridging is at the {pct_text(ev.percentile)} after halving the rank percentile "
            f"for each taxonomy level climbed ({levels} {lv}).",
        ]
    name = ev.matched_tag_name or cat
    return [f"Among {pool}, {name} ranks {k} of {n} ({pct_text(ev.percentile)})."]


# --------------------------------------------------------------------------------------
# fame
# --------------------------------------------------------------------------------------


def describe_fame(ev: FameEvidence | None, p: _Parties) -> list[str]:
    if ev is None:
        return ["Fame: not measured in this run."]
    senior = p.name("senior")
    out: list[str] = []
    if ev.breadth_score is None:
        out.append(f"Demographic breadth for {senior}: no data.")
    else:
        parts = [
            f"{label} {num(v)}"
            for label, v in (("age", ev.breadth_age), ("gender", ev.breadth_gender))
            if v is not None
        ]
        extra = f" ({', '.join(parts)})" if parts else ""
        out.append(
            f"Demographic breadth of {poss(senior)} audience is {num(ev.breadth_score)} on a 0-1 "
            f"scale where 1 means no age or gender skew{extra}."
        )
        if ev.skew_description == "broad":
            out.append(f"{poss(senior)} audience shows no marked age or gender skew.")
        elif ev.skew_description.startswith("skews"):
            out.append(f"{poss(senior)} audience {ev.skew_description}.")
    if ev.popularity_percentile is None:
        out.append(f"Popularity of {senior}: no data.")
    else:
        out.append(
            f"{senior} is at the {pct_text(ev.popularity_percentile)} of popularity on Qloo."
        )
    if ev.heatmap_coverage is None:
        out.append("National heatmap coverage: no data.")
    else:
        out.append(
            f"National heatmap coverage is {num(ev.heatmap_coverage)} (share of map cells with "
            "above-median affinity)."
        )
    if ev.fame_score is None:
        out.append("Combined fame score: not computed (needs breadth, popularity and coverage).")
    else:
        out.append(
            f"Combined fame score is {num(ev.fame_score)} (mean of breadth, popularity and "
            "coverage, 0-1)."
        )
    return out


# --------------------------------------------------------------------------------------
# zone
# --------------------------------------------------------------------------------------


def describe_zone(ev: ZoneEvidence | None, p: _Parties) -> list[str]:
    if ev is None:
        return ["Zone of reputation: not measured in this run."]
    senior = p.name("senior")
    out: list[str] = []
    if ev.concentration_index is None:
        out.append(f"Geographic concentration of {poss(senior)} affinity: no data.")
    else:
        out.append(
            f"Geographic concentration of {poss(senior)} affinity is {num(ev.concentration_index)} "
            "(0 = evenly spread, 1 = concentrated in a few places)."
        )
    regions = [r for r in ev.top_regions if r.get("label")][:TOP_REGIONS_IN_FACTS]
    if regions:
        listed = "; ".join(f"{r['label']} ({num(float(r.get('share') or 0))})" for r in regions)
        out.append(f"Top regions by share of {poss(senior)} total affinity: {listed}.")
    if ev.geographic_overlap is None:
        out.append(f"Geographic overlap with {poss(p.name('junior'))} map: no data.")
    else:
        out.append(
            f"Geographic overlap between {poss(senior)} and {poss(p.name('junior'))} maps is "
            f"{num(ev.geographic_overlap)} (cosine similarity, 0-1)."
        )
    return out


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------


def describe_evidence(
    evidence: Evidence | None,
    resolution: Resolution | None,
    names: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Exact fact sentences per analysis: keys overlap, bridging, fame, zone. `names`
    ({side: display name}) overrides the resolution's names, e.g. the document's spelling."""
    ev = evidence or Evidence()
    p = _Parties(resolution, names)
    return {
        "overlap": describe_overlap(ev.overlap, p),
        "bridging": describe_bridging(ev.bridging, p),
        "fame": describe_fame(ev.fame, p),
        "zone": describe_zone(ev.zone, p),
    }


def facts_block(facts: dict[str, list[str]]) -> str:
    """Render the sentences as the prompt's FACTS block."""
    lines: list[str] = []
    for key, sentences in facts.items():
        lines.append(f"[{key}]")
        lines += [f"- {s}" for s in sentences]
    return "\n".join(lines)
