"""Agent pipeline tests: scripted fake model + FixtureClient, no network, no real LLM.

Unit-level fixtures are written per test into tmp_path (deterministic, independent of the
shared backend/fixtures/qloo set); one smoke test runs against the shared set if present.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tearose.agent.graph import GraphEngine
from tearose.agent.llm import ScriptedChatModel, ai_tools, ainvoke_structured, tool_call
from tearose.agent.nodes import extract, fetch, interpret, resolve, route
from tearose.agent.nodes.base import RunContext
from tearose.agent.nodes.memo import FIXED_LIMITATIONS, brand_name, party_names
from tearose.agent.runs import RunHandle
from tearose.agent.tools import ToolContext, make_tools
from tearose.config import BACKEND_DIR
from tearose.qloo.fixtures import FixtureClient
from tearose.schemas import (
    AnalysisResult,
    Evidence,
    Extraction,
    ProxyResolution,
    Resolution,
    ResolvedBrand,
    RoutingDecision,
    TraceEvent,
    Universe,
)
from tearose.scoring import synthesize_bottom_line
from tearose.scoring.describe import describe_evidence
from tearose.scoring.score import overlap_evidence

# --------------------------------------------------------------------------------------
# Minimal synthetic Qloo world
# --------------------------------------------------------------------------------------

JD, JDH, BB, KG, PU = "E-JD", "E-JDH", "E-BB", "E-KG", "E-PU"
DOG = "urn:tag:genre:brand:pet_supplies:dog_toys"
PETS = "urn:tag:genre:brand:pet_supplies"
PETFOOD = "urn:tag:genre:brand:pet_supplies:pet_food"
WHISKEY = "urn:tag:genre:brand:wine_and_spirits:whiskey"
SPIRITS = "urn:tag:genre:brand:wine_and_spirits"
JUNIOR_GOODS = "durable rubber squeaky novelty dog toys"

TEXT = (
    "VIP Products LLC v. Jack Daniel's Properties, Inc. Jack Daniel's Properties, Inc. owns the "
    "JACK DANIEL'S trademarks and trade dress used on Tennessee whiskey since 1866. VIP Products "
    'LLC markets durable rubber squeaky novelty dog toys under the name "Bad Spaniels", in a '
    "bottle shape imitating the Jack Daniel's label, sold through pet stores and online. "
    "Count I alleges trademark infringement; Count II alleges dilution by tarnishment."
)

EXTRACTION: dict[str, Any] = {
    "document_type": "complaint",
    "title": "VIP Products LLC v. Jack Daniel's Properties, Inc.",
    "senior": {
        "side": "senior",
        "name": "Jack Daniel's Properties, Inc.",
        "marks": ["Jack Daniel's"],
        "goods": ["Tennessee whiskey"],
    },
    "junior": {
        "side": "junior",
        "name": "VIP Products LLC",
        "marks": ["Bad Spaniels"],
        "goods": [JUNIOR_GOODS],
        "channels": ["pet stores", "online"],
    },
    "claims": ["likelihood_of_confusion", "dilution"],
    "summary": "A whiskey brand owner alleges a dog-toy maker infringes and dilutes its marks.",
    "key_quotes": ["Count II alleges dilution by tarnishment"],
}


def _ent(eid: str, name: str, tags: list[str]) -> dict[str, Any]:
    return {
        "entity_id": eid,
        "name": name,
        "types": ["urn:entity:brand"],
        "popularity": 0.9,
        "tags": [{"tag_id": t, "name": t.rsplit(":", 1)[-1]} for t in tags],
    }


def write_fixtures(d: Path, *, peers: int = 60) -> Path:
    def w(name: str, body: dict[str, Any]) -> None:
        (d / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")

    w("empty_results", {"success": True, "results": {"entities": []}})
    w(
        "search_brand_jack_daniels",
        {
            "results": [
                {**_ent(JD, "Jack Daniel's", [WHISKEY]), "popularity": 0.99},
                _ent(JDH, "Jack Daniel's Tennessee Honey", [WHISKEY]),
            ]
        },
    )
    w("search_brand_barkbox", {"results": [_ent(BB, "BarkBox", [DOG, PETS])]})
    w("search_brand_kong", {"results": [_ent(KG, "KONG", [DOG])]})
    w("search_brand_purina", {"results": [_ent(PU, "Purina", [PETFOOD])]})
    tag = lambda i, n, t="urn:tag:genre:brand": {"id": i, "name": n, "type": t}  # noqa: E731
    w(
        "tags_search_dog_toys",
        {"results": {"tags": [tag(DOG, "Dog Toys"), tag("urn:tag:category:place:pet_store",
                                                        "Pet Store", "urn:tag:category:place")]}},
    )  # fmt: skip
    w("tags_search_pet_supplies", {"results": {"tags": [tag(PETS, "Pet Supplies"),
                                                        tag(DOG, "Dog Toys")]}})  # fmt: skip
    w("tags_search_tennessee_whiskey", {"results": {"tags": [tag(WHISKEY, "Whiskey")]}})
    # Senior seed in the pet universe: BarkBox at rank 55, KONG at 57 (page 2 of 50).
    ents = [_ent(f"E-F{i:02d}", f"Pet brand {i}", [DOG]) for i in range(peers)]
    if peers >= 57:
        ents[54] = _ent(BB, "BarkBox", [DOG])
        ents[56] = _ent(KG, "KONG", [DOG])
    for i, e in enumerate(ents):
        e["query"] = {"affinity": round(0.99 - i * 0.01, 3)}
    w("insights_brand_seed_jack_daniels_filter_pet_tags", {"results": {"entities": ents}})
    w(
        "insights_tag_seed_jack_daniels",
        {
            "results": {
                "tags": [
                    {"tag_id": f"urn:tag:keyword:t{i}", "name": f"Taste {i}"} for i in range(3)
                ]
                + [{"tag_id": DOG, "name": "Dog Toys"}]
                + [{"tag_id": f"urn:tag:keyword:u{i}", "name": f"Taste u{i}"} for i in range(16)]
            }
        },
    )
    demo = {
        "age": {
            "24_and_younger": 0.1,
            "25_to_29": 0.3,
            "30_to_34": 0.2,
            "35_to_44": 0.1,
            "45_to_54": -0.1,
            "55_and_older": -0.2,
        },
        "gender": {"male": 0.3, "female": -0.1},
    }
    w("insights_demographics_jack_daniels", {"results": {"demographics": [{"query": demo}]}})
    w("insights_demographics_barkbox_and_kong", {"results": {"demographics": [{"query": demo}]}})
    pts = [
        {"location": {"latitude": 36.0 + i, "longitude": -86.0 - i}, "query": {"affinity": a}}
        for i, a in enumerate([0.9, 0.5, 0.3, 0.2, 0.1])
    ]
    w("insights_heatmap_jack_daniels", {"results": {"heatmap": pts}})
    w(
        "compare_jack_daniels_vs_barkbox_and_kong",
        {"results": {"tags": [{"tag_id": "urn:tag:keyword:humor", "name": "Humorous",
                               "query": {"score": 0.4}}]}},
    )  # fmt: skip
    return d


@pytest.fixture
def client(tmp_path: Path) -> FixtureClient:
    return FixtureClient(write_fixtures(tmp_path))


def make_ctx(client: Any, model: ScriptedChatModel) -> tuple[RunContext, list[TraceEvent]]:
    events: list[TraceEvent] = []

    async def emit(e: TraceEvent) -> None:
        events.append(e)

    ctx = RunContext(
        client=client,
        model_factory=lambda strong=False: model,
        emit=emit,
        tools=ToolContext(client, emit),
    )
    return ctx, events


def proxied_resolution() -> Resolution:
    return Resolution(
        senior=ResolvedBrand(
            side="senior", query="Jack Daniel's", entity_id=JD, entity_name="Jack Daniel's",
            popularity=0.99,
        ),
        junior=ResolvedBrand(side="junior", query="Bad Spaniels"),
        junior_proxy=ProxyResolution(
            side="junior", goods_phrase=JUNIOR_GOODS, tag_options=[{"id": DOG}],
            chosen_tag_ids=[DOG], comparator_brand_ids=[BB, KG],
            comparator_brand_names=["BarkBox", "KONG"], rationale="test",
        ),
        universes=[
            Universe(side="senior", description="whiskey brands", tag_ids=[WHISKEY], size=150),
            Universe(side="junior", description="dog-toy brands", tag_ids=[DOG], size=150),
        ],
    )  # fmt: skip


RESOLVE_DECISION: dict[str, Any] = {
    "senior": {
        "query": "Jack Daniel's",
        "entity_id": JD,
        "candidates_considered": ["Jack Daniel's", "Jack Daniel's Tennessee Honey"],
        "disambiguation_note": "Parent whiskey brand, not the line extension.",
        "universe_tag_ids": [WHISKEY],
        "universe_description": "whiskey brands",
        "rationale": "Exact match for the whiskey brand.",
    },
    "junior": {
        "query": "Bad Spaniels",
        "entity_id": None,
        "proxy_goods_phrase": JUNIOR_GOODS,
        "proxy_chosen_tag_ids": [DOG],
        "comparator_entity_ids": [BB, KG, PU],
        "universe_description": "dog-toy brands",
        "rationale": "Bad Spaniels is not in Qloo; dog-toy brands stand in.",
    },
}

RESOLVE_LOOP: list[Any] = [
    ai_tools(tool_call("qloo_search", query="Jack Daniel's"),
             tool_call("qloo_search", query="Bad Spaniels")),
    ai_tools(tool_call("qloo_search", query="VIP Products LLC")),
    ai_tools(tool_call("qloo_tags_search", query=JUNIOR_GOODS)),
    ai_tools(tool_call("qloo_tags_search", query="dog toys")),
    ai_tools(tool_call("qloo_search", query="BarkBox"), tool_call("qloo_search", query="KONG"),
             tool_call("qloo_search", query="Purina")),
    ai_tools(tool_call("qloo_tags_search", query="Tennessee whiskey")),
    "Resolution complete.",
]  # fmt: skip

INTERPRETATION: dict[str, Any] = {
    "findings": [
        {
            "factor": "relatedness_of_goods",
            "lean": "favors_junior",
            "confidence": "medium",
            "finding": "Jack Daniel's fans rank the dog-toy comparators low among pet brands.",
            "evidence_refs": ["overlap.symmetric_percentile"],
        },
        {
            "factor": "fame",
            "lean": "favors_senior",
            "confidence": "high",
            "finding": "The senior brand's audience is broad across age groups.",
            "evidence_refs": ["fame.breadth_score"],
        },
    ],
    "limitations": ["The junior brand is represented by two comparator brands."],
}

MEMO_DRAFT: dict[str, Any] = {
    "headline": "Jack Daniel's fans show little affinity for dog-toy brands. A second sentence.",
    "sections": [{"id": "summary", "title": "Summary", "markdown": "Short summary."}],
}


# --------------------------------------------------------------------------------------
# llm helpers
# --------------------------------------------------------------------------------------


class _NoStructured(ScriptedChatModel):
    def with_structured_output(self, schema: Any, **kwargs: Any):  # type: ignore[override]
        raise NotImplementedError


async def test_structured_output_falls_back_to_json_mode() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    model = _NoStructured(scripts={"extract": ["```json\n" + json.dumps(EXTRACTION) + "\n```"]})
    out = await ainvoke_structured(
        model, Extraction, [SystemMessage("# extract\nx"), HumanMessage("doc")]
    )
    assert out.junior.marks == ["Bad Spaniels"]
    assert "JSON schema" in model.prompts_for("extract")[0]


# --------------------------------------------------------------------------------------
# (1) extract
# --------------------------------------------------------------------------------------


async def test_extract_maps_bad_spaniels_paragraph(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={"Extraction": [json.dumps(EXTRACTION)]})
    ctx, events = make_ctx(client, model)
    out = await extract.run({"input_text": TEXT}, ctx)
    ex: Extraction = out["extraction"]
    assert ex.senior.name == "Jack Daniel's Properties, Inc."
    assert ex.junior.marks == ["Bad Spaniels"]
    assert ex.junior.goods == [JUNIOR_GOODS]
    assert set(ex.claims) == {"likelihood_of_confusion", "dilution"}
    assert TEXT in model.prompts_for("Extraction")[0]
    assert any(e.type == "decision" and "Bad Spaniels" in (e.detail or "") for e in events)
    assert not [e for e in events if e.type == "warning"]  # goods are verbatim


async def test_extract_warns_on_paraphrased_goods(client: FixtureClient) -> None:
    bad = json.loads(json.dumps(EXTRACTION))
    bad["junior"]["goods"] = ["canine playthings"]
    ctx, events = make_ctx(client, ScriptedChatModel(scripts={"Extraction": [bad]}))
    await extract.run({"input_text": TEXT}, ctx)
    assert any(e.type == "warning" and "verbatim" in e.title for e in events)


# --------------------------------------------------------------------------------------
# (2) route guardrails
# --------------------------------------------------------------------------------------


def test_guardrails_add_required_analyses() -> None:
    ex = Extraction.model_validate({**EXTRACTION, "claims": ["dilution", "common_law_priority"]})
    final, added = route.apply_guardrails(RoutingDecision(analyses=[], rationale={}), ex)
    assert final.analyses == ["overlap", "fame", "zone"]
    assert {a for a, _ in added} == {"overlap", "fame", "zone"}
    assert set(final.rationale) == {"overlap", "bridging", "fame", "zone"}


async def test_route_adds_fame_when_dilution_pleaded(client: FixtureClient) -> None:
    model = ScriptedChatModel(
        scripts={"RoutingDecision": [{"analyses": ["overlap"], "rationale": {"overlap": "x"}}]}
    )
    ctx, events = make_ctx(client, model)
    out = await route.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx)
    routing: RoutingDecision = out["routing"]
    assert "fame" in routing.analyses and "bridging" in routing.analyses
    assert routing.rationale["fame"].startswith("Added by guardrail")
    assert any(e.title == "Guardrail added 'fame'" for e in events)


# --------------------------------------------------------------------------------------
# (3) resolve: proxy path
# --------------------------------------------------------------------------------------


async def test_resolve_takes_proxy_path_and_records_tag_options(client: FixtureClient) -> None:
    model = ScriptedChatModel(
        scripts={"resolve": list(RESOLVE_LOOP), "ResolveDecision": [RESOLVE_DECISION]}
    )
    ctx, events = make_ctx(client, model)
    out = await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx)
    res: Resolution = out["resolution"]

    assert res.senior.entity_id == JD
    assert "Jack Daniel's Tennessee Honey" in res.senior.candidates_considered
    assert res.junior.entity_id is None
    proxy = res.junior_proxy
    assert proxy is not None
    assert proxy.goods_phrase == JUNIOR_GOODS
    assert {o["id"] for o in proxy.tag_options} == {DOG, "urn:tag:category:place:pet_store"}
    assert proxy.chosen_tag_ids == [DOG]
    assert proxy.comparator_brand_ids == [BB, KG]  # Purina shares no chosen tag → dropped
    assert "Purina" in proxy.rationale
    assert {u.side: u.tag_ids for u in res.universes} == {"senior": [WHISKEY], "junior": [DOG]}
    # the verbatim phrase was queried first, the shortened one second
    queries = [q for q, _ in ctx.tools.tag_searches]
    assert queries.index(JUNIOR_GOODS) < queries.index("dog toys")
    assert any(e.type == "warning" and "Purina" in e.title for e in events)
    assert any(e.type == "tool_call" for e in events)


async def test_resolve_code_enforces_verbatim_goods_lookup(client: FixtureClient) -> None:
    """The model skips the tag lookup entirely; code runs the verbatim then the short phrase."""
    loop = [
        ai_tools(tool_call("qloo_search", query="Jack Daniel's"),
                 tool_call("qloo_search", query="Bad Spaniels"),
                 tool_call("qloo_search", query="BarkBox")),
    ]  # fmt: skip
    decision = json.loads(json.dumps(RESOLVE_DECISION))
    decision["junior"]["proxy_chosen_tag_ids"] = ["urn:tag:made:up"]
    decision["junior"]["comparator_entity_ids"] = [BB]
    model = ScriptedChatModel(scripts={"resolve": loop, "ResolveDecision": [decision]})
    ctx, events = make_ctx(client, model)
    out = await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx)
    proxy = out["resolution"].junior_proxy
    assert [q for q, _ in ctx.tools.tag_searches][:2] == [JUNIOR_GOODS, "dog toys"]
    assert proxy.chosen_tag_ids == [DOG]  # made-up tag rejected; heuristic pick from the menu
    assert any("not on the returned menu" in e.title for e in events)


TAX_PET_FOOD = "urn:tag:genre:brand:food_and_beverage:pet_food"


def _with_taxonomy(d: Path) -> FixtureClient:
    shared = BACKEND_DIR / "fixtures" / "qloo" / "brand_taxonomy.json"
    (d / "brand_taxonomy.json").write_text(shared.read_text(encoding="utf-8"), encoding="utf-8")
    body = {"results": [_ent("E-CH", "Chewy Treats", [TAX_PET_FOOD])]}
    (d / "search_brand_chewy_treats.json").write_text(json.dumps(body), encoding="utf-8")
    return FixtureClient(d)


async def test_resolve_proxy_uses_brand_taxonomy_with_fit(tmp_path: Path) -> None:
    client = _with_taxonomy(write_fixtures(tmp_path))
    loop = [
        ai_tools(tool_call("qloo_search", query="Jack Daniel's"),
                 tool_call("qloo_search", query="Bad Spaniels"),
                 tool_call("qloo_search", query="Chewy Treats")),
        "done",
    ]  # fmt: skip
    decision = json.loads(json.dumps(RESOLVE_DECISION))
    decision["junior"].update(
        proxy_chosen_tag_ids=[],
        proxy_taxonomy_choices=[
            {"tag_id": TAX_PET_FOOD, "fit": "nearest"},
            {"tag_id": "urn:tag:genre:brand:toys", "fit": "exact"},  # not in the taxonomy
        ],
        comparator_entity_ids=["E-CH", BB],
    )
    model = ScriptedChatModel(scripts={"resolve": loop, "ResolveDecision": [decision]})
    ctx, events = make_ctx(client, model)
    out = await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx)
    proxy = out["resolution"].junior_proxy
    assert proxy.chosen_tag_ids == [TAX_PET_FOOD]
    assert proxy.fit == "nearest" and "no exact match" in (proxy.fit_note or "")
    assert proxy.comparator_brand_ids == ["E-CH"]  # BarkBox carries no pet_food tag
    assert ctx.tools.tag_searches == []  # no free-text /v2/tags needed
    prompt = model.prompts_for("resolve")[0]
    assert "BRAND TAXONOMY (67 nodes" in prompt
    assert "food_and_beverage/pet_food = Pet Food" in prompt
    # a company broader than the goods (retailer, parent) is a match, not a reject
    assert "retailer, marketplace, platform, media company or parent company" in prompt
    assert "never a reason to reject" in prompt and "namesake restaurant" in prompt
    assert any("not in Qloo's brand taxonomy" in e.title for e in events)
    assert {u.side: u.tag_ids for u in out["resolution"].universes}["junior"] == [TAX_PET_FOOD]
    # the memo states the approximation in code
    from tearose.agent.nodes.memo import proxy_limitations

    lims = proxy_limitations({"resolution": out["resolution"]})
    assert lims and "nearest category, no exact match" in lims[0] and "Pet Food" in lims[0]


async def test_resolve_universe_is_the_brands_own_category(client: FixtureClient) -> None:
    decision = json.loads(json.dumps(RESOLVE_DECISION))
    decision["senior"]["universe_tag_ids"] = [SPIRITS]  # the model asks for a broader set
    decision["senior"]["universe_description"] = "all spirits"
    model = ScriptedChatModel(
        scripts={"resolve": list(RESOLVE_LOOP), "ResolveDecision": [decision]}
    )
    ctx, events = make_ctx(client, model)
    res = (await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx))[
        "resolution"
    ]
    senior = next(u for u in res.universes if u.side == "senior")
    assert senior.tag_ids == [WHISKEY] and senior.description == "whiskey brands"
    assert any(e.type == "decision" and e.data.get("source") == "entity own tags" for e in events)
    assert any("model's universe choice is not used" in e.title for e in events)


async def test_resolve_universe_falls_back_to_insights_tags(tmp_path: Path) -> None:
    write_fixtures(tmp_path)
    body = {"results": [{**_ent(JD, "Jack Daniel's", []), "popularity": 0.99}]}  # no own tags
    (tmp_path / "search_brand_jack_daniels.json").write_text(json.dumps(body), encoding="utf-8")
    model = ScriptedChatModel(
        scripts={"resolve": list(RESOLVE_LOOP), "ResolveDecision": [RESOLVE_DECISION]}
    )
    ctx, events = make_ctx(FixtureClient(tmp_path), model)
    res = (await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx))[
        "resolution"
    ]
    senior = next(u for u in res.universes if u.side == "senior")
    assert senior.tag_ids == [DOG]  # the only brand-genre tag among the insights tags
    assert any(
        e.type == "decision" and e.data.get("source") == "insights tags (fallback)" for e in events
    )
    assert (JD,) in ctx.tools.seed_tags  # fetched once, reusable for bridging


async def test_resolve_without_model_decision_is_a_miss_not_first_hit(
    client: FixtureClient,
) -> None:
    loop = [ai_tools(tool_call("qloo_search", query="Jack Daniel's")), "done"]
    model = ScriptedChatModel(scripts={"resolve": loop, "ResolveDecision": []})  # decision fails
    ctx, events = make_ctx(client, model)
    out = await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx)
    res = out["resolution"]
    assert res.senior.entity_id is None and res.senior_proxy is not None
    assert not any("first search hit" in e.title for e in events)


async def test_resolve_flags_low_name_similarity_and_guards_same_entity(
    client: FixtureClient,
) -> None:
    decision = json.loads(json.dumps(RESOLVE_DECISION))
    decision["senior"]["entity_id"] = BB  # the model picks a dissimilar name: kept, flagged
    decision["junior"].update(entity_id=BB, query="BarkBox")  # same entity on both sides
    loop = [ai_tools(tool_call("qloo_search", query="Jack Daniel's"),
                     tool_call("qloo_search", query="BarkBox")), "done"]  # fmt: skip
    model = ScriptedChatModel(scripts={"resolve": loop, "ResolveDecision": [decision]})
    ctx, events = make_ctx(client, model)
    res = (await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx))[
        "resolution"
    ]
    assert res.senior.entity_id == BB
    assert "Name check" in (res.senior.disambiguation_note or "")
    assert any(e.type == "warning" and "low name similarity" in e.title for e in events)
    assert res.junior.entity_id is None and res.junior_proxy is not None
    assert any("other side's entity" in e.title for e in events)


async def test_search_summary_shows_categories(client: FixtureClient) -> None:
    ctx, _ = make_ctx(client, ScriptedChatModel())
    tools = {t.name: t for t in make_tools(ctx.tools)}
    out = json.loads(await tools["qloo_search"].ainvoke({"query": "BarkBox"}))
    first = out["results"][0]
    assert {"id", "name", "popularity", "tags", "categories"} <= set(first)
    assert "dog toys" in first["categories"]


# --------------------------------------------------------------------------------------
# (4) fetch: paging, feedback, code fallback, give-up
# --------------------------------------------------------------------------------------


async def test_fetch_pages_until_target_found(client: FixtureClient) -> None:
    page = lambda p: ai_tools(  # noqa: E731
        tool_call("qloo_insights_entities", seed_entity_ids=[JD], filter_tags=[DOG], page=p)
    )
    model = ScriptedChatModel(scripts={"fetch": [page(1), "done", page(2), "done"]})
    ctx, events = make_ctx(client, model)
    state = {
        "resolution": proxied_resolution(),
        "routing": RoutingDecision(analyses=["overlap"], rationale={}),
    }
    out = await fetch.run(state, ctx)
    raw = out["raw"]
    peers = raw.senior_seed_junior_universe
    assert peers.pages_fetched == 2
    assert len(peers.entities) == 60
    assert {e.entity_id: e.rank for e in peers.entities}[BB] == 55
    assert raw.junior_target_entity_ids == [BB, KG]

    calls = [
        e for e in events if e.type == "tool_call" and e.data["tool"] == "qloo_insights_entities"
    ]
    assert [c.data["params"]["page"] for c in calls[:2]] == [1, 2]
    assert any(e.type == "tool_result" for e in events)
    assert any(e.type == "note" and "Completeness check 1" in e.title for e in events)
    # the model never fetched the reverse direction or compare: code did
    assert any(e.type == "decision" and e.title.startswith("Code fallback") for e in events)
    assert raw.compare is not None
    # junior→senior (comparators seeded, whiskey universe) has no fixture: single tag ⇒ give up
    assert any(n.startswith("Gave up") for n in raw.notes)
    assert raw.junior_seed_senior_universe.entities == []
    # the second page of the model's call reported the targets
    tool_msgs = [m for m in model.calls[-1][1] if m.type == "tool"]
    assert '"targets_found":[{"id":"E-BB"' in tool_msgs[1].content

    # harness v2: one direct affinity lookup per target, planned up front, run by code after
    # the paging (the model has no tool for it and never sees it in its checklist)
    plan = next(e for e in events if e.type == "decision" and e.title.startswith("Data plan"))
    assert sum("direct affinity" in c for c in plan.data["checklist"]) == 2
    assert "qloo_target_affinity" not in model.prompts_for("fetch")[0]
    assert peers.target_affinities == {BB: pytest.approx(0.45), KG: pytest.approx(0.43)}
    lookups = [
        e for e in events if e.type == "tool_call" and e.data["tool"] == "qloo_target_affinity"
    ]
    assert [c.data["params"]["filter_tags"] for c in lookups[:2]] == [[DOG], [DOG]]
    ov = overlap_evidence(raw)
    assert ov.senior_to_junior_rank == 56 and ov.senior_to_junior_censored is False
    assert ov.senior_to_junior_affinity_ratio == pytest.approx(0.44 / 0.99)
    # junior→senior gave up (no brands): no lookup, no ratio
    assert raw.junior_seed_senior_universe.target_affinities == {}


async def test_retry_with_broadest_tag(tmp_path: Path) -> None:
    write_fixtures(tmp_path)
    wide = "insights_brand_seed_jack_daniels_filter_urn_tag_genre_brand_wine_and_spirits.json"
    body = {"results": {"entities": [_ent("E-X", "Jim Beam", [SPIRITS])]}}
    (tmp_path / wide).write_text(json.dumps(body), encoding="utf-8")
    events: list[TraceEvent] = []

    async def emit(e: TraceEvent) -> None:
        events.append(e)

    tc = ToolContext(FixtureClient(tmp_path), emit)
    ents, _ = await tc.insights_entities([JD], [WHISKEY, SPIRITS])
    assert [e.name for e in ents] == ["Jim Beam"]
    assert tc.resolve_filter([JD], [WHISKEY, SPIRITS]) == ((JD,), (SPIRITS,))
    assert any("widened" in n for n in tc.notes)
    assert any(e.type == "warning" and "broadest" in e.title for e in events)
    assert len(tc.queries) == 2


async def test_tool_summary_is_compact_but_context_keeps_everything(
    client: FixtureClient,
) -> None:
    ctx, events = make_ctx(client, ScriptedChatModel())
    tools = {t.name: t for t in make_tools(ctx.tools)}
    out = json.loads(
        await tools["qloo_insights_entities"].ainvoke(
            {"seed_entity_ids": [JD], "filter_tags": [DOG], "page": 1}
        )
    )
    assert out["count"] == 50 and len(out["top"]) == 10 and out["ref"] == "Q1"
    assert len(ctx.tools.pages[((JD,), (DOG,))][1]) == 50
    assert [e.type for e in events] == ["tool_call", "tool_result"]
    assert events[1].data["query"]["endpoint"] == "/v2/insights"


# --------------------------------------------------------------------------------------
# (5) full run through GraphEngine + follow-up
# --------------------------------------------------------------------------------------


def full_script() -> ScriptedChatModel:
    return ScriptedChatModel(
        scripts={
            "Extraction": [EXTRACTION],
            "RoutingDecision": [{"analyses": ["overlap"], "rationale": {"overlap": "confusion"}}],
            "resolve": [
                *RESOLVE_LOOP,
                # follow-up round: the comparators must be searched again in the new context
                ai_tools(
                    tool_call("qloo_search", query="BarkBox"),
                    tool_call("qloo_search", query="KONG"),
                    tool_call("qloo_tags_search", query="pet supplies"),
                ),
                "done",
            ],  # fmt: skip
            "ResolveDecision": [
                RESOLVE_DECISION,
                {
                    "senior": RESOLVE_DECISION["senior"],
                    "junior": {
                        **RESOLVE_DECISION["junior"],
                        "proxy_goods_phrase": "pet supplies",
                        "proxy_chosen_tag_ids": [PETS],
                        "comparator_entity_ids": [BB, KG],
                    },
                },
            ],
            "Interpretation": [INTERPRETATION, INTERPRETATION],
            "MemoDraft": [MEMO_DRAFT, MEMO_DRAFT],
            "FollowupPlan": [
                {
                    "action": "re_resolve_junior_goods",
                    "instruction": "Treat the junior's goods as pet supplies.",
                    "junior_goods_phrase": "pet supplies",
                }
            ],
        }
    )


def new_handle() -> RunHandle:
    return RunHandle(
        AnalysisResult(run_id="r1", status="queued", mode="fixture", input_excerpt=TEXT[:600])
    )


async def test_full_run_streams_events_and_finishes(client: FixtureClient) -> None:
    model = full_script()
    engine = GraphEngine(client=client, model_factory=lambda strong=False: model)
    handle = new_handle()
    status_at_event: list[str] = []

    async def consume() -> None:
        async for _ in handle.events():
            status_at_event.append(handle.result.status)

    consumer = asyncio.create_task(consume())
    await engine.run(handle, TEXT)
    await asyncio.wait_for(consumer, 5)

    r = handle.result
    assert r.status == "finished", r.error
    assert len(r.trace) >= 10
    assert "running" in status_at_event  # events arrived while the run was in progress
    assert r.trace[0].type == "run_started" and r.trace[-1].type == "run_finished"
    assert [e.seq for e in r.trace] == list(range(1, len(r.trace) + 1))
    nodes_started = [e.node for e in r.trace if e.type == "node_started"]
    assert nodes_started == ["extract", "route", "resolve", "fetch", "score", "interpret", "memo"]

    assert r.extraction and r.routing and r.resolution
    assert set(r.routing.analyses) == {"overlap", "bridging", "fame"}
    assert r.evidence is not None and r.evidence.overlap is not None
    memo = r.memo
    assert memo is not None
    assert memo.headline == "Jack Daniel's fans show little affinity for dog-toy brands."
    # computed in code from the leans (relatedness favors junior, fame favors senior), not scripted
    assert memo.bottom_line == (
        "Taste data cuts against Jack Daniel's on the one confusion factor measured but "
        "supports Jack Daniel's on fame. It is silent on mark similarity, intent and actual "
        "confusion."
    )
    state = engine.state_of("r1")
    assert memo.bottom_line == synthesize_bottom_line(memo.findings, *party_names(state))
    assert memo.limitations[-5:] == list(FIXED_LIMITATIONS)
    assert memo.limitations[0] == INTERPRETATION["limitations"][0]
    assert [s.id for s in memo.sections] == ["summary", "factors", "method", "limitations"]
    assert len(memo.appendix_queries) >= 10
    assert memo.appendix_queries == engine.state_of("r1")["queries"]

    # both prompts carry the code-written fact sentences, and no float with > 2 decimals
    facts = describe_evidence(r.evidence, r.resolution)
    for schema in ("Interpretation", "MemoDraft"):
        prompt = model.prompts_for(schema)[0]
        assert "FACTS (computed in code; the only source for numbers)" in prompt
        for sentence in facts["overlap"] + facts["fame"]:
            assert sentence in prompt
        human = prompt[prompt.index("FACTS (computed in code") :]
        assert not re.search(r"\d\.\d{3,}", human), schema


async def test_followup_reruns_from_resolve_and_accumulates_queries(
    client: FixtureClient,
) -> None:
    model = full_script()
    engine = GraphEngine(client=client, model_factory=lambda strong=False: model)
    handle = new_handle()
    await engine.run(handle, TEXT)
    first_queries = len(handle.result.memo.appendix_queries)

    await engine.followup(handle, "What if the junior's goods are pet supplies generally?")
    r = handle.result
    assert r.status == "finished", r.error
    assert r.resolution.junior_proxy.goods_phrase == "pet supplies"
    assert r.resolution.junior_proxy.chosen_tag_ids == [PETS]
    assert len(r.memo.appendix_queries) > first_queries
    followup_nodes = [e.node for e in r.trace if e.type == "node_started"][7:]
    assert followup_nodes == ["followup", "resolve", "fetch", "score", "interpret", "memo"]
    assert "pet supplies" in model.prompts_for("ResolveDecision")[-1]


async def test_run_failure_sets_failed_status(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={})  # no Extraction scripted ⇒ extract fails
    engine = GraphEngine(client=client, model_factory=lambda strong=False: model)
    handle = new_handle()
    await engine.run(handle, TEXT)
    assert handle.result.status == "failed"
    assert handle.result.error and handle.result.error.startswith("extract:")
    assert handle.result.trace[-1].type == "run_failed"


@pytest.mark.skipif(
    not (BACKEND_DIR / "fixtures" / "qloo" / "search_brand_jack_daniels.json").exists(),
    reason="shared fixtures not present",
)
async def test_smoke_run_on_shared_fixtures() -> None:
    client = FixtureClient(BACKEND_DIR / "fixtures" / "qloo")
    ex = json.loads(json.dumps(EXTRACTION))
    ex["junior"]["goods"] = ["dog toys"]
    decision = json.loads(json.dumps(RESOLVE_DECISION))
    decision["junior"]["comparator_entity_ids"] = ["FA4E0000-0000-4000-A000-000000000004"]
    decision["junior"]["proxy_goods_phrase"] = "dog toys"
    decision["junior"]["proxy_chosen_tag_ids"] = [DOG]
    decision["senior"]["entity_id"] = "FA4E0000-0000-4000-A000-000000000001"
    decision["senior"]["universe_tag_ids"] = [SPIRITS]
    model = ScriptedChatModel(
        scripts={
            "Extraction": [ex],
            "RoutingDecision": [{"analyses": ["overlap"], "rationale": {}}],
            "resolve": [
                ai_tools(
                    tool_call("qloo_search", query="Jack Daniel's"),
                    tool_call("qloo_search", query="Bad Spaniels"),
                    tool_call("qloo_tags_search", query="dog toys"),
                    tool_call("qloo_search", query="BarkBox"),
                    tool_call("qloo_tags_search", query="whiskey"),
                ),
            ],  # fmt: skip
            "ResolveDecision": [decision],
            "Interpretation": [INTERPRETATION],
            "MemoDraft": [MEMO_DRAFT],
        }
    )
    engine = GraphEngine(client=client, model_factory=lambda strong=False: model)
    handle = new_handle()
    await engine.run(handle, TEXT)
    r = handle.result
    assert r.status == "finished", r.error
    assert r.resolution.junior_proxy.comparator_brand_names == ["BarkBox"]
    assert r.evidence is not None and r.memo is not None


# --------------------------------------------------------------------------------------
# (6) blind mode
# --------------------------------------------------------------------------------------


async def test_blind_mode_replaces_names_in_interpret_prompt(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={"Interpretation": [INTERPRETATION]})
    ctx, events = make_ctx(client, model)
    state = {
        "extraction": Extraction.model_validate(EXTRACTION),
        "routing": RoutingDecision(analyses=["overlap", "fame"], rationale={}),
        "resolution": proxied_resolution(),
        "evidence": Evidence(),
        "blind": True,
    }
    out = await interpret.run(state, ctx)
    prompt = model.prompts_for("Interpretation")[0]
    for name in ("Jack Daniel", "Bad Spaniels", "VIP Products", "JACK DANIEL"):
        assert name.lower() not in prompt.lower()
    assert "Brand A (senior)" in prompt and "Brand B (junior)" in prompt
    assert "BarkBox" in prompt  # comparators are not parties and stay named
    # no evidence at all ⇒ guardrail forces insufficient_data
    assert {f.lean for f in out["findings"]} == {"insufficient_data"}
    assert any(e.type == "warning" and "insufficient_data" in e.title for e in events)


async def test_not_blind_keeps_names(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={"Interpretation": [INTERPRETATION]})
    ctx, _ = make_ctx(client, model)
    state = {
        "extraction": Extraction.model_validate(EXTRACTION),
        "routing": RoutingDecision(analyses=["overlap"], rationale={}),
        "evidence": Evidence(),
        "blind": False,
    }
    await interpret.run(state, ctx)
    assert "Bad Spaniels" in model.prompts_for("Interpretation")[0]


def test_bottom_line_party_names() -> None:
    assert brand_name("Jack Daniel's Properties, Inc.") == "Jack Daniel's"
    assert brand_name("VIP Products LLC") == "VIP Products"
    assert brand_name("Acme Co.") == "Acme"
    assert brand_name("Inc.") == "Inc"  # never stripped to nothing
    ex = Extraction.model_validate(EXTRACTION)
    # resolved senior keeps its Qloo name; the proxied junior is named by its party, not the
    # category comparators (BarkBox, KONG)
    assert party_names({"extraction": ex, "resolution": proxied_resolution()}) == (
        "Jack Daniel's",
        "VIP Products",
    )
    # nothing resolved yet: both sides from the extraction
    assert party_names({"extraction": ex}) == ("Jack Daniel's", "VIP Products")
    # nothing known: role phrases in the bottom line
    assert party_names({}) == (None, None)
