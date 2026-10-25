"""Qloo layer: test-safety settings, name matching, brand taxonomy, parsers. No network."""

from __future__ import annotations

import os
from typing import Any

import pytest

from tearose.config import BACKEND_DIR, get_settings
from tearose.qloo import params as P
from tearose.qloo.client import GENRE_BRAND, get_qloo_client
from tearose.qloo.fixtures import FixtureClient
from tearose.qloo.models import Entity, QlooQuery, Tag
from tearose.qloo.names import match_rule, normalize_name, pick_by_name
from tearose.qloo.parse import parse_compare
from tearose.qloo.taxonomy import (
    BIGRAMS,
    NEAREST_NOTE,
    SYNONYMS,
    load_brand_taxonomy,
    map_goods_phrase,
    node_from_tag_id,
)

FIXTURES = BACKEND_DIR / "fixtures" / "qloo"

# --------------------------------------------------------------------------------------
# tests never run against live Qloo or a real LLM, whatever backend/.env says
# --------------------------------------------------------------------------------------


def test_settings_are_forced_to_fixture_mode() -> None:
    s = get_settings()
    assert s.qloo_mode == "fixture"
    assert s.qloo_api_key == "" and s.llm_api_key == ""
    assert os.environ["QLOO_MODE"] == "fixture"
    assert isinstance(get_qloo_client(), FixtureClient)


# --------------------------------------------------------------------------------------
# FIX A: name matching
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("Jack Daniel's", "jack daniels"),
        ("Jack Daniel’s Properties, Inc.", "jack daniels properties"),
        ("adidas", "adidas"),
        ("Häagen-Dazs", "haagen dazs"),
        ("Barnes & Noble", "barnes and noble"),
        ("Acme Co.", "acme"),
        ("Foo Holdings LLC", "foo holdings"),
        ("Company", "company"),  # a lone corporate word is not stripped to nothing
    ],
)
def test_normalize_name(raw: str, norm: str) -> None:
    assert normalize_name(raw) == norm


def test_match_rule_exact_fuzzy_miss() -> None:
    assert match_rule("Jack Daniels", "Jack Daniel's") == "exact"
    assert match_rule("Adidas", "adidas") == "exact"
    assert match_rule("Bark Box", "BarkBox") == "exact"
    assert match_rule("Jack Daniel's", "Jack Daniel's Distillery").startswith("fuzzy:")
    assert match_rule("Smashburgers", "Smashburger").startswith("fuzzy:0.9")
    assert match_rule("Jack Daniel's", "Jack Daniel's Tennessee Honey") == "miss"  # 2 extra
    for q, garbage in [
        ("VIP Products", "EOS Products"),
        ("Haute Diggity Dog", "The Last of Us Part II"),
        ("Triumph Learning", "Triumph Motorcycles"),
        ("Black Bear Micro Roastery", "Black Bear Diner"),
    ]:
        assert match_rule(q, garbage) == "miss", (q, garbage)


def _e(eid: str, name: str) -> Entity:
    return Entity(entity_id=eid, name=name)


def test_pick_by_name_never_takes_the_first_hit() -> None:
    assert pick_by_name("MSCHF", []) == (None, "miss")
    assert pick_by_name("Triumph Learning", [_e("1", "Triumph Motorcycles")]) == (None, "miss")
    ents = [_e("1", "Jack Daniel's Distillery"), _e("2", "Jack Daniel's")]
    assert pick_by_name("Jack Daniels", ents) == (ents[1], "exact")
    # several query strings (mark + company name); avoid_ids skips an entity
    hit, rule = pick_by_name(["Bad Spaniels", "Jack Daniel's"], ents, avoid_ids=["2"])
    assert hit is ents[0] and rule.startswith("fuzzy:")


# --------------------------------------------------------------------------------------
# FIX B: insights tags restricted to brand genres
# --------------------------------------------------------------------------------------


async def test_insights_tags_sends_genre_brand_filter_by_default() -> None:
    client = FixtureClient(FIXTURES)
    tags, q = await client.insights_tags(["FA4E0000-0000-4000-A000-000000000001"])
    assert q.params["filter.tag.types"] == GENRE_BRAND
    assert tags and all(t.tag_type == GENRE_BRAND for t in tags)
    _, q2 = await client.insights_tags(["x"], tag_types=None)
    assert "filter.tag.types" not in q2.params
    assert P.insights_tags_params(["a", "b"], 50, ["t1", "t2"])["filter.tag.types"] == "t1,t2"


# --------------------------------------------------------------------------------------
# FIX C: brand taxonomy
# --------------------------------------------------------------------------------------


class _LetterClient:
    """Answers letter queries from a node list by name substring; counts calls."""

    def __init__(self, nodes: list[tuple[str, str]]) -> None:
        self.nodes = nodes
        self.calls: list[tuple[str, Any]] = []

    async def tags_search(self, query: str, *, tag_types: Any = None, take: int = 20):
        self.calls.append((query, tag_types))
        hits = [
            Tag(tag_id=i, name=n, tag_type=GENRE_BRAND) for i, n in self.nodes if query in n.lower()
        ][:take]
        return hits, QlooQuery(endpoint="/v2/tags", params={})


async def test_load_brand_taxonomy_harvests_dedupes_and_memoises() -> None:
    client = _LetterClient(
        [
            (f"{GENRE_BRAND}:wine_and_spirits", "Wine & Spirits"),
            (f"{GENRE_BRAND}:wine_and_spirits:spirits:whiskey", "Whiskey"),
            (f"{GENRE_BRAND}:food_and_beverage:pet_food", "Pet Food"),
            ("urn:tag:keyword:qloo:whiskey", "Whiskey"),  # not a brand genre: ignored
        ]
    )
    nodes = await load_brand_taxonomy(client)
    assert len(client.calls) == 26
    assert {c[0] for c in client.calls} == set("abcdefghijklmnopqrstuvwxyz")
    assert all(c[1] == [GENRE_BRAND] for c in client.calls)
    assert [n.name for n in nodes] == ["Pet Food", "Wine & Spirits", "Whiskey"]  # deduped
    whiskey = nodes[2]
    assert whiskey.path == ("wine_and_spirits", "spirits", "whiskey") and whiskey.depth == 3
    assert whiskey.parent == f"{GENRE_BRAND}:wine_and_spirits:spirits"
    assert nodes[1].parent is None
    assert await load_brand_taxonomy(client) is nodes and len(client.calls) == 26  # memo


async def test_fixture_taxonomy_is_harvested_from_letter_queries() -> None:
    nodes = await load_brand_taxonomy(FixtureClient(FIXTURES))
    assert len(nodes) == 67
    assert len({n.path[0] for n in nodes}) == 15
    assert node_from_tag_id("urn:tag:keyword:x", "X") is None


def test_synonym_targets_are_taxonomy_paths() -> None:
    """Every synonym/bigram target is a full path in the (real-slug) fixture tree."""
    import json

    body = json.loads((FIXTURES / "brand_taxonomy.json").read_text(encoding="utf-8"))
    paths = {t["id"].removeprefix(GENRE_BRAND + ":") for t in body["results"]["tags"]}
    targets = {t for tbl in (SYNONYMS, BIGRAMS) for v in tbl.values() for t, _ in v}
    fixture_gaps = targets - paths  # real nodes this slice leaves out are allowed
    real_only = {
        "food_and_beverage:drinks:carbonated", "food_and_beverage:drinks:sport_drinks",
        "food_and_beverage:food:bakery", "wine_and_spirits:spirits:liqueur",
        "wine_and_spirits:beer:cider", "fashion:footwear:sandals", "health_and_beauty:hair_care",
        "health_and_beauty:oral_care", "electronics:headphones", "electronics:phones_and_tablets",
        "electronics:computers_and_laptops", "electronics:camera_and_video",
        "electronics:appliances", "entertainment:production_company",
        "entertainment:video_game_developer", "automotive:commercial", "automotive:motorcycle",
        "travel:cruise", "travel:car_rental", "sports_organization:league_tournament",
        "financial_services", "financial_services:credit_card", "mobile_app",
    }  # fmt: skip
    assert fixture_gaps <= real_only, fixture_gaps - real_only


@pytest.fixture
async def taxonomy() -> list[Any]:
    return await load_brand_taxonomy(FixtureClient(FIXTURES))


async def test_map_dog_toy_to_pet_food_as_nearest(taxonomy: list[Any]) -> None:
    m = map_goods_phrase("squeaky dog chew toy", taxonomy)
    assert [(x.node.path_label, x.fit) for x in m] == [("food_and_beverage/pet_food", "nearest")]
    assert m[0].node.tag_id == f"{GENRE_BRAND}:food_and_beverage:pet_food"
    assert "nearest category" in NEAREST_NOTE
    assert map_goods_phrase("toys", taxonomy)[0].node.path_label == "games"
    assert map_goods_phrase("toys", taxonomy)[0].fit == "partial"


async def test_map_bourbon_whiskey_exact(taxonomy: list[Any]) -> None:
    m = map_goods_phrase("bourbon whiskey", taxonomy)
    assert (m[0].node.name, m[0].fit) == ("Whiskey", "exact")
    assert (m[1].node.name, m[1].fit) == ("Bourbon", "partial")
    assert map_goods_phrase("Tennessee whisky", taxonomy)[0].fit == "exact"


@pytest.mark.parametrize(
    ("phrase", "path", "fit"),
    [
        ("luxury handbags", "fashion/accessories/bags_and_leather", "exact"),
        ("audio systems, radios, speakers", "electronics/home_theater", "exact"),
        ("bottled artesian water", "food_and_beverage/drinks/non_carbonated", "exact"),
        ("bottled mineral water from Fiji", "food_and_beverage/drinks/non_carbonated", "exact"),
        ("children's books", "entertainment/publisher", "exact"),
        ("diamond engagement rings", "fashion/accessories/jewelry", "exact"),
        ("educational test-preparation materials", "academic", "exact"),
        ("illustrated book", "entertainment/publisher", "exact"),
        ("keyword search advertising", "software", "partial"),
        ("luxury resale", "retail/fashion", "exact"),
        ("military-style wristwatches", "fashion/accessories/watch", "exact"),
        ("online marketplace", "website", "exact"),
        ("search advertising", "software", "partial"),
        ("athletic sneakers", "fashion/footwear/sneakers", "exact"),
        ("fashion apparel", "fashion", "exact"),  # not entertainment/media/fashion
    ],
)
async def test_map_backtest_phrases(taxonomy: list[Any], phrase: str, path: str, fit: str) -> None:
    top = map_goods_phrase(phrase, taxonomy)[0]
    assert (top.node.path_label, top.fit) == (path, fit)


async def test_map_no_match(taxonomy: list[Any]) -> None:
    assert map_goods_phrase("NFT digital collectibles", taxonomy) == []
    assert map_goods_phrase("golf putters and equipment", taxonomy) == []
    assert map_goods_phrase("", taxonomy) == []
    assert map_goods_phrase("whiskey", []) == []
    assert len(map_goods_phrase("wine beer spirits whiskey bourbon", taxonomy)) == 3


# --------------------------------------------------------------------------------------
# FIX D: compare shape
# --------------------------------------------------------------------------------------

_SEED_A = [{"entity_id": "A1", "name": "Brand A", "subtype": "urn:entity:brand"}]
_SEED_B = [{"entity_id": "B1", "name": "Brand B", "subtype": "urn:entity:brand"}]


def _own(tid: str, count: str) -> dict[str, Any]:
    return {"tag_id": tid, "name": tid, "type": "urn:tag", "subtype": "urn:tag:keyword:qloo",
            "entity_id": "X", "popularity": 0.5, "query": {"count": count}}  # fmt: skip


def test_parse_compare_live_shape() -> None:
    raw = {
        "duration": 3,
        "results": {
            "tags": [
                {
                    "tag_id": "urn:tag:adjective:qloo:bold",
                    "name": "Bold",
                    "type": "urn:tag",
                    "subtype": "urn:tag:adjective:qloo",
                    "entity_id": "T1",
                    "popularity": 0.4,
                    "query": {
                        "score": 0.71,
                        "a.signal.interests.entities": _SEED_A,
                        "b.signal.interests.entities": _SEED_B,
                    },
                }
            ],
            "a": [_own("t1", "12"), _own("t2", "7")],
            "b": [_own("t3", "5")],
            "matchEntities": [],
        },
    }
    cmp = parse_compare(raw)
    assert not cmp.insufficient_data
    assert [(t.name, t.score, t.tag_type) for t in cmp.tags] == [
        ("Bold", 0.71, "urn:tag:adjective:qloo")
    ]
    assert [t.count for t in cmp.a_tags] == [12, 7] and cmp.b_tags[0].count == 5
    assert cmp.entities == [] and cmp.match_entities == []


def test_parse_compare_thin_brand_is_insufficient_data() -> None:
    cmp = parse_compare({"results": {"tags": [], "a": [_own("t1", "3")], "b": [],
                                     "matchEntities": []}})  # fmt: skip
    assert cmp.insufficient_data and cmp.tags == [] and len(cmp.a_tags) == 1
    assert parse_compare({}).insufficient_data
