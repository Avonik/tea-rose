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
from tearose.scoring.universe import build_universe_description, pick_category_tags

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


def test_overlap_not_found_exhausted_universe_is_list_length():
    raw = RawData(
        senior_seed_junior_universe=peers(40, exhausted=True), junior_target_entity_ids=["JUN"]
    )
    ev = overlap_evidence(raw)
    assert ev.senior_to_junior_universe == 40
    assert ev.senior_to_junior_rank == 41
    assert ev.symmetric_percentile == 0.0
    assert any("complete list" in n for n in ev.notes)


def test_overlap_not_found_not_exhausted_uses_search_cap():
    raw = RawData(senior_seed_junior_universe=peers(100), junior_target_entity_ids=["JUN"])
    ev = overlap_evidence(raw)
    assert ev.senior_to_junior_universe == 150
    assert ev.senior_to_junior_rank == 151
    assert ev.symmetric_percentile == 0.0
    assert any("search depth 150" in n for n in ev.notes)


def test_overlap_proxy_three_comparators_one_missing():
    raw = RawData(
        senior_seed_junior_universe=peers(150, ids={2: "C1", 10: "C2"}),
        junior_target_entity_ids=["C1", "C2", "C3"],
        used_proxy_junior=True,
    )
    ev = overlap_evidence(raw)
    mr = (2 + 10 + 151) / 3
    assert ev.senior_to_junior_rank == round(mr)
    assert ev.symmetric_percentile == pytest.approx(1 - (mr - 1) / 150)
    assert ev.used_proxy is True
    assert any("C3" in n and "1 of 3" in n for n in ev.notes)
    assert any("mean over 3 comparator" in n for n in ev.notes)


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


def test_bridging_not_found_and_empty():
    ev = bridging_evidence(RawData(senior_tags=_tags(20, {}), junior_category_tag_ids=["pet"]))
    assert ev.percentile == 0.0 and ev.category_rank_among_senior_tags is None and ev.notes
    ev2 = bridging_evidence(RawData())
    assert ev2.percentile is None and ev2.notes
    ev3 = bridging_evidence(RawData(junior_category_tag_ids=["pet"]))
    assert ev3.percentile is None and ev3.notes


# --------------------------------------------------------------------------------------
# fame
# --------------------------------------------------------------------------------------


def test_breadth_broad_vs_narrow():
    broad = breadth_score(demo([0.1, 0.12, 0.1, 0.08, 0.1, 0.09], 0.05, 0.06))
    narrow = breadth_score(demo([-0.3, 0.6, 0.5, -0.2, -0.4, -0.5], 0.4, -0.4))
    assert broad == pytest.approx(1.0)
    assert narrow is not None and narrow < 0.3
    assert breadth_score(None) is None
    assert breadth_score(Demographics()) is None


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


def ff(factor: str, lean: str) -> FactorFinding:
    return FactorFinding(factor=factor, lean=lean, confidence="medium", finding="x")


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
    for a, b, c, fame, zone in itertools.product(leans, repeat=5):
        findings = [
            *confusion(a, b, c),
            ff("fame", fame),
            ff("zone_of_reputation", zone),
        ]
        line = synthesize_bottom_line(findings)
        assert line.endswith(SILENT) and line.startswith("Taste data ")
        words = set(re.findall(r"[a-z]+", line.lower()))
        assert not words & set(FORBIDDEN), line
        assert line.count(".") == 2  # one synthesised sentence + the fixed clause


def test_memo_without_bottom_line_still_loads() -> None:
    memo = Memo.model_validate(
        {"headline": "h", "findings": [], "sections": [], "limitations": [], "appendix_queries": []}
    )
    assert memo.bottom_line == ""
