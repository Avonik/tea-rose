"""Back-test harness: prepare, statistics, resolve + score on fixtures, report. No network."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tearose.config import get_settings
from tearose.eval.backtest import prepare, report, resolve, score_step, stats
from tearose.eval.backtest.common import Recorder, read_csv
from tearose.qloo.fixtures import FixtureClient

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
    assert a["junior_goods_phrase"] == "squeaky dog chew toy (Silly Squeakers line)"

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
    assert len(rows) == 52
    assert all(r["senior_query"].strip() and r["junior_query"].strip() for r in rows)
    coach = next(r for r in rows if r["case_id"].startswith("coach_services"))
    assert coach["junior_query"] == "Triumph Learning"


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
    assert sen["pick_rule"] == "exact name match"
    assert "urn:tag:genre:brand:pet_supplies" in sen["universe"]["tag_ids"]
    assert jun["status"] == "proxy" and jun["entity_id"] is None
    assert jun["proxy"]["phrases_tried"] == ["dog toys"]
    assert "urn:tag:genre:brand:pet_supplies:dog_toys" in jun["proxy"]["chosen_tag_ids"]
    assert any(q["call"] == "search" for q in case["queries"])

    scores = await score_step.run(rec, resolved)
    s = scores["cases"][0]
    assert s["status"] == "scored" and s["used_proxy"] is True
    assert s["proxy_sides"] == ["junior"]
    assert s["comparators"]["junior"]["names"] == ["Ruffwear", "Petco", "Greenies"]
    # pet universe has 15 brands (BarkBox ranks 14 of 15); comparator ranks 13, 3, 10
    assert s["senior_to_junior"]["universe"] == 15
    assert s["symmetric_percentile"] == pytest.approx(1 - (26 / 3 - 1) / 15)
    assert s["junior_to_senior"]["percentile"] is None  # comparators have no fixture
    assert s["breadth_score"] is not None and s["senior_popularity"] == pytest.approx(0.9981)
    assert s["queries"]


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
            "symmetric_percentile": (k * 7 % n) / n, "senior_popularity": 0.9,
            "junior_popularity": 0.5 + k / (2 * n), "breadth_score": k / n,
        })  # fmt: skip
    return mapping, {"qloo_mode": "fixture", "mapping_sha256": "abc", "cases": cases}


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
                    "## Exclusions", "Fixture run"):  # fmt: skip
        assert section in md
    assert "On 19 decided cases, Qloo's symmetric overlap percentile correlates" in md
    assert "proxy (reported in the secondary 'with proxies' line): 1" in md
    res = json.loads(Path(out["json"]).read_text(encoding="utf-8"))
    assert res["relatedness"]["with_proxies"]["qloo"]["n"] == 20
    fe = json.loads(frontend.read_text(encoding="utf-8"))
    assert fe["status"] == "complete" and len(fe["rows"]) == 6
    assert all({"n", "metric", "value", "baseline"} <= set(r) for r in fe["rows"])

    small_map, small_scores = _synthetic(6)
    small = report.build(small_map, small_scores)
    assert "underpowered" in report.headline(small)
