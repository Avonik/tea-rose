"""Fact sentences written in code (scoring/describe.py)."""

from __future__ import annotations

import re

from tearose.qloo.models import Demographics
from tearose.schemas import (
    BridgingEvidence,
    Evidence,
    FameEvidence,
    OverlapEvidence,
    ProxyResolution,
    Resolution,
    ResolvedBrand,
    Universe,
    ZoneEvidence,
)
from tearose.scoring.describe import describe_evidence, facts_block, ordinal, pct_text

SENIOR = "Oakbarrel Spirits"
JUNIOR = "Squeaky Paws"
CAT = "urn:tag:genre:brand:household:pets"
LEAF = f"{CAT}:toys"


def proxied_resolution() -> Resolution:
    return Resolution(
        senior=ResolvedBrand(side="senior", query=SENIOR, entity_id="S1", entity_name=SENIOR),
        junior=ResolvedBrand(side="junior", query=JUNIOR),
        junior_proxy=ProxyResolution(
            side="junior", goods_phrase="chew toys", tag_options=[{"id": LEAF, "name": "Pet Toys"}],
            chosen_tag_ids=[LEAF], fit="nearest", comparator_brand_ids=["C1", "C2"],
            comparator_brand_names=["Comparator One", "Comparator Two"], rationale="test",
        ),
        universes=[
            Universe(side="senior", description="spirits brands", tag_ids=["s"], size=150),
            Universe(side="junior", description="pet-supply brands", tag_ids=[LEAF], size=13),
        ],
    )  # fmt: skip


def overlap() -> OverlapEvidence:
    return OverlapEvidence(
        senior_to_junior_rank=3, senior_to_junior_universe=13,
        senior_to_junior_percentile=0.846153846153846,
        junior_to_senior_rank=40, junior_to_senior_universe=150,
        junior_to_senior_percentile=0.74, symmetric_percentile=0.793076923076923,
        used_proxy=True,
    )  # fmt: skip


def all_sentences(facts: dict[str, list[str]]) -> list[str]:
    return [s for v in facts.values() for s in v]


def test_ordinals() -> None:
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 86, 100, 0)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "86th", "100th", "0th"
    ]  # fmt: skip
    assert pct_text(0.8636363636) == "86th percentile"


def test_proxied_junior_overlap_names_comparators_and_never_ranks_senior_in_junior_category():
    facts = describe_evidence(Evidence(overlap=overlap()), proxied_resolution())
    s2j = facts["overlap"][0]
    assert s2j == (
        "Among 13 pet-supply brands, ranked by affinity to Oakbarrel Spirits' audience, the "
        "comparator brands Comparator One and Comparator Two (standing in for Squeaky Paws, not "
        "in Qloo) rank 3 of 13 on average (85th percentile)."
    )
    assert "Small category (13 brands), rank is coarse." in facts["overlap"]
    text = " ".join(facts["overlap"])
    # the senior is ranked only among its own category, never among the junior's
    assert not re.search(rf"{SENIOR}\W*(?:s )?(?:is |was )?rank(?:s|ed)? \d+ of 13", text)
    assert "ranked among" not in text
    assert f"{SENIOR} ranks 40 of 150 (74th percentile)" in text
    assert "audience of the comparator brands Comparator One and Comparator Two" in text
    assert "Averaged over both directions, audience overlap is at the 79th percentile." in text


def test_no_number_has_more_than_two_decimals() -> None:
    ev = Evidence(
        overlap=overlap(),
        bridging=BridgingEvidence(
            category_tag_ids=[LEAF], category_rank_among_senior_tags=9, senior_tag_universe=50,
            category_affinity=0.123456, percentile=0.42, matched_tag_id=CAT,
            matched_tag_name="Pets", ancestor_levels=1,
        ),
        fame=FameEvidence(
            demographics=Demographics(), breadth_score=0.587512345, breadth_age=0.5833333,
            breadth_gender=0.6, skew_description="skews 55+, male",
            popularity_percentile=0.9312345, heatmap_coverage=0.4999181, fame_score=0.6727,
        ),
        zone=ZoneEvidence(
            points=[], concentration_index=0.3333333,
            top_regions=[{"label": "Region X", "share": 0.1234567}], geographic_overlap=0.7777777,
        ),
    )  # fmt: skip
    facts = describe_evidence(ev, proxied_resolution())
    for s in all_sentences(facts):
        assert not re.search(r"\d\.\d{3,}", s), s
    assert "Oakbarrel Spirits is at the 93rd percentile of popularity on Qloo." in facts["fame"]
    assert any("0.59" in s and "age 0.58, gender 0.60" in s for s in facts["fame"])
    assert any("Combined fame score is 0.67" in s for s in facts["fame"])
    assert "Region X (0.12)" in " ".join(facts["zone"])


def test_bridging_parent_only_hit() -> None:
    ev = Evidence(
        bridging=BridgingEvidence(
            category_tag_ids=[LEAF], category_rank_among_senior_tags=9, senior_tag_universe=50,
            category_affinity=0.5, percentile=(1 - 8 / 50) * 0.5, matched_tag_id=CAT,
            matched_tag_name="Pets", ancestor_levels=1,
        )
    )  # fmt: skip
    facts = describe_evidence(ev, proxied_resolution())["bridging"]
    assert facts == [
        "Pet Toys is not among the 50 brand-category tags most associated with Oakbarrel "
        "Spirits' audience; its parent category Pets is, at rank 9 of 50.",
        "Bridging is at the 42nd percentile after halving the rank percentile for each taxonomy "
        "level climbed (1 level).",
    ]


def test_bridging_leaf_and_nothing_present() -> None:
    leaf = BridgingEvidence(
        category_tag_ids=[LEAF], category_rank_among_senior_tags=5, senior_tag_universe=50,
        category_affinity=0.5, percentile=0.92, matched_tag_id=LEAF, matched_tag_name="Pet Toys",
    )  # fmt: skip
    assert describe_evidence(Evidence(bridging=leaf), proxied_resolution())["bridging"] == [
        "Among the 50 brand-category tags most associated with Oakbarrel Spirits' audience, "
        "Pet Toys ranks 5 of 50 (92nd percentile)."
    ]
    none = BridgingEvidence(
        category_tag_ids=[LEAF], category_rank_among_senior_tags=None, senior_tag_universe=50,
        category_affinity=None, percentile=0.0,
    )  # fmt: skip
    line = describe_evidence(Evidence(bridging=none), proxied_resolution())["bridging"][0]
    assert line.startswith("Neither Pet Toys nor any parent category appears")
    assert line.endswith("(0th percentile).")


def test_no_data_cases_and_resolved_junior() -> None:
    facts = describe_evidence(None, None)
    assert set(facts) == {"overlap", "bridging", "fame", "zone"}
    assert all("not measured" in v[0] for v in facts.values())
    empty = OverlapEvidence(
        senior_to_junior_rank=None, senior_to_junior_universe=None, junior_to_senior_rank=None,
        junior_to_senior_universe=None, symmetric_percentile=None,
    )  # fmt: skip
    res = Resolution(
        senior=ResolvedBrand(side="senior", query=SENIOR, entity_id="S1", entity_name=SENIOR),
        junior=ResolvedBrand(side="junior", query=JUNIOR, entity_id="J1", entity_name=JUNIOR),
    )
    lines = describe_evidence(Evidence(overlap=empty), res)["overlap"]
    assert all("no data" in s for s in lines)
    ev = overlap().model_copy(update={"senior_to_junior_universe": 150, "used_proxy": False})
    s2j = describe_evidence(Evidence(overlap=ev), res)["overlap"][0]
    assert s2j.startswith(f"Among 150 brands in the junior's category, ranked by affinity to "
                          f"{SENIOR}' audience, {JUNIOR} ranks 3 of 150")  # fmt: skip
    assert "comparator" not in s2j
    assert facts_block({"overlap": ["a", "b"]}) == "[overlap]\n- a\n- b"


# --------------------------------------------------------------------------------------
# harness v2: censored ranks + affinity ratio
# --------------------------------------------------------------------------------------


def resolved_pair() -> Resolution:
    return Resolution(
        senior=ResolvedBrand(side="senior", query=SENIOR, entity_id="S1", entity_name=SENIOR),
        junior=ResolvedBrand(side="junior", query=JUNIOR, entity_id="J1", entity_name=JUNIOR),
        universes=[
            Universe(side="senior", description="spirits brands", tag_ids=["s"], size=150),
            Universe(side="junior", description="pet-supply brands", tag_ids=[LEAF], size=150),
        ],
    )


def test_names_override_replaces_resolved_names() -> None:
    ev = OverlapEvidence(
        senior_to_junior_rank=3, senior_to_junior_universe=150,
        senior_to_junior_percentile=0.9866667,
        junior_to_senior_rank=12, junior_to_senior_universe=150,
        junior_to_senior_percentile=0.9266667, symmetric_percentile=0.9566667,
    )  # fmt: skip
    plain = " ".join(describe_evidence(Evidence(overlap=ev), resolved_pair())["overlap"])
    named = " ".join(
        describe_evidence(Evidence(overlap=ev), resolved_pair(), names={"senior": "Oak Barrel"})[
            "overlap"
        ]
    )
    assert SENIOR in plain and SENIOR not in named and "Oak Barrel" in named
    assert JUNIOR in named  # a side without an override keeps its resolved name


def test_censored_direction_reports_affinity_not_last_place() -> None:
    ev = OverlapEvidence(
        senior_to_junior_rank=None, senior_to_junior_universe=150,
        senior_to_junior_censored=True, senior_to_junior_depth_scanned=150,
        senior_to_junior_target_affinity=0.6612, senior_to_junior_top1_affinity=1.08,
        senior_to_junior_affinity_ratio=0.6122,
        junior_to_senior_rank=12, junior_to_senior_universe=150,
        junior_to_senior_percentile=0.9266667, junior_to_senior_target_affinity=0.91,
        junior_to_senior_affinity_ratio=0.9381,
        symmetric_percentile=0.9266667, symmetric_affinity_ratio=0.77515,
    )  # fmt: skip
    lines = describe_evidence(Evidence(overlap=ev), resolved_pair())["overlap"]
    assert lines[0] == (
        f"{JUNIOR}: affinity 0.66 to {SENIOR}' audience, 0.61 of the strongest brand in the "
        "category (pet-supply brands), beyond the 150 strongest (rank censored, no rank "
        "percentile)."
    )
    assert "counted as last" not in " ".join(lines) and "0th percentile" not in " ".join(lines)
    assert lines[1] == (
        f"Among 150 spirits brands, ranked by affinity to {JUNIOR}' audience, {SENIOR} ranks "
        "12 of 150 (93rd percentile). Affinity 0.91, 0.94 of the strongest brand in the category."
    )
    assert "Only one direction has a rank percentile; audience overlap is at the 93rd " in (
        " ".join(lines)
    )
    assert (
        "Averaged over both directions, the target's affinity is 0.78 of the strongest brand in "
        "its category (affinity ratio, 0-1)." in lines
    )
    for s in lines:
        assert not re.search(r"\d\.\d{3,}", s), s


def test_censored_without_lookup_and_proxy_mean_affinity() -> None:
    ev = OverlapEvidence(
        senior_to_junior_rank=None, senior_to_junior_universe=150,
        senior_to_junior_censored=True, senior_to_junior_depth_scanned=150,
        senior_to_junior_target_affinity=0.5, senior_to_junior_affinity_ratio=0.5,
        junior_to_senior_rank=None, junior_to_senior_universe=40,
        junior_to_senior_censored=True, junior_to_senior_depth_scanned=40,
        symmetric_percentile=None, symmetric_affinity_ratio=0.5, used_proxy=True,
    )  # fmt: skip
    lines = describe_evidence(Evidence(overlap=ev), proxied_resolution())["overlap"]
    assert lines[0].startswith(
        "The comparator brands Comparator One and Comparator Two (standing in for Squeaky Paws, "
        f"not in Qloo): mean affinity 0.50 to {SENIOR}' audience, 0.50 of the strongest brand"
    )
    assert lines[1].endswith(
        f"{SENIOR} is beyond the 40 strongest (rank censored, no rank percentile; no direct "
        "affinity available)."
    )
    assert "No rank percentile in either direction (censored or missing)." in lines
    assert any(s.startswith("In the one direction available") for s in lines)


def test_old_v1_record_without_v2_fields_still_describes() -> None:
    v1 = OverlapEvidence.model_validate(
        {"senior_to_junior_rank": 151, "senior_to_junior_universe": 150,
         "senior_to_junior_percentile": 0.0, "junior_to_senior_rank": None,
         "junior_to_senior_universe": None, "symmetric_percentile": 0.0}
    )  # fmt: skip
    assert v1.senior_to_junior_censored is False and v1.symmetric_affinity_ratio is None
    lines = describe_evidence(Evidence(overlap=v1), resolved_pair())["overlap"]
    assert "counted as last" in lines[0]
