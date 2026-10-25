"""Back-test harness: prepare, statistics, resolve + score on fixtures, report. No network."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tearose.agent.llm import ScriptedChatModel, ai_tools, tool_call
from tearose.config import get_settings
from tearose.eval.backtest import HARNESS_VERSION, prepare, report, resolve, score_step, stats
from tearose.eval.backtest.common import Recorder, read_csv
from tearose.qloo.fixtures import FixtureClient
from tearose.qloo.models import Entity

CASE_COLUMNS = [
    "case_name", "citation", "court", "year", "senior_mark", "senior_goods", "junior_mark",
    "junior_goods", "claims", "factor_relatedness_of_goods", "factor_channels_purchasers",
    "fame_found", "outcome_confusion", "opinion_url", "quote_relatedness", "confidence", "notes",
]  # fmt: skip


def _case(name: str, year: str, senior: str, s_goods: str, junior: str, j_goods: str,
          rel: str, ch: str, fame: str = "not_at_issue") -> dict[str, str]:  # fmt: skip
    row = dict.fromkeys(CASE_COLUMNS, "")
    row.update(
        case_name=name, year=year, senior_mark=senior, senior_goods=s_goods, junior_mark=junior,
        junior_goods=j_goods, factor_relatedness_of_goods=rel, factor_channels_purchasers=ch,
        fame_found=fame, confidence="high",
    )  # fmt: skip
    return row


@pytest.fixture
def five_row_csv(tmp_path: Path) -> Path:
    rows = [
        _case("Alpha v. Beta", "2010", "JACK DANIEL'S (Old No. 7 word marks)",
              "Tennessee whiskey; licensed dog collars", "BAD SPANIELS (\"Old No. 2\")",
              "squeaky dog chew toy (Silly Squeakers line)", "favors_plaintiff",
              "favors_plaintiff", "yes"),
        _case("Gamma v. Delta", "2011", "GAMMA word mark", "flavored vodka", "DELTA",
              "premium tequila", "favors_plaintiff", "neutral"),
        _case("Eps v. Zeta", "2012", "EPS / E logo", "athletic footwear", "ZETA",
              "discount footwear", "not_discussed", "favors_defendant", "no"),
        _case("Eta v. Theta", "2013", "ETA", "jewelry", "THETA", "online marketplace",
              "not_discussed", "not_discussed"),
        _case("Iota v. Kappa", "2014", "IOTA", "hamburgers", "KAPPA", "hamburger",
              "unread", "unread", "unread"),
    ]  # fmt: skip
    path = tmp_path / "cases.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CASE_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


# --------------------------------------------------------------------------------------
# prepare
# --------------------------------------------------------------------------------------


def test_prepare_mapping(five_row_csv: Path, tmp_path: Path) -> None:
    out = tmp_path / "mapping.csv"
    summary = prepare.run(five_row_csv, out)
    rows = {r["case_id"]: r for r in read_csv(out)}
    a, g, e, t, i = (rows[k] for k in (
        "alpha_v_beta_2010", "gamma_v_delta_2011", "eps_v_zeta_2012", "eta_v_theta_2013",
        "iota_v_kappa_2014"))  # fmt: skip

    assert (a["senior_query"], a["junior_query"]) == ("Jack Daniel's", "Bad Spaniels")
    assert g["senior_query"] == "Gamma" and e["senior_query"] == "Eps"
    # goods phrases: generic cleaning (parenthetical gone, text after ";" dropped)
    assert a["senior_goods_phrase"] == "Tennessee whiskey"
    assert a["junior_goods_phrase"] == "squeaky dog chew toy"
    assert (a["goods_note"], a["query_note"]) == ("generic rule", "generic rule")
    assert all(r["senior_type"] == r["junior_type"] == "brand" for r in rows.values())

    # same-category: earliest keyword wins (whiskey before dog), parentheticals ignored
    assert (a["senior_category"], a["junior_category"], a["same_category"]) == (
        "beverage/alcohol", "pet", "no")  # fmt: skip
    assert g["same_category"] == "yes" and e["same_category"] == "yes"
    assert t["same_category"] == "no" and i["same_category"] == "yes"

    # labels: agreement, disagreement (mixed), one-sided, none, unread
    assert (a["label_relatedness"], a["include_relatedness"]) == ("favors_plaintiff", "yes")
    assert (g["label_relatedness"], g["include_relatedness"], g["relatedness_exclusion"]) == (
        "mixed", "no", "mixed")  # fmt: skip
    assert (e["label_relatedness"], e["include_relatedness"]) == ("favors_defendant", "yes")
    assert (t["include_relatedness"], t["relatedness_exclusion"]) == ("no", "not_discussed")
    assert (i["include_relatedness"], i["relatedness_exclusion"]) == ("no", "unread")
    assert (a["include_fame"], a["label_fame"], e["label_fame"]) == ("yes", "yes", "no")
    assert t["include_fame"] == "no" and i["include_fame"] == "no"

    assert summary["relatedness_included"] == 2 and summary["fame_included"] == 2
    assert summary["relatedness_excluded"] == {"mixed": 1, "not_discussed": 1, "unread": 1}

    # idempotent; refuses to overwrite a hand-edited (pre-registered) mapping without --force
    assert prepare.run(five_row_csv, out)["status"] == "unchanged"
    out.write_text(out.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        prepare.run(five_row_csv, out)
    assert prepare.run(five_row_csv, out, force=True)["status"].startswith("overwritten")


def test_real_mapping_builds_without_blocked_rows() -> None:
    rows = prepare.build_mapping(read_csv(prepare.CASES_CSV))
    assert len(rows) == 80  # 52 round-1 + 28 round-2 rows
    assert all(r["senior_query"].strip() and r["junior_query"].strip() for r in rows)
    coach = next(r for r in rows if r["case_id"].startswith("coach_services"))
    assert coach["junior_query"] == "Triumph Learning"
    by_id = {r["case_id"]: r for r in rows}

    # query overrides land in query_note; entity type columns
    mattel = by_id["mattel_inc_v_mca_records_inc_2002"]
    assert (mattel["junior_query"], mattel["junior_type"], mattel["senior_type"]) == (
        "Aqua", "artist", "brand")  # fmt: skip
    assert "Barbie Girl" in mattel["query_note"] and "junior type artist" in mattel["query_note"]
    playboy = by_id["playboy_enterprises_inc_v_netscape_communications_corp_2004"]
    assert playboy["junior_query"] == "Netscape"
    assert "defunct brand; expect a search miss" in playboy["query_note"]
    mtm = by_id["multi_time_machine_inc_v_amazon_com_inc_2015"]
    assert mtm["senior_query"] == "MTM Special Ops"
    # accused side = seller brand, not the product name
    spaniels = [r for r in rows if r["junior_query"] == "VIP Products"]
    assert len(spaniels) == 4 and len({r["dispute_id"] for r in spaniels}) == 1
    assert all("seller brand" in r["query_note"] for r in spaniels)
    assert {r["junior_query"] for r in rows if r["case_id"].startswith("starbucks")} == {
        "Black Bear Micro Roastery"}  # fmt: skip
    assert by_id["vans_inc_v_mschf_product_studio_inc_2023"]["junior_query"] == "MSCHF"
    assert (
        sum(r["senior_type"] != "brand" or r["junior_type"] != "brand" for r in rows) == 2
    )  # Aqua and Survivor are artists

    # goods overrides land in goods_note; every phrase is a short category phrase
    mm = by_id["makers_mark_distillery_inc_v_diageo_north_america_inc_2012"]
    assert (mm["senior_goods_phrase"], mm["junior_goods_phrase"]) == (
        "bourbon whiskey", "premium tequila")  # fmt: skip
    assert "whisky -> whiskey" in mm["goods_note"]
    penn = by_id["the_pennsylvania_state_university_v_vintage_brand_llc_2024"]
    assert (penn["senior_goods_phrase"], penn["senior_category"]) == (
        "collegiate licensed apparel", "apparel/footwear")  # fmt: skip
    for r in rows:
        for side in ("senior", "junior"):
            phrase = r[f"{side}_goods_phrase"]
            assert phrase and not prepare.goods_needs_review(phrase), (r["case_id"], phrase)
            assert not any(ch in phrase for ch in '();$"“”') and "http" not in phrase
    assert prepare.summarize(rows)["goods_phrases_to_review"] == []


def test_clean_goods_generic_rule() -> None:
    cg = prepare.clean_goods
    assert cg("squeaky dog chew toy (Silly Squeakers line)") == "squeaky dog chew toy"
    assert cg("Tennessee whiskey; licensed merchandise incl. dog collars") == "Tennessee whiskey"
    assert cg("$30-$55 canvas tote bags") == "canvas tote bags"
    assert cg("bourbon whisky ($24)") == "bourbon whisky"  # no vocabulary change
    assert cg("premium tequila $100 to $150 per bottle") == "premium tequila per bottle"
    assert cg("distorted 'wavy' sneaker, limited drop") == "distorted wavy sneaker, limited drop"
    assert cg('“limited” "drop" sneakers') == "limited drop sneakers"
    assert cg("women’s apparel") == "women's apparel" and cg("men's apparel") == "men's apparel"
    assert cg("NFT bags sold at https://example.com/x and metabirkins.com") == (
        "NFT bags sold at and")  # fmt: skip
    assert cg("  luxury   handbags ,") == "luxury handbags"
    assert prepare.goods_needs_review("hams and other packaged foods in grocery stores")
    assert prepare.goods_needs_review("Old No. 7 whiskey")
    assert not prepare.goods_needs_review("Mexican fast food restaurant")


def test_clean_mark_keeps_acronyms() -> None:
    assert prepare.clean_mark("MTM SPECIAL OPS") == "MTM Special Ops"
    assert prepare.clean_mark("QSC POWERWAVE") == "QSC Powerwave"
    assert prepare.clean_mark("JACK DANIEL'S (Old No. 7 word marks)") == "Jack Daniel's"
    assert prepare.clean_mark("POM WONDERFUL") == "Pom Wonderful"  # vowels -> a word
    assert prepare.clean_mark("LSU") == "Lsu"  # has a vowel: not treated as an acronym


# --------------------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------------------


def test_average_ranks_ties() -> None:
    assert stats.average_ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]
    assert stats.average_ranks([3, 1, 3, 3]) == [3.0, 1.0, 3.0, 3.0]


def test_spearman_hand_computed() -> None:
    assert stats.spearman([1, 2, 3, 4, 5], [5, 6, 7, 8, 7]) == pytest.approx(0.8207826817)
    assert stats.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    # ties on both sides: x ranks [1,2.5,2.5,4], y ranks [1.5,1.5,3.5,3.5] -> 3 / sqrt(18)
    assert stats.spearman([1, 2, 2, 3], [0, 0, 1, 1]) == pytest.approx(0.7071067812)
    assert stats.spearman([1, 1, 1], [1, 2, 3]) is None  # zero variance
    assert stats.spearman([1, 2], [1, 2]) is None  # too few points


def test_auc_hand_computed() -> None:
    # pos {0.9, 0.5}, neg {0.5, 0.1}: pairs 1 + 1 + 0.5 (tie) + 1 = 3.5 of 4
    assert stats.auc([0.9, 0.5, 0.5, 0.1], [True, True, False, False]) == pytest.approx(0.875)
    assert stats.auc([0.1, 0.9], [True, False]) == 0.0
    assert stats.auc([0.1, 0.9], [True, True]) is None


def test_bootstrap_ci_deterministic_and_brackets_value() -> None:
    xs = [0.1, 0.2, 0.35, 0.4, 0.5, 0.55, 0.7, 0.8, 0.85, 0.95]
    ys = [0, 0, 1, 0, 1, 1, 2, 2, 1, 2]
    pairs = list(zip(xs, ys, strict=True))

    def rho(p: list[tuple[float, int]]) -> float | None:
        return stats.spearman([a for a, _ in p], [b for _, b in p])

    lo, hi, valid = stats.bootstrap_ci(pairs, rho)
    assert lo is not None and hi is not None
    assert lo <= rho(pairs) <= hi <= 1.0  # type: ignore[operator]
    assert valid > 1900
    assert stats.bootstrap_ci(pairs, rho) == (lo, hi, valid)  # fixed seed
    assert stats.percentile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)


# --------------------------------------------------------------------------------------
# resolve + score on fixtures
# --------------------------------------------------------------------------------------


def _mapping_row() -> dict[str, str]:
    return {
        "case_id": "jd_v_bad_spaniels", "dispute_id": "jack_daniels_vs_bad_spaniels",
        "case_name": "VIP v. Jack Daniel's", "year": "2018", "confidence": "high",
        "senior_query": "Jack Daniel's", "junior_query": "Bad Spaniels", "query_note": "",
        "senior_goods_phrase": "Tennessee whiskey", "junior_goods_phrase": "dog toys",
        "senior_category": "beverage/alcohol", "junior_category": "pet", "same_category": "no",
        "factor_relatedness": "favors_plaintiff", "factor_channels": "favors_plaintiff",
        "include_relatedness": "yes", "label_relatedness": "favors_plaintiff",
        "relatedness_exclusion": "", "include_fame": "yes", "label_fame": "yes",
    }  # fmt: skip


async def test_resolve_and_score_fixture_end_to_end() -> None:
    rec = Recorder(FixtureClient(get_settings().fixtures_dir), live=False)
    resolved = await resolve.run(rec, [_mapping_row()], "fixture", "sha")
    case = resolved["cases"][0]
    sen, jun = case["senior"], case["junior"]
    assert sen["status"] == "resolved" and sen["entity_name"] == "Jack Daniel's"
    assert sen["pick_rule"] == "exact"
    assert resolved["harness_version"] == HARNESS_VERSION == 3
    assert resolved["resolver"] == case["resolver"] == "rule" and resolved["model"] is None
    # harness v2 universe = the brand's OWN most specific genre:brand tags from /search
    # (wine_and_spirits and spirits are ancestors of whiskey and drop out); no insights call
    assert sen["universe"]["tag_ids"] == ["urn:tag:genre:brand:wine_and_spirits:spirits:whiskey"]
    assert sen["universe"]["tag_names"] == ["Whiskey"]
    assert sen["universe"]["source"] == "entity own tags"
    assert len(sen["universe"]["own_genre_tag_ids"]) == 3
    assert not [q for q in case["queries"] if q["call"] == "insights_tags"]
    # junior: no search hit -> proxy via the brand taxonomy, "nearest" (no toy/pet-supply node)
    assert jun["status"] == "proxy" and jun["entity_id"] is None
    assert jun["pick_rule"] == "no results"
    assert jun["proxy"]["chosen_tag_ids"] == ["urn:tag:genre:brand:food_and_beverage:pet_food"]
    assert jun["proxy"]["fit"] == "nearest"
    assert "nearest category" in jun["proxy"]["fit_note"]
    assert jun["proxy"]["rule"].startswith("brand taxonomy")
    assert not any(q["call"] == "tags_search" for q in case["queries"])  # no free-text lookup
    assert any(q["call"] == "brand_taxonomy" for q in case["queries"])
    assert any(q["call"] == "search" for q in case["queries"])

    scores = await score_step.run(rec, resolved)
    s = scores["cases"][0]
    assert s["status"] == "scored" and s["used_proxy"] is True
    assert s["proxy_sides"] == ["junior"]
    assert s["comparators"]["junior"]["names"] == ["Ruffwear", "Petco", "Greenies"]
    assert s["comparator_source"] == {"junior": "rule"}  # rule resolver: always the code rule
    # pet universe has 15 brands (BarkBox ranks 14 of 15); comparator ranks 13, 3, 10
    assert s["senior_to_junior"]["universe"] == 15
    assert s["symmetric_percentile"] == pytest.approx(1 - (26 / 3 - 1) / 15)
    assert s["junior_to_senior"]["percentile"] is None  # comparators have no fixture
    # second signal: each comparator's affinity looked up directly (same seeds/filter/type)
    s2j = s["senior_to_junior"]
    assert s2j["censored"] is False and s2j["depth_scanned"] == 15
    assert s2j["affinity_ratio"] == pytest.approx(s2j["target_affinity"] / s2j["top1_affinity"])
    assert s["symmetric_affinity_ratio"] == pytest.approx(s2j["affinity_ratio"])
    lookups = _params(s, "target_affinity")
    assert {p["filter.results.entities"] for p in lookups} == set(s["comparators"]["junior"]["ids"])
    assert all(p["filter.tags"] == "urn:tag:genre:brand:food_and_beverage:pet_food"
               for p in lookups)  # fmt: skip
    assert scores["harness_version"] == 3 and scores["resolver"] == "rule"
    assert "pick_vs_rule" not in s  # rule resolver: nothing to compare
    assert s["breadth_score"] is not None and s["senior_popularity"] == pytest.approx(0.9981)
    assert s["queries"]


async def test_resolve_universe_depth1_own_tag_and_insights_fallback(tmp_path: Path) -> None:
    rec = Recorder(FixtureClient(get_settings().fixtures_dir), live=False)
    smash = await resolve.resolve_side(rec, "Smashburger", "hamburger restaurants")
    # only a top family among its own tags: used, since nothing deeper exists
    assert smash["universe"]["tag_ids"] == ["urn:tag:genre:brand:dining"]
    assert smash["universe"]["source"] == "entity own tags"

    genre = "urn:tag:genre:brand"
    search = {
        "results": [
            {
                "entity_id": "E-AC",
                "name": "Acme",
                "types": ["urn:entity:brand"],
                "tags": [{"tag_id": "urn:tag:keyword:x", "name": "X", "type": "urn:tag:keyword"}],
            }
        ]
    }
    tags = {"results": {"tags": [{"tag_id": f"{genre}:dining", "name": "Dining",
                                  "subtype": genre}]}}  # fmt: skip
    (tmp_path / "search_brand_acme.json").write_text(json.dumps(search), encoding="utf-8")
    (tmp_path / "insights_tag_seed_acme.json").write_text(json.dumps(tags), encoding="utf-8")
    rec2 = Recorder(FixtureClient(tmp_path), live=False)
    acme = await resolve.resolve_side(rec2, "Acme", "burgers")
    assert acme["universe"]["source"] == "insights tags (fallback)"
    assert acme["universe"]["tag_ids"] == [f"{genre}:dining"]
    assert any(q["call"] == "insights_tags" for q in rec2.queries)


def _params(case_or_score: dict[str, object], call: str) -> list[dict[str, object]]:
    return [q["params"] for q in case_or_score["queries"] if q["call"] == call]  # type: ignore[index,union-attr]


async def test_resolve_and_score_honour_entity_type() -> None:
    rec = Recorder(FixtureClient(get_settings().fixtures_dir), live=False)
    row = {
        **_mapping_row(), "case_id": "mattel_v_aqua", "senior_query": "Jack Daniel's",
        "junior_query": "Aqua", "senior_type": "brand", "junior_type": "artist",
        "junior_goods_phrase": "dog toys",  # a phrase the fixtures can serve as a universe
    }  # fmt: skip
    resolved = await resolve.run(rec, [row], "fixture", "sha")
    case = resolved["cases"][0]
    sen, jun = case["senior"], case["junior"]
    assert (jun["status"], jun["entity_name"], jun["type"]) == ("resolved", "Aqua", "artist")
    assert jun["type_urn"] == "urn:entity:artist" and sen["type"] == "brand"
    searches = {p["query"]: p["types"] for p in _params(case, "search")}
    assert searches == {"Jack Daniel's": "urn:entity:brand", "Aqua": "urn:entity:artist"}

    s = (await score_step.run(rec, resolved))["cases"][0]
    by_seed = {p["signal.interests.entities"]: p["filter.type"]
               for p in _params(s, "insights_entities")}  # fmt: skip
    assert by_seed[sen["entity_id"]] == "urn:entity:artist"  # senior->junior ranks artists
    assert by_seed[jun["entity_id"]] == "urn:entity:brand"  # junior->senior ranks brands

    # no type column (older mapping) -> brand
    old = {k: v for k, v in _mapping_row().items() if not k.endswith("_type")}
    doc = await resolve.run(rec, [old], "fixture", "sha")
    assert doc["cases"][0]["junior"]["type"] == "brand"


def _ent(eid: str, name: str) -> Entity:
    return Entity(entity_id=eid, name=name, subtype="urn:entity:brand")


@pytest.mark.parametrize(
    ("query", "garbage"),
    [
        ("VIP Products", "EOS Products"),
        ("Haute Diggity Dog", "The Last of Us Part II"),
        ("Triumph Learning", "Triumph Motorcycles"),
        ("Black Bear Micro Roastery", "Black Bear Diner"),
    ],
)
def test_pick_entity_rejects_unrelated_top_hit(query: str, garbage: str) -> None:
    assert resolve.pick_entity(query, [_ent("G", garbage)]) == (None, "miss")


def test_pick_entity_exact_after_normalisation_beats_rank() -> None:
    results = [_ent("A", "Jack Daniel's Tennessee Honey"), _ent("B", "Jack Daniel's")]
    entity, rule = resolve.pick_entity("Jack Daniels", results)
    assert (entity.entity_id, rule) == ("B", "exact")  # type: ignore[union-attr]
    assert resolve.pick_entity("x", []) == (None, "no results")


async def test_resolve_side_same_entity_guard_makes_junior_a_miss() -> None:
    rec = Recorder(FixtureClient(get_settings().fixtures_dir), live=False)
    senior = await resolve.resolve_side(rec, "Jack Daniel's", "Tennessee whiskey")
    junior = await resolve.resolve_side(
        rec, "Jack Daniels", "bourbon whiskey", avoid_entity_id=senior["entity_id"]
    )
    assert senior["status"] == "resolved"
    assert junior["entity_id"] is None and junior["pick_rule"] == "picked the other side's entity"
    assert junior["status"] == "proxy"
    assert junior["proxy"]["chosen_tag_names"][0] == "Whiskey"
    assert junior["proxy"]["fit"] == "exact"


async def test_tags_for_phrase_falls_back_to_free_text_without_taxonomy(tmp_path: Path) -> None:
    (tmp_path / "tags_search_dog_toys.json").write_text(
        json.dumps({"results": {"tags": [{"id": "urn:tag:x:dog_toys", "name": "Dog Toys"}]}}),
        encoding="utf-8",
    )
    rec = Recorder(FixtureClient(tmp_path), live=False)
    out = await resolve.tags_for_phrase(rec, "dog toys")
    assert out["chosen_tag_ids"] == ["urn:tag:x:dog_toys"]
    assert out["rule"].startswith("brand taxonomy unavailable; free-text")
    assert out["fit"] == "partial"


# --------------------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------------------


def _synthetic(n: int) -> tuple[list[dict[str, str]], dict[str, object]]:
    mapping, cases = [], []
    for k in range(n):
        label = "favors_plaintiff" if k % 3 else "favors_defendant"
        m = {
            **_mapping_row(),
            "case_id": f"c{k}",
            "dispute_id": f"d{k}",
            "year": str(2000 + k),
            "case_name": f"Case {k}",
            "label_relatedness": label,
            "same_category": "yes" if k % 2 else "no",
            "label_fame": "yes" if k % 4 else "no",
        }
        mapping.append(m)
        cases.append({
            "case_id": f"c{k}", "status": "scored", "used_proxy": k == 0,
            "symmetric_percentile": None if k == 1 else (k * 7 % n) / n,
            "symmetric_affinity_ratio": 0.4 + (k * 3 % n) / (2 * n), "senior_popularity": 0.9,
            "junior_popularity": 0.5 + k / (2 * n), "breadth_score": k / n,
            "pick_vs_rule": {
                "senior": {"agent": "The Hershey Company", "rule": None, "differs": k == 2},
                "junior": {"agent": "Chase Bank", "rule": "Chase Bank", "differs": False},
            },
        })  # fmt: skip
    doc = {
        "harness_version": 3,
        "resolver": "agent",
        "model": "test-model",
        "qloo_mode": "fixture",
        "mapping_sha256": "abc",
        "cases": cases,
    }
    return mapping, doc


def test_report_sections(tmp_path: Path) -> None:
    mapping, scores = _synthetic(20)
    frontend = tmp_path / "backtest.json"
    frontend.write_text(json.dumps({"status": "pending", "note": "x", "rows": [
        {"n": "pending", "metric": "Agreement: LLM-only baseline", "value": "pending",
         "baseline": "n/a"}]}), encoding="utf-8")  # fmt: skip
    out = report.run(mapping, scores, tmp_path / "results", True, frontend_json=frontend)
    md = Path(out["markdown"]).read_text(encoding="utf-8")
    for section in ("## Headline", "#### Primary (no proxy)", "Baseline: same-category",
                    "Baseline: popularity product", "## Fame", "## Per-case table",
                    "## Exclusions", "Fixture run", "## Deviations from pre-registration",
                    "Harness version: **3**", "Qloo symmetric affinity ratio",
                    "Qloo symmetric rank percentile (censored ranks excluded)",
                    "affinity ratio | residual (ratio)"):  # fmt: skip
        assert section in md, section
    # the dated deviation text: what changed, and that labels/mapping did not
    assert "On 2026-10-25, after run 1" in md and "kept unchanged as the record" in md
    for change in ("Universe rule", "Censored ranks", "Taxonomy synonym",
                   "Labels (`cases_candidates.csv`) and `mapping.csv` are unchanged"):  # fmt: skip
        assert change in md
    # harness v3: dated paragraph, resolver header line, per-case pick-vs-rule note
    assert "**Harness v3 (2026-10-25): identification by the product's resolver.**" in md
    for phrase in ("model-driven resolve node", "Scoring is unchanged",
                   "`mapping.csv` are unchanged; the v1 and v2 reports are kept"):  # fmt: skip
        assert phrase in md, phrase
    assert "Resolver: **agent** (the product's resolve node, model `test-model`)" in md
    assert "| pick vs rule |" in md
    assert "senior: The Hershey Company (rule: miss)" in md
    assert md.count("(rule: ") == 1  # only the differing side of the differing case
    # v3 files; run 1 and v2 names are never written by harness v3
    assert Path(out["markdown"]).name.endswith("_v3.md")
    assert Path(out["json"]).name.endswith("_v3.json")
    written = sorted(p.name for p in (tmp_path / "results").iterdir())
    assert written == sorted([Path(out["markdown"]).name, Path(out["json"]).name])
    # case 1 has no rank percentile but an affinity ratio: still in the subset, per-signal n
    assert "On 18 decided cases, Qloo's symmetric overlap percentile correlates" in md
    assert "affinity ratio (second Qloo signal, n = 19)" in md
    assert "proxy (reported in the secondary 'with proxies' line): 1" in md
    res = json.loads(Path(out["json"]).read_text(encoding="utf-8"))
    assert res["harness_version"] == 3 and res["resolver"] == "agent"
    assert res["model"] == "test-model"
    wp = res["relatedness"]["with_proxies"]
    assert (wp["qloo"]["n"], wp["qloo_ratio"]["n"]) == (19, 20)
    for subset in ("primary", "with_proxies", "dedup_by_dispute", "relatedness_factor_only",
                   "channels_factor_only"):  # fmt: skip
        assert "qloo_ratio" in res["relatedness"][subset]
    case1 = next(c for c in res["per_case"] if c["case_id"] == "c1")
    assert case1["residual"] is None and case1["residual_ratio"] is not None
    fe = json.loads(frontend.read_text(encoding="utf-8"))
    assert fe["status"] == "complete" and len(fe["rows"]) == 8 and fe["harness_version"] == 3
    assert all({"n", "metric", "value", "baseline"} <= set(r) for r in fe["rows"])
    assert sum("affinity ratio" in r["metric"] for r in fe["rows"]) == 2
    assert "Harness v2" in fe["note"] and "Harness v3" in fe["note"]

    # v1 / v2 scores.json are refused instead of overwriting earlier runs' file names
    for old in (1, 2):
        with pytest.raises(SystemExit):
            report.run(mapping, {**scores, "harness_version": old}, tmp_path / f"r{old}", False)
    # rule resolver: header says so
    assert "Resolver: **rule**" in report.render_markdown(
        report.build(mapping, {**scores, "resolver": "rule", "model": None})
    )

    small_map, small_scores = _synthetic(6)
    small = report.build(small_map, small_scores)
    assert "underpowered" in report.headline(small)


# --------------------------------------------------------------------------------------
# harness v3: the product's resolve node as the resolver (scripted model, fixtures)
# --------------------------------------------------------------------------------------

JD_ID = "FA4E0000-0000-4000-A000-000000000001"
INO_ID = "FA4E0000-0000-4000-A000-000000000005"
SMASH_ID = "FA4E0000-0000-4000-A000-000000000006"
AQUA_ID = "FA4E0000-0000-4000-A000-0000000000A1"
PET_FOOD = "urn:tag:genre:brand:food_and_beverage:pet_food"


def _agent_rows() -> list[dict[str, str]]:
    base = {**_mapping_row(), "senior_type": "brand", "junior_type": "brand"}
    return [
        {**base, "junior_query": "Bad Spaniels"},
        {**base, "case_id": "ino_v_smash", "dispute_id": "ino", "case_name": "In-N-Out v. Smash",
         "year": "2025", "senior_query": "In-N-Out", "junior_query": "Smashburger",
         "senior_goods_phrase": "hamburger restaurants",
         "junior_goods_phrase": "hamburger restaurants"},
        {**base, "case_id": "mattel_v_aqua", "junior_query": "Aqua", "junior_type": "artist",
         "case_name": "Mattel v. MCA", "year": "2002"},
    ]  # fmt: skip


def _side(entity_id: str | None = None, **kw: object) -> dict[str, object]:
    return {"entity_id": entity_id, "rationale": "scripted", **kw}


def _agent_model() -> ScriptedChatModel:
    def loop(a: str, b: str) -> list[object]:
        return [ai_tools(tool_call("qloo_search", query=a), tool_call("qloo_search", query=b)),
                "done"]  # fmt: skip

    return ScriptedChatModel(
        scripts={
            "resolve": [*loop("Jack Daniel's", "Bad Spaniels"), *loop("In-N-Out", "Smashburger"),
                        *loop("Jack Daniel's", "Aqua")],
            "ResolveDecision": [
                {"senior": _side(JD_ID, query="Jack Daniel's"),
                 "junior": _side(proxy_goods_phrase="dog toys",
                                 proxy_taxonomy_choices=[{"tag_id": PET_FOOD, "fit": "nearest"}])},
                {"senior": _side(INO_ID), "junior": _side(SMASH_ID)},
                # third case: no decision left -> structured output fails -> recorded, continue
            ],
        }
    )  # fmt: skip


async def test_resolve_agent_records_picks_and_continues_after_failure() -> None:
    rows = _agent_rows()
    model = _agent_model()
    rec = Recorder(FixtureClient(get_settings().fixtures_dir), live=False)
    doc = await resolve.run(
        rec, rows, "fixture", "sha", resolver="agent",
        model_factory=lambda strong=False: model, model_name="scripted-test",
    )  # fmt: skip
    assert (doc["harness_version"], doc["resolver"], doc["model"]) == (3, "agent", "scripted-test")
    jd, ino, aqua = doc["cases"]

    # case 1: senior picked by the model, junior proxied via the brand taxonomy
    sen, jun = jd["senior"], jd["junior"]
    assert (sen["status"], sen["entity_id"], sen["entity_name"]) == (
        "resolved", JD_ID, "Jack Daniel's")  # fmt: skip
    assert sen["popularity"] is not None
    assert "Jack Daniel's Tennessee Honey" in sen["candidates_considered"]
    assert sen["name_check"]["rule"] == "exact" and sen["name_check"]["similarity"] == 1.0
    assert "name-rule guardrail" in sen["name_check"]["note"]
    assert sen["universe"]["source"] == "entity own tags"
    assert sen["universe"]["tag_names"] == ["Whiskey"]
    assert sen["rule_pick"]["entity_id"] == JD_ID and sen["agrees_with_rule"] is True
    assert (jun["status"], jun["entity_id"]) == ("proxy", None)
    assert jun["proxy"]["chosen_tag_ids"] == [PET_FOOD] and jun["proxy"]["fit"] == "nearest"
    assert jun["proxy"]["comparator_entity_ids"] == []
    assert jun["universe"]["tag_ids"] == [PET_FOOD]
    assert jd["tool_calls"] == 2 and jd["llm_calls"] >= 2  # scripted structured calls bypass
    assert jd["model"] == "scripted-test" and jd["error"] is None and jd["resolver"] == "agent"

    # case 2: both sides picked; the rule pick is computed alongside
    assert (ino["senior"]["entity_id"], ino["junior"]["entity_id"]) == (INO_ID, SMASH_ID)
    assert ino["senior"]["entity_name"] == "In-N-Out Burger"
    assert ino["senior"]["agrees_with_rule"] == (
        ino["senior"]["rule_pick"]["entity_id"] == INO_ID)  # fmt: skip

    # case 3: structured decision failed -> error recorded, code fallbacks, run continued;
    # the artist side was searched as an artist (type hint); the rule finds Aqua there
    assert aqua["error"] and aqua["error"].startswith("Resolution decision failed")
    assert aqua["junior"]["type"] == "artist" and aqua["junior"]["entity_id"] is None
    assert aqua["junior"]["rule_pick"]["entity_id"] == AQUA_ID
    assert aqua["junior"]["agrees_with_rule"] is False
    agent_types = {
        q["params"].get("types")
        for q in aqua["queries"]
        if q["call"] == "agent:/search" and "aqua" in str(q["params"]).lower()
    }
    assert agent_types == {"urn:entity:artist"}

    # no label or factor column reaches the model; case name/year and the type hint do
    prompts = "\n".join(model.prompts_for("resolve"))
    assert "favors_plaintiff" not in prompts and "label_relatedness" not in prompts
    assert "Mattel v. MCA (2002)" in prompts and "is a Qloo artist" in prompts

    summary = resolve.summarize(doc)
    assert summary["resolver"] == "agent" and summary["errors"] == 1
    assert summary["llm_calls"] == sum(c["llm_calls"] for c in doc["cases"]) >= 6
    assert summary["picks_differing_from_rule"] >= 1

    # scoring stays in code and accepts the agent's resolved.json; picks pass through
    scores = await score_step.run(rec, doc)
    assert scores["resolver"] == "agent" and scores["model"] == "scripted-test"
    s1 = scores["cases"][0]
    assert s1["status"] == "scored" and s1["proxy_sides"] == ["junior"]
    assert s1["comparator_source"] == {"junior": "rule"}  # the agent kept no comparators
    assert any("agent kept no comparators" in n for n in s1["notes"])
    assert s1["pick_vs_rule"]["senior"] == {"agent": "Jack Daniel's", "rule": "Jack Daniel's",
                                            "differs": False}  # fmt: skip
    assert scores["cases"][2]["resolver_error"]


async def test_resolve_agent_same_entity_guard() -> None:
    row = {**_mapping_row(), "junior_query": "Jack Daniels", "junior_goods_phrase": "bourbon"}
    model = ScriptedChatModel(scripts={
        "resolve": [ai_tools(tool_call("qloo_search", query="Jack Daniel's")), "done"],
        "ResolveDecision": [{"senior": _side(JD_ID), "junior": _side(JD_ID)}],
    })  # fmt: skip
    rec = Recorder(FixtureClient(get_settings().fixtures_dir), live=False)
    doc = await resolve.run(rec, [row], "fixture", "sha", resolver="agent",
                            model_factory=lambda strong=False: model)  # fmt: skip
    case = doc["cases"][0]
    assert case["senior"]["entity_id"] == JD_ID
    assert case["junior"]["entity_id"] is None and case["junior"]["status"] != "resolved"
    assert any("other side's entity" in n for n in case["notes"])


def _write_mapping(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


def test_cli_resolver_choice_and_version_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tearose.agent import llm
    from tearose.eval.backtest.__main__ import main

    mapping = _write_mapping(tmp_path / "mapping.csv", [_agent_rows()[0]])
    out = tmp_path / "out"

    main(["resolve", "--resolver", "rule", "--mapping", str(mapping), "--out", str(out)])
    doc = json.loads((out / "resolved.json").read_text(encoding="utf-8"))
    assert doc["resolver"] == "rule" and doc["harness_version"] == 3
    assert doc["cases"][0]["senior"]["pick_rule"] == "exact"

    # default resolver = agent; the configured model is replaced by the scripted one
    model = _agent_model()
    monkeypatch.setattr(llm, "get_chat_model", lambda strong=False: model)
    main(["resolve", "--mapping", str(mapping), "--out", str(out)])
    doc = json.loads((out / "resolved.json").read_text(encoding="utf-8"))
    assert doc["resolver"] == "agent" and doc["model"] == get_settings().llm_model
    assert doc["cases"][0]["senior"]["entity_id"] == JD_ID

    # score refuses a resolved.json from harness v2
    v2 = {**doc, "harness_version": 2}
    (out / "resolved.json").write_text(json.dumps(v2), encoding="utf-8")
    with pytest.raises(SystemExit, match="harness v2"):
        main(["score", "--mapping", str(mapping), "--out", str(out)])


async def test_score_uses_agent_comparators_when_agent_resolved() -> None:
    barkbox = "FA4E0000-0000-4000-A000-000000000004"
    loop = [ai_tools(tool_call("qloo_search", query="Jack Daniel's"),
                     tool_call("qloo_search", query="Bad Spaniels"),
                     tool_call("qloo_search", query="BarkBox")), "done"]  # fmt: skip
    decision = {
        "senior": _side(JD_ID),
        "junior": _side(proxy_taxonomy_choices=[{"tag_id": PET_FOOD, "fit": "nearest"}],
                        comparator_entity_ids=[barkbox]),
    }  # fmt: skip
    model = ScriptedChatModel(scripts={"resolve": loop, "ResolveDecision": [decision]})
    rec = Recorder(FixtureClient(get_settings().fixtures_dir), live=False)
    doc = await resolve.run(rec, [_agent_rows()[0]], "fixture", "sha", resolver="agent",
                            model_factory=lambda strong=False: model)  # fmt: skip
    proxy = doc["cases"][0]["junior"]["proxy"]
    assert proxy["comparator_entity_ids"] == [barkbox]
    assert proxy["comparator_popularity"] == [pytest.approx(0.9312)]

    scores = await score_step.run(rec, doc)
    s = scores["cases"][0]
    assert s["comparator_source"] == {"junior": "agent"}
    comps = s["comparators"]["junior"]
    assert (comps["source"], comps["ids"], comps["names"]) == ("agent", [barkbox], ["BarkBox"])
    assert not any("code rule used" in n for n in s["notes"])
    assert barkbox in {p["filter.results.entities"] for p in _params(s, "target_affinity")}
    assert "agent resolver" in scores["comparator_rule"]


def test_cli_resolve_only_merges_and_refuses_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tearose.eval.backtest.__main__ import main

    mapping = _write_mapping(tmp_path / "mapping.csv", _agent_rows()[:2])
    out = tmp_path / "out"
    args = ["--resolver", "rule", "--mapping", str(mapping), "--out", str(out)]
    main(["resolve", *args])
    path = out / "resolved.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    before["cases"][0]["sentinel"] = "kept"  # an untouched case must survive byte for byte
    before["cases"][1]["senior"]["entity_id"] = "stale"
    path.write_text(json.dumps(before), encoding="utf-8")
    capsys.readouterr()

    main(["resolve", "--only", " ino_v_smash ", *args])
    summary = capsys.readouterr().out
    assert '"re_resolved": 1' in summary and '"cases": 2' in summary
    after = json.loads(path.read_text(encoding="utf-8"))
    assert [c["case_id"] for c in after["cases"]] == ["jd_v_bad_spaniels", "ino_v_smash"]
    assert after["cases"][0] == before["cases"][0]
    ino = after["cases"][1]
    assert ino["senior"]["entity_id"] == INO_ID and ino["re_resolved_at"]
    assert {k: v for k, v in after.items() if k != "cases"} == {
        k: v for k, v in before.items() if k != "cases"}  # fmt: skip

    # score reads the merged file (extra re_resolved_at field) without complaint
    main(["score", "--mapping", str(mapping), "--out", str(out)])
    assert len(json.loads((out / "scores.json").read_text(encoding="utf-8"))["cases"]) == 2

    with pytest.raises(SystemExit, match="not in mapping"):
        main(["resolve", "--only", "nope", *args])
    for key, bad, msg in (("mapping_sha256", "other", "mapping.csv"),
                          ("harness_version", 2, "harness version")):  # fmt: skip
        path.write_text(json.dumps({**after, key: bad}), encoding="utf-8")
        with pytest.raises(SystemExit, match=msg):
            main(["resolve", "--only", "ino_v_smash", *args])
        assert json.loads(path.read_text(encoding="utf-8"))[key] == bad  # file left as it was
