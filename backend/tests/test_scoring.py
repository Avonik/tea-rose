"""Unit tests for the deterministic scoring module (no LLM, no network)."""

from __future__ import annotations

import itertools
import re

import pytest

from tearose.qloo.models import (
    CompareEntity,
    CompareResult,
    Demographics,
    Entity,
    HeatmapPoint,
    Tag,
)
from tearose.schemas import (
    Evidence,
    FactorFinding,
    Memo,
    ProxyResolution,
    Resolution,
    ResolvedBrand,
    RoutingDecision,
)
from tearose.scoring import DirectionalPeers, RawData, compute_evidence, synthesize_bottom_line
from tearose.scoring.score import (
    bin_points,
    breadth_parts,
    breadth_score,
    bridging_evidence,
    cosine,
    fame_evidence,
    gini,
    mean_rank,
    overlap_evidence,
    percentile_from_rank,
    skew_description,
    zone_evidence,
)
from tearose.scoring.universe import (
    build_universe_description,
    genre_depth,
    insights_universe_tags,
    own_category_tags,
    pick_category_tags,
)

# --------------------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------------------


def peers(n: int, exhausted: bool = False, ids: dict[int, str] | None = None) -> DirectionalPeers:
    """n brands ranked 1..n; `ids` overrides the entity id at given 1-based ranks."""
    ids = ids or {}
    ents = [
        Entity(
            entity_id=ids.get(r, f"e{r}"),
            name=f"Brand {r}",
            subtype="urn:entity:brand",
            affinity=round(1 - r / (n + 1), 4),
            rank=r,
        )
        for r in range(1, n + 1)
    ]
    return DirectionalPeers(
        seed_entity_ids=["seed"],
        universe_tag_ids=["t"],
        universe_description="test brands",
        entities=ents,
        pages_fetched=(n + 49) // 50,
        exhausted=exhausted,
    )


def resolution() -> Resolution:
    return Resolution(
        senior=ResolvedBrand(side="senior", query="S", entity_id="SEN", popularity=0.97),
        junior=ResolvedBrand(side="junior", query="J", entity_id="JUN"),
    )


def pt(lat: float, lon: float, aff: float | None, label: str | None = None) -> HeatmapPoint:
    return HeatmapPoint(latitude=lat, longitude=lon, affinity=aff, label=label)


def demo(ages: list[float], male: float, female: float) -> Demographics:
    keys = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]
    return Demographics(
        age=dict(zip(keys, ages, strict=True)), gender={"male": male, "female": female}
    )


ALL = RoutingDecision(analyses=["overlap", "bridging", "fame", "zone"], rationale={"all": "test"})

# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def test_percentile_from_rank():
    assert percentile_from_rank(1, 150) == 1.0
    assert percentile_from_rank(151, 150) == 0.0
    assert percentile_from_rank(76, 150) == pytest.approx(0.5)
    assert percentile_from_rank(500, 150) == 0.0  # clipped
    assert percentile_from_rank(None, 150) is None
    assert percentile_from_rank(3, 0) is None


def test_mean_rank():
    assert mean_rank([]) is None
    assert mean_rank([2, 10, 151]) == pytest.approx(163 / 3)


def test_gini_uniform_is_zero():
    assert gini([0.4] * 20) == pytest.approx(0.0)


def test_gini_single_spike_near_one():
    g = gini([1.0] + [0.0] * 99)
    assert g == pytest.approx(0.99)
    assert gini([]) is None
    assert gini([0.0, 0.0]) is None


def test_cosine():
    assert cosine([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 1]) is None
    assert cosine([1], [1, 2]) is None


def test_bin_points():
    pts = [pt(40.71, -74.01, 0.5), pt(40.74, -73.98, 0.25), pt(34.05, -118.24, 0.2, "LA")]
    bins = bin_points(pts)
    assert bins == {"40.7, -74.0": pytest.approx(0.75), "34.0, -118.2": pytest.approx(0.2)}
    assert set(bin_points(pts, use_label=True)) == {"40.7, -74.0", "LA"}
    assert bin_points([pt(1, 1, None)]) == {}


# --------------------------------------------------------------------------------------
# overlap
# --------------------------------------------------------------------------------------


def test_overlap_target_found_on_page_1():
    raw = RawData(
        senior_seed_junior_universe=peers(150, ids={3: "JUN"}),
        junior_target_entity_ids=["JUN"],
    )
    ev = overlap_evidence(raw, resolution())
    assert ev.senior_to_junior_rank == 3
    assert ev.senior_to_junior_universe == 150
    assert ev.symmetric_percentile == pytest.approx(1 - 2 / 150)
    assert any("one direction" in n for n in ev.notes)
    assert len(ev.top_peers_senior_seed) == 10
    assert ev.top_peers_senior_seed[2].entity_id == "JUN"


def test_overlap_target_found_on_page_3():
    raw = RawData(
        senior_seed_junior_universe=peers(150, ids={120: "JUN"}),
        junior_target_entity_ids=["JUN"],
    )
    ev = overlap_evidence(raw)
    assert ev.senior_to_junior_rank == 120
    assert ev.symmetric_percentile == pytest.approx(1 - 119 / 150)


def test_overlap_not_found_exhausted_universe_is_censored():
    raw = RawData(
        senior_seed_junior_universe=peers(40, exhausted=True), junior_target_entity_ids=["JUN"]
    )
    ev = overlap_evidence(raw)
    assert ev.senior_to_junior_universe == 40 and ev.senior_to_junior_depth_scanned == 40
    assert ev.senior_to_junior_rank is None and ev.senior_to_junior_percentile is None
    assert ev.senior_to_junior_censored is True
    assert ev.symmetric_percentile is None  # censored, not 0 (harness v1 counted rank 41)
    assert ev.senior_to_junior_affinity_ratio is None  # no lookup made
    assert any("complete list" in n for n in ev.notes)


def test_overlap_censored_rank_has_no_percentile_but_an_affinity_ratio():
    p = peers(150).model_copy(update={"target_affinities": {"JUN": 0.5}})
    ev = overlap_evidence(RawData(senior_seed_junior_universe=p, junior_target_entity_ids=["JUN"]))
    top, last = p.entities[0].affinity, p.entities[-1].affinity
    assert ev.senior_to_junior_universe == 150
    assert ev.senior_to_junior_rank is None and ev.senior_to_junior_percentile is None
    assert ev.senior_to_junior_censored is True and ev.symmetric_percentile is None
    assert ev.senior_to_junior_target_affinity == pytest.approx(0.5)
    assert ev.senior_to_junior_top1_affinity == pytest.approx(top)
    assert ev.senior_to_junior_last_scanned_affinity == pytest.approx(last)
    assert ev.senior_to_junior_affinity_ratio == pytest.approx(0.5 / top)
    assert ev.symmetric_affinity_ratio == pytest.approx(0.5 / top)
    assert any("search depth 150" in n and "rank censored" in n for n in ev.notes)


def test_overlap_found_target_uses_lookup_else_listed_affinity():
    p = peers(150, ids={3: "JUN"})
    listed = p.entities[2].affinity
    ev = overlap_evidence(RawData(senior_seed_junior_universe=p, junior_target_entity_ids=["JUN"]))
    assert ev.senior_to_junior_censored is False and ev.senior_to_junior_rank == 3
    assert ev.senior_to_junior_affinity_ratio == pytest.approx(listed / p.entities[0].affinity)
    looked = p.model_copy(update={"target_affinities": {"JUN": 0.97}})
    ev2 = overlap_evidence(
        RawData(senior_seed_junior_universe=looked, junior_target_entity_ids=["JUN"])
    )
    assert ev2.senior_to_junior_target_affinity == pytest.approx(0.97)
    assert ev2.senior_to_junior_affinity_ratio == pytest.approx(0.97 / p.entities[0].affinity)


def test_overlap_ratio_is_clipped_and_needs_a_top_affinity():
    p = peers(10).model_copy(update={"target_affinities": {"JUN": 5.0}})
    ev = overlap_evidence(RawData(senior_seed_junior_universe=p, junior_target_entity_ids=["JUN"]))
    assert ev.senior_to_junior_affinity_ratio == 1.0
    empty = peers(0, exhausted=True).model_copy(update={"target_affinities": {"JUN": 0.4}})
    ev = overlap_evidence(
        RawData(senior_seed_junior_universe=empty, junior_target_entity_ids=["JUN"])
    )
    assert ev.senior_to_junior_affinity_ratio is None and ev.symmetric_affinity_ratio is None


def test_overlap_proxy_three_comparators_one_missing_is_censored():
    p = peers(150, ids={2: "C1", 10: "C2"}).model_copy(
        update={"target_affinities": {"C1": 0.9, "C2": 0.8, "C3": 0.4}}
    )
    raw = RawData(
        senior_seed_junior_universe=p,
        junior_target_entity_ids=["C1", "C2", "C3"],
        used_proxy_junior=True,
    )
    ev = overlap_evidence(raw)
    assert ev.senior_to_junior_rank is None and ev.senior_to_junior_censored is True
    assert ev.symmetric_percentile is None
    assert ev.senior_to_junior_target_affinity == pytest.approx(0.7)  # mean over comparators
    assert ev.senior_to_junior_affinity_ratio == pytest.approx(0.7 / p.entities[0].affinity)
    assert ev.used_proxy is True
    assert any("C3" in n and "1 of 3" in n for n in ev.notes)
    assert any("mean over 3 comparator" in n for n in ev.notes)


def test_overlap_proxy_all_comparators_found_mean_rank():
    raw = RawData(
        senior_seed_junior_universe=peers(150, ids={2: "C1", 10: "C2", 30: "C3"}),
        junior_target_entity_ids=["C1", "C2", "C3"],
        used_proxy_junior=True,
    )
    ev = overlap_evidence(raw)
    assert ev.senior_to_junior_rank == 14
    assert ev.symmetric_percentile == pytest.approx(1 - 13 / 150)


def test_overlap_symmetric_means_with_one_side_censored():
    s2j = peers(150).model_copy(update={"target_affinities": {"JUN": 0.4}})  # censored
    j2s = peers(50, exhausted=True, ids={26: "SEN"}).model_copy(
        update={"target_affinities": {"SEN": 0.6}}
    )
    raw = RawData(
        senior_seed_junior_universe=s2j,
        junior_seed_senior_universe=j2s,
        junior_target_entity_ids=["JUN"],
        senior_target_entity_ids=["SEN"],
    )
    ev = overlap_evidence(raw)
    assert ev.senior_to_junior_percentile is None and ev.junior_to_senior_percentile == 0.5
    assert ev.symmetric_percentile == pytest.approx(0.5)  # the one available rank percentile
    r1 = 0.4 / s2j.entities[0].affinity
    r2 = 0.6 / j2s.entities[0].affinity
    assert ev.symmetric_affinity_ratio == pytest.approx((r1 + r2) / 2)
    assert any("Only one direction has a rank percentile" in n for n in ev.notes)


def test_overlap_symmetric_mean_and_compare_lists():
    compare = CompareResult(
        entities=[
            CompareEntity(entity_id="x", name="X", a_affinity=0.9, b_affinity=0.8, delta=0.1),
            CompareEntity(entity_id="y", name="Y", a_affinity=0.9, b_affinity=0.1, delta=0.8),
            CompareEntity(entity_id="z", name="Z", a_affinity=0.1, b_affinity=0.9, delta=-0.8),
        ]
    )
    raw = RawData(
        senior_seed_junior_universe=peers(150, ids={1: "JUN"}),
        junior_seed_senior_universe=peers(50, exhausted=True, ids={26: "SEN"}),
        compare=compare,
    )
    ev = overlap_evidence(raw, resolution())  # targets fall back to the resolution ids
    assert ev.symmetric_percentile == pytest.approx((1.0 + 0.5) / 2)
    assert ev.shared_affinities[0]["entity_id"] == "x"
    assert set(ev.shared_affinities[0]) == {
        "entity_id",
        "name",
        "a_affinity",
        "b_affinity",
        "delta",
    }
    assert ev.distinct_to_senior[0]["entity_id"] == "y"
    assert ev.distinct_to_junior[0]["entity_id"] == "z"
    assert ev.used_proxy is False


def test_overlap_compare_tags_use_score_and_thin_brand_is_insufficient():
    shared = CompareResult(
        tags=[Tag(tag_id="t", name="Bold", tag_type="urn:tag:adjective:qloo", score=0.71)]
    )
    ev = overlap_evidence(RawData(compare=shared), resolution())
    assert ev.shared_affinities == [
        {"tag_id": "t", "name": "Bold", "type": "urn:tag:adjective:qloo", "score": 0.71}
    ]
    thin = CompareResult(a_tags=[Tag(tag_id="a", name="A", count=3)])  # b and tags empty
    ev = overlap_evidence(RawData(compare=thin), resolution())
    assert ev.shared_affinities == []
    assert any("insufficient data" in n for n in ev.notes)


def test_overlap_empty_inputs():
    ev = overlap_evidence(RawData())
    assert ev.symmetric_percentile is None
    assert ev.senior_to_junior_rank is None and ev.junior_to_senior_rank is None
    assert ev.notes


def test_overlap_empty_exhausted_universe():
    raw = RawData(
        senior_seed_junior_universe=peers(0, exhausted=True), junior_target_entity_ids=["J"]
    )
    ev = overlap_evidence(raw)
    assert ev.symmetric_percentile is None
    assert any("empty" in n for n in ev.notes)


# --------------------------------------------------------------------------------------
# bridging
# --------------------------------------------------------------------------------------


def _tags(n: int, ids: dict[int, str]) -> list[Tag]:
    return [
        Tag(tag_id=ids.get(r, f"t{r}"), name=f"Tag {r}", affinity=1 - r / 100, rank=r)
        for r in range(1, n + 1)
    ]


def test_bridging_best_rank_wins():
    raw = RawData(
        senior_tags=_tags(50, {5: "dog", 30: "pet"}), junior_category_tag_ids=["pet", "dog"]
    )
    ev = bridging_evidence(raw)
    assert ev.category_rank_among_senior_tags == 5
    assert ev.senior_tag_universe == 50
    assert ev.percentile == pytest.approx(1 - 4 / 50)
    assert ev.category_affinity == pytest.approx(0.95)


BRAND = "urn:tag:genre:brand"
LEAF = f"{BRAND}:household:pets:toys"
PARENT = f"{BRAND}:household:pets"
GRANDPARENT = f"{BRAND}:household"


def test_bridging_leaf_present_is_undiscounted():
    raw = RawData(senior_tags=_tags(50, {4: PARENT, 10: LEAF}), junior_category_tag_ids=[LEAF])
    ev = bridging_evidence(raw)
    assert ev.category_rank_among_senior_tags == 10 and ev.ancestor_levels == 0
    assert ev.matched_tag_id == LEAF
    assert ev.percentile == pytest.approx(1 - 9 / 50)
    assert not any("leaf absent" in n for n in ev.notes)


def test_bridging_parent_present_is_discounted_per_level():
    raw = RawData(senior_tags=_tags(50, {11: PARENT}), junior_category_tag_ids=[LEAF])
    ev = bridging_evidence(raw)
    assert ev.category_rank_among_senior_tags == 11
    assert ev.matched_tag_id == PARENT and ev.ancestor_levels == 1
    assert ev.percentile == pytest.approx((1 - 10 / 50) * 0.5)
    assert any(n.startswith("leaf absent; parent Tag 11 at rank 11") for n in ev.notes)
    # two levels up: discount 0.25; the bare brand-genre root never counts
    ev2 = bridging_evidence(
        RawData(senior_tags=_tags(50, {1: GRANDPARENT, 2: BRAND}), junior_category_tag_ids=[LEAF])
    )
    assert ev2.ancestor_levels == 2 and ev2.percentile == pytest.approx(0.25)
    raw3 = RawData(senior_tags=_tags(50, {1: BRAND}), junior_category_tag_ids=[LEAF])
    ev3 = bridging_evidence(raw3)
    assert ev3.percentile == 0.0 and ev3.category_rank_among_senior_tags is None


def test_bridging_not_found_and_empty():
    ev = bridging_evidence(RawData(senior_tags=_tags(20, {}), junior_category_tag_ids=[LEAF]))
    assert ev.percentile == 0.0 and ev.category_rank_among_senior_tags is None and ev.notes
    assert ev.matched_tag_id is None and ev.ancestor_levels == 0
    ev2 = bridging_evidence(RawData())
    assert ev2.percentile is None and ev2.notes
    ev3 = bridging_evidence(RawData(junior_category_tag_ids=["pet"]))
    assert ev3.percentile is None and ev3.notes


# --------------------------------------------------------------------------------------
# fame
# --------------------------------------------------------------------------------------


def test_breadth_flat_zeros_is_one():
    assert breadth_score(demo([0.0] * 6, 0.0, 0.0)) == pytest.approx(1.0)
    assert breadth_parts(demo([0.0] * 6, 0.0, 0.0)) == (pytest.approx(1.0), pytest.approx(1.0))
    assert breadth_score(None) is None
    assert breadth_score(Demographics()) is None


def test_breadth_single_strong_spike_is_low():
    spike = breadth_score(demo([0.9, -0.9, -0.9, -0.9, -0.9, -0.9], 0.9, -0.9))
    assert spike is not None and spike == pytest.approx(0.1)
    # mild deviations everywhere score high
    mild = breadth_score(demo([0.1, 0.12, -0.1, 0.08, -0.1, 0.09], 0.05, -0.06))
    assert mild is not None and mild > 0.9


def test_breadth_mixed_real_world_like_pattern():
    # one bucket +0.4, the others between -0.1 and -0.7, a moderate gender gap
    d = demo([-0.2, -0.1, -0.7, -0.6, -0.5, 0.4], 0.4, -0.4)
    b = breadth_score(d)
    assert b is not None and 0.5 <= b <= 0.6
    assert b == pytest.approx(1 - 3.3 / 8)
    age, gender = breadth_parts(d)
    assert age == pytest.approx(1 - 2.5 / 6) and gender == pytest.approx(0.6)


def test_skew_description_wording():
    assert (
        skew_description(demo([-0.2, 0.5, 0.4, 0.0, -0.1, -0.3], 0.3, -0.3)) == "skews 25–34, male"
    )
    assert skew_description(demo([0.4, 0.0, 0.0, 0.0, 0.0, 0.3], -0.2, 0.2)) == (
        "skews under 25 and 55+, female"
    )
    assert skew_description(demo([0.05, 0.1, 0.0, 0.05, 0.1, 0.08], 0.02, 0.0)) == "broad"
    assert skew_description(None).startswith("unknown")


def test_fame_evidence_coverage_and_popularity():
    national = [pt(i, i, a) for i, a in enumerate([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])]
    raw = RawData(
        senior_demographics=demo([0.1] * 6, 0.1, 0.1),
        senior_popularity=0.98,
        senior_heatmap_national=national,
    )
    ev = fame_evidence(raw)
    assert ev.popularity_percentile == 0.98
    assert ev.heatmap_coverage == pytest.approx(0.5)
    assert ev.skew_description == "broad"
    assert ev.breadth_score == pytest.approx(0.9)
    assert ev.fame_score == pytest.approx((0.9 + 0.98 + 0.5) / 3)
    # fame_score needs all three inputs
    assert fame_evidence(RawData(senior_demographics=demo([0.1] * 6, 0.1, 0.1))).fame_score is None


def test_fame_empty_inputs():
    ev = fame_evidence(RawData())
    assert ev.breadth_score is None and ev.heatmap_coverage is None
    assert ev.popularity_percentile is None
    assert len(ev.notes) == 3
    assert fame_evidence(RawData(), resolution()).popularity_percentile == 0.97


# --------------------------------------------------------------------------------------
# zone
# --------------------------------------------------------------------------------------


def test_zone_evidence_full():
    senior = [pt(40.7, -74.0, 0.9, "New York")] + [pt(30 + i, -90, 0.1) for i in range(5)]
    raw = RawData(senior_heatmap=senior, junior_heatmap=list(senior))
    ev = zone_evidence(raw)
    assert ev.concentration_index is not None and 0 < ev.concentration_index < 1
    assert ev.top_regions[0] == {"label": "New York", "share": pytest.approx(0.9 / 1.4)}
    assert sum(r["share"] for r in ev.top_regions) == pytest.approx(1.0)
    assert ev.geographic_overlap == pytest.approx(1.0)
    assert len(ev.junior_points) == 6


def test_zone_top_regions_capped_at_eight():
    raw = RawData(senior_heatmap=[pt(i, i, 0.1 + i / 100) for i in range(12)])
    ev = zone_evidence(raw)
    assert len(ev.top_regions) == 8
    assert ev.geographic_overlap is None


def test_zone_empty_and_thin_inputs():
    ev = zone_evidence(RawData())
    assert ev.concentration_index is None and ev.geographic_overlap is None
    assert ev.top_regions == [] and ev.notes
    thin = zone_evidence(RawData(senior_heatmap=[pt(1, 1, 0.5)] * 3))
    assert thin.concentration_index is None


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------


def test_routing_subset_only_computes_requested():
    routing = RoutingDecision(analyses=["fame", "zone"], rationale={})
    ev = compute_evidence(RawData(), resolution(), routing)
    assert ev.overlap is None and ev.bridging is None
    assert ev.fame is not None and ev.zone is not None


def test_compute_evidence_fully_empty_raw():
    res = Resolution(
        senior=ResolvedBrand(side="senior", query="S"),
        junior=ResolvedBrand(side="junior", query="J"),
        junior_proxy=ProxyResolution(
            side="junior", goods_phrase="dog toys", tag_options=[], chosen_tag_ids=[], rationale=""
        ),
    )
    ev = compute_evidence(RawData(), res, ALL)
    assert isinstance(ev, Evidence)
    for part in (ev.overlap, ev.bridging, ev.fame, ev.zone):
        assert part is not None and part.notes
    assert ev.overlap.symmetric_percentile is None
    assert ev.bridging.percentile is None
    assert ev.fame.breadth_score is None
    assert ev.zone.concentration_index is None


def test_compute_evidence_none_inputs():
    ev = compute_evidence(None, None, None)
    assert ev == Evidence()


# --------------------------------------------------------------------------------------
# universe.py
# --------------------------------------------------------------------------------------


def _gt(path: str, name: str = "") -> Tag:
    return Tag(
        tag_id=f"urn:tag:genre:brand:{path}",
        name=name or path.rsplit(":", 1)[-1].title(),
        tag_type="urn:tag:genre:brand",
    )


def test_own_category_tags_keeps_most_specific_nodes():
    tags = [
        _gt("fashion"),
        Tag(tag_id="urn:tag:wikipedia_category:x", name="X", tag_type="urn:tag:wikipedia_category"),
        _gt("fashion:footwear"),
        _gt("fashion:footwear:sneakers"),
        _gt("fashion:footwear:other", "Other"),
        _gt("fashion:athletic"),
        _gt("retail"),  # a depth-1 leaf loses to deeper nodes
        _gt("fashion:accessories:watch"),
    ]
    out = own_category_tags(tags)
    assert [t.tag_id.removeprefix("urn:tag:genre:brand:") for t in out] == [
        "fashion:footwear:sneakers", "fashion:footwear:other", "fashion:athletic"
    ]  # fmt: skip
    assert out[1].name == "Other footwear"  # readable label for an "Other" leaf
    assert genre_depth(tags[0].tag_id) == 1 and genre_depth("urn:tag:keyword:x") == 0


def test_own_category_tags_top_family_only_when_nothing_deeper_and_empty_without_genre():
    assert [t.tag_id for t in own_category_tags([_gt("dining")])] == ["urn:tag:genre:brand:dining"]
    two = own_category_tags([_gt("dining"), _gt("retail")])
    assert len(two) == 2
    assert own_category_tags([Tag(tag_id="urn:tag:keyword:x", name="x")]) == []
    assert own_category_tags([]) == []


def test_insights_universe_tags_fallback_rule():
    tags = [Tag(tag_id="urn:tag:keyword:a", name="A")] + [_gt(f"f{i}") for i in range(7)]
    assert [t.name for t in insights_universe_tags(tags)] == ["F0", "F1", "F2", "F3", "F4"]
    other = [Tag(tag_id="x", name="X", tag_type="urn:tag:category:place")]
    assert insights_universe_tags(other) == other  # any category/genre tag as a last resort
    assert insights_universe_tags([Tag(tag_id="k", name="K", tag_type="urn:tag:keyword")]) == []


def test_build_universe_description():
    assert build_universe_description([Tag(tag_id="a", name="Pet Supply")]) == "pet supply brands"
    two = [
        Tag(tag_id="a", name="Whiskey"),
        Tag(tag_id="b", name="Bourbon"),
        Tag(tag_id="c", name="X"),
    ]
    assert build_universe_description(two) == "whiskey / bourbon brands"
    assert build_universe_description([Tag(tag_id="a", name="Luxury Brands")]) == "luxury brands"
    assert build_universe_description([]) == "brands (unspecified category)"


def test_pick_category_tags_deterministic():
    tags = [
        Tag(tag_id="1", name="Dog Toys and Chews for Puppies", tag_type="urn:tag:keyword"),
        Tag(tag_id="2", name="Dog Toys", tag_type="urn:tag:category:brand"),
        Tag(tag_id="3", name="Whiskey", tag_type="urn:tag:category:brand"),
        Tag(tag_id="4", name="Toys", tag_type="urn:tag:keyword"),
        Tag(tag_id="5", name="Toy", tag_type="urn:tag:category:brand"),
    ]
    picked = pick_category_tags(tags, "squeaky dog toys, namely rubber chew toys", max_n=3)
    assert [t.tag_id for t in picked] == ["1", "2", "5"]
    assert pick_category_tags(tags, "financial services") == []
    assert pick_category_tags([], "dog toys") == []
    assert pick_category_tags(tags, "dog toys", max_n=0) == []


def test_pick_category_tags_prefers_brand_genre_tags():
    tags = [
        Tag(tag_id="urn:tag:keyword:media:dog_toy", name="Dog Toy", tag_type="urn:tag:keyword"),
        Tag(tag_id="urn:tag:category:place:pet_store", name="Pet Store",
            tag_type="urn:tag:category:place"),
        Tag(tag_id="urn:tag:genre:brand:food_and_beverage:pet_food", name="Pet Food",
            tag_type="urn:tag:genre:brand"),
    ]  # fmt: skip
    picked = pick_category_tags(tags, "dog toys and pet treats", max_n=3)
    assert picked[0].tag_id == "urn:tag:genre:brand:food_and_beverage:pet_food"
    # fallback kept: without any genre tag the keyword overlap still decides
    assert [t.name for t in pick_category_tags(tags[:2], "dog toys")] == ["Dog Toy"]


# --------------------------------------------------------------------------------------
# bottom line (synthesised in code from the factor leans)
# --------------------------------------------------------------------------------------

SILENT = "It is silent on mark similarity, intent and actual confusion."
FORBIDDEN = ("win", "lose", "verdict", "likely", "probability")


def ff(factor: str, lean: str, confidence: str = "medium") -> FactorFinding:
    return FactorFinding(factor=factor, lean=lean, confidence=confidence, finding="x")


def test_bottom_line_low_confidence_clauses() -> None:
    relat = ff("relatedness_of_goods", "favors_junior", "low")
    chan = ff("channels_and_purchasers", "neutral", "low")
    bridge = ff("bridging_the_gap", "neutral", "low")
    fame = ff("fame", "favors_senior", "high")
    assert synthesize_bottom_line([relat, chan, bridge, fame]) == (
        "Taste data cuts against the senior mark on 1 of 3 confusion factors (low confidence) "
        f"but supports the senior mark on fame. {SILENT}"
    )
    # one non-low counted finding: no tag on that clause; low fame and zone get their own tag
    chan_med = ff("channels_and_purchasers", "neutral", "medium")
    zone = ff("zone_of_reputation", "favors_senior", "low")
    assert synthesize_bottom_line(
        [relat, chan_med, bridge, ff("fame", "favors_senior", "low"), zone]
    ) == (
        "Taste data cuts against the senior mark on 1 of 3 confusion factors but supports the "
        "senior mark on fame (low confidence), and shows a wide zone of reputation "
        f"(low confidence). {SILENT}"
    )
    # insufficient findings are not counted; tag merges with the insufficient-data note
    missing = ff("bridging_the_gap", "insufficient_data", "low")
    assert synthesize_bottom_line([relat, ff("channels_and_purchasers", "favors_junior", "low"),
                                   missing]) == (
        "Taste data cuts against the senior mark on both confusion factors measured "
        f"(low confidence; 1 factor has insufficient data). {SILENT}"
    )  # fmt: skip
    # all insufficient: inconclusive, no confidence tag
    assert "low confidence" not in synthesize_bottom_line(
        [ff(f.factor, "insufficient_data", "low") for f in (relat, chan, bridge)]
    )


def confusion(*leans: str) -> list[FactorFinding]:
    names = ("relatedness_of_goods", "channels_and_purchasers", "bridging_the_gap")
    return [ff(n, lean) for n, lean in zip(names, leans, strict=False)]


def test_bottom_line_all_neutral() -> None:
    assert synthesize_bottom_line(confusion("neutral", "neutral", "neutral")) == (
        f"Taste data is neutral on all 3 confusion factors. {SILENT}"
    )


def test_bottom_line_all_insufficient() -> None:
    leans = ("insufficient_data",) * 3
    assert synthesize_bottom_line(confusion(*leans)) == (
        "Taste data is inconclusive on the confusion factors "
        f"(3 factors have insufficient data). {SILENT}"
    )


def test_bottom_line_counts_and_insufficient_note() -> None:
    assert synthesize_bottom_line(confusion("favors_senior", "favors_senior", "neutral")) == (
        f"Taste data supports the senior mark on 2 of 3 confusion factors. {SILENT}"
    )
    assert synthesize_bottom_line(confusion("favors_junior", "neutral", "favors_junior")) == (
        f"Taste data cuts against the senior mark on 2 of 3 confusion factors. {SILENT}"
    )
    assert synthesize_bottom_line(confusion("favors_senior", "neutral", "insufficient_data")) == (
        "Taste data supports the senior mark on 1 of 2 confusion factors "
        f"(1 factor has insufficient data). {SILENT}"
    )


def test_bottom_line_mixed() -> None:
    assert synthesize_bottom_line(confusion("favors_senior", "favors_junior", "neutral")) == (
        "Taste data supports the senior mark on 1 confusion factor and the junior user on 1. "
        f"{SILENT}"
    )


def test_bottom_line_fame_and_zone() -> None:
    base = confusion("favors_senior", "favors_senior", "neutral")
    assert synthesize_bottom_line([*base, ff("fame", "favors_senior")]) == (
        f"Taste data supports the senior mark on 2 of 3 confusion factors and on fame. {SILENT}"
    )
    assert synthesize_bottom_line([*base, ff("fame", "favors_junior")]) == (
        f"Taste data supports the senior mark on 2 of 3 confusion factors but not on fame. {SILENT}"
    )
    assert synthesize_bottom_line([*base, ff("fame", "neutral")]) == (
        "Taste data supports the senior mark on 2 of 3 confusion factors and is neutral on fame. "
        f"{SILENT}"
    )
    # insufficient fame is omitted; zone is phrased from the lean only
    assert synthesize_bottom_line(
        [*base, ff("fame", "insufficient_data"), ff("zone_of_reputation", "favors_senior")]
    ) == (
        "Taste data supports the senior mark on 2 of 3 confusion factors, and shows a wide zone "
        f"of reputation. {SILENT}"
    )
    assert synthesize_bottom_line(
        [
            *confusion("neutral", "neutral", "neutral"),
            ff("fame", "favors_senior"),
            ff("zone_of_reputation", "favors_junior"),
        ]
    ) == (
        "Taste data is neutral on all 3 confusion factors but supports the senior mark on fame, "
        f"and shows a narrow zone of reputation. {SILENT}"
    )
    assert synthesize_bottom_line([*base, ff("zone_of_reputation", "neutral")]) == (
        f"Taste data supports the senior mark on 2 of 3 confusion factors. {SILENT}"
    )


def test_bottom_line_without_confusion_factors() -> None:
    assert synthesize_bottom_line([ff("fame", "favors_junior")]) == (
        f"Taste data cuts against the senior mark on fame. {SILENT}"
    )
    assert synthesize_bottom_line([]) == f"Taste data produced no factor findings. {SILENT}"


def test_bottom_line_never_uses_outcome_words() -> None:
    leans = ("favors_senior", "neutral", "favors_junior", "insufficient_data")
    combos = itertools.product(leans, leans, leans, leans, leans, ("low", "medium"))
    for a, b, c, fame, zone, conf in combos:
        findings = [
            *(f.model_copy(update={"confidence": conf}) for f in confusion(a, b, c)),
            ff("fame", fame, conf),
            ff("zone_of_reputation", zone, conf),
        ]
        line = synthesize_bottom_line(findings)
        counted = any(x != "insufficient_data" for x in (a, b, c, fame)) or zone in (
            "favors_senior",
            "favors_junior",
        )
        assert ("(low confidence" in line) == (conf == "low" and counted), line
        assert line.endswith(SILENT) and line.startswith("Taste data ")
        words = set(re.findall(r"[a-z]+", line.lower()))
        assert not words & set(FORBIDDEN), line
        assert line.count(".") == 2  # one synthesised sentence + the fixed clause


def test_memo_without_bottom_line_still_loads() -> None:
    memo = Memo.model_validate(
        {"headline": "h", "findings": [], "sections": [], "limitations": [], "appendix_queries": []}
    )
    assert memo.bottom_line == ""
