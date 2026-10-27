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
from tearose.agent.nodes import assess, extract, fetch, interpret, memo, resolve, route
from tearose.agent.nodes.base import RunContext
from tearose.agent.nodes.interpret import display_name, display_names
from tearose.agent.nodes.memo import FIXED_LIMITATIONS, brand_name, party_names
from tearose.agent.runs import RunHandle
from tearose.agent.tools import ToolContext, make_tools
from tearose.config import BACKEND_DIR
from tearose.qloo.fixtures import FixtureClient
from tearose.schemas import (
    NOT_A_PREDICTION,
    READ_FACTORS,
    AnalysisResult,
    Evidence,
    Extraction,
    FactorFinding,
    Memo,
    PreliminaryRead,
    ProxyResolution,
    Resolution,
    ResolvedBrand,
    RoutingDecision,
    TraceEvent,
    Universe,
)
from tearose.scoring import synthesize_bottom_line, synthesize_read_line
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
                {**_ent(JD, "Jack Daniels", [WHISKEY]), "popularity": 0.99},
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


PRELIM_READ: dict[str, Any] = {
    "lean": "newcomer",
    "confidence": "medium",
    "turns_on": "The case most likely turns on the parody defence.",
    "rationale": (
        "The audience data shows weak relatedness and a broad senior audience. On the pleading, "
        "the bottle shape imitates the senior label and the dog-toy maker answers with parody."
    ),
    "flip_risks": [
        "A court that rejects the parody defence would weigh the imitated label heavily.",
        "A consumer survey showing source confusion would change the confusion factors.",
    ],
    "read_factors": [
        {"factor": "similarity_of_marks", "lean": "favors_senior", "confidence": "high",
         "basis": "document", "finding": 'The toy uses "a bottle shape imitating" the label.'},
        {"factor": "intent", "lean": "neutral", "confidence": "low", "basis": "document",
         "finding": "Not alleged."},
        {"factor": "actual_confusion", "lean": "insufficient_data", "confidence": "low",
         "basis": "document", "finding": "Not alleged."},
        {"factor": "buyer_care", "lean": "insufficient_data", "confidence": "low",
         "basis": "document", "finding": "Not alleged."},
        {"factor": "protectability", "lean": "favors_senior", "confidence": "medium",
         "basis": "document", "finding": "The trade dress is used \"since 1866\"."},
        {"factor": "mark_strength", "lean": "favors_senior", "confidence": "medium",
         "basis": "document", "finding": "A long-used whiskey mark; strength is not contested."},
        {"factor": "defences", "lean": "favors_junior", "confidence": "medium",
         "basis": "document", "finding": "Parody is pleaded."},
    ],
    "best_defence": "Parody: the toy comments on the whiskey label, as the answer pleads.",
    "one_sided_input": False,
    "data_factors_used": ["relatedness_of_goods", "fame"],
    "not_a_prediction": "model text that code replaces",
}  # fmt: skip


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


async def test_extract_marks_bundled_pleadings_in_code(client: FixtureClient) -> None:
    """A second document banner (the defendant's answer or motion) makes the input "pleadings"."""
    bundled = (
        "===== DOCUMENT 1: Complaint =====\n" + TEXT + "\n===== DOCUMENT 2: Answer =====\nDenied.\n"
    )
    model = ScriptedChatModel(scripts={"Extraction": [json.dumps(EXTRACTION)]})
    ctx, _ = make_ctx(client, model)
    out = await extract.run({"input_text": bundled}, ctx)
    assert out["extraction"].document_type == "pleadings"
    model = ScriptedChatModel(scripts={"Extraction": [json.dumps(EXTRACTION)]})
    ctx, _ = make_ctx(client, model)
    out = await extract.run({"input_text": TEXT}, ctx)
    assert out["extraction"].document_type == "complaint"


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


async def test_analyses_override_runs_all_and_records_context(client: FixtureClient) -> None:
    """Full coverage (showcase --all-analyses): zone is not pleaded but measured for context."""
    model = ScriptedChatModel(
        scripts={"RoutingDecision": [{"analyses": ["overlap"], "rationale": {"overlap": "x"}}]}
    )
    ctx, events = make_ctx(client, model)
    state = {
        "extraction": Extraction.model_validate(EXTRACTION),
        "analyses_override": ["overlap", "bridging", "fame", "zone"],
    }
    routing: RoutingDecision = (await route.run(state, ctx))["routing"]
    assert routing.analyses == ["overlap", "bridging", "fame", "zone"]
    assert routing.context_only == ["zone"]
    assert routing.rationale["zone"].startswith("Measured for context: not pleaded")
    assert routing.rationale["fame"].startswith("Added by guardrail")  # pleaded: unchanged
    full = next(e for e in events if e.title.startswith("Full coverage"))
    assert full.data["pleaded"] == ["overlap", "bridging", "fame"]
    # without the override nothing changes
    plain, extra = route.apply_override(routing.model_copy(update={"context_only": []}), None)
    assert extra == [] and plain.context_only == []


async def test_zone_runs_for_brand_vs_brand_and_interpret_marks_context(tmp_path: Path) -> None:
    """Zone with no geographic dispute: both heatmaps and the overlap of the maps; the
    interpret step says the unpleaded analysis is context, not a live factor."""
    from tearose.scoring import compute_evidence

    write_fixtures(tmp_path)
    pts = [
        {"location": {"latitude": 36.0 + i, "longitude": -86.0 - i}, "query": {"affinity": a}}
        for i, a in enumerate([0.2, 0.4, 0.6, 0.8, 0.9])
    ]
    (tmp_path / "insights_heatmap_barkbox.json").write_text(
        json.dumps({"results": {"heatmap": pts}}), encoding="utf-8"
    )
    client = FixtureClient(tmp_path)
    res = Resolution(
        senior=ResolvedBrand(side="senior", query="Jack Daniel's", entity_id=JD,
                             entity_name="Jack Daniel's"),
        junior=ResolvedBrand(side="junior", query="BarkBox", entity_id=BB, entity_name="BarkBox"),
    )  # fmt: skip
    routing = RoutingDecision(
        analyses=["zone"],
        rationale={"zone": "Measured for context: not pleaded."},
        context_only=["zone"],
    )
    model = ScriptedChatModel(
        scripts={
            "fetch": ["done"],
            "Interpretation": [
                {
                    "findings": [
                        {
                            "factor": "zone_of_reputation",
                            "lean": "neutral",
                            "confidence": "low",
                            "finding": "The two maps overlap broadly.",
                        }
                    ],
                    "limitations": [],
                }
            ],
        }
    )
    ctx, _ = make_ctx(client, model)
    raw = (await fetch.run({"resolution": res, "routing": routing}, ctx))["raw"]
    assert raw.senior_heatmap and raw.junior_heatmap
    ev = compute_evidence(raw, res, routing)
    assert ev.zone is not None and ev.zone.concentration_index is not None
    assert ev.zone.geographic_overlap is not None
    state = {
        "extraction": Extraction.model_validate(EXTRACTION),
        "routing": routing,
        "resolution": res,
        "evidence": ev,
        "raw": raw,
    }
    out = await interpret.run(state, ctx)
    finding = out["findings"][0].finding
    assert finding.startswith(interpret.CONTEXT_MARK)
    prompt = model.prompts_for("Interpretation")[0]
    assert '"context_only_analyses"' in prompt and "CONTEXT ONLY" in prompt


def test_showcase_all_analyses_flag_builds_override_engine() -> None:
    from tearose.eval import precompute_showcase as pc

    engine = pc.make_engine(True)
    assert isinstance(engine, GraphEngine)
    assert engine.analyses_override == ["overlap", "bridging", "fame", "zone"]
    assert pc.ALL_ANALYSES_FLAG == "--all-analyses"


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
    # no StandInDecision scripted: the agent's pick fails, code picks by popularity ("rule")
    assert proxy.comparator_brand_ids == ["E-F00", "E-F01", "E-F02"]
    assert proxy.comparator_source == "rule"
    assert len(proxy.stand_in_candidates) == 10 and proxy.measure_overlap
    assert any("stand-in choice failed" in e.title for e in events)
    assert {u.side: u.tag_ids for u in res.universes} == {"senior": [WHISKEY], "junior": [DOG]}
    # the verbatim phrase was queried first, the shortened one second
    queries = [q for q, _ in ctx.tools.tag_searches]
    assert queries.index(JUNIOR_GOODS) < queries.index("dog toys")
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
    # stand-ins come only from the code-built shortlist (no StandInDecision scripted: rule)
    assert "E-CH" not in proxy.comparator_brand_ids and BB not in proxy.comparator_brand_ids
    assert proxy.comparator_source == "rule"
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


def _rule_fixture_popularity(d: Path) -> None:
    """Two page-1 brands (ranks 11 and 4) become the most popular in the pet universe; BarkBox
    and KONG (page 2, beyond the rule's single page) would be even more popular."""
    p = d / "insights_brand_seed_jack_daniels_filter_pet_tags.json"
    body = json.loads(p.read_text(encoding="utf-8"))
    for e in body["results"]["entities"]:
        e["popularity"] = {"E-F10": 0.97, "E-F03": 0.96, BB: 0.99, KG: 0.99}.get(
            e["entity_id"], 0.5
        )
    p.write_text(json.dumps(body), encoding="utf-8")


def _stand_in(picks: list[str], **kw: Any) -> dict[str, Any]:
    return {"picks": picks, "comparator_rationale": "best-known dog-toy brands", **kw}


async def _resolve_with(
    tmp_path: Path, stand_in: dict[str, Any] | None
) -> tuple[Resolution, RunContext, list[TraceEvent], ScriptedChatModel]:
    _rule_fixture_popularity(write_fixtures(tmp_path))
    scripts: dict[str, list[Any]] = {
        "resolve": list(RESOLVE_LOOP),
        "ResolveDecision": [RESOLVE_DECISION],
        "fetch": ["done"],
    }
    if stand_in is not None:
        scripts["StandInDecision"] = [stand_in]
    model = ScriptedChatModel(scripts=scripts)
    ctx, events = make_ctx(FixtureClient(tmp_path), model)
    res = (await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx))[
        "resolution"
    ]
    return res, ctx, events, model


async def test_resolve_agent_picks_stand_ins_from_the_shortlist(tmp_path: Path) -> None:
    """Code builds the shortlist (JD-seeded brands in the proxy category, by popularity); the
    agent picks 3 with a reason; picks, reason and shortlist are recorded (source "agent")."""
    res, ctx, events, model = await _resolve_with(
        tmp_path, _stand_in(["E-F05", "E-F03", "E-F10"], fit_reason="dog toys sit in pet goods")
    )
    proxy = res.junior_proxy
    # the shortlist: up to 10, by popularity (ties by rank), as the model saw it
    ids = [c["entity_id"] for c in proxy.stand_in_candidates]
    assert ids[:3] == ["E-F10", "E-F03", "E-F00"] and len(ids) == 10
    assert {"entity_id", "name", "popularity", "categories"} <= set(proxy.stand_in_candidates[0])
    prompt = model.prompts_for("StandInDecision")[0]
    assert "STAND-IN SHORTLIST" in prompt and "E-F10" in prompt and "Pick exactly 3" in prompt
    # the agent's picks, in its order, with its reason
    assert proxy.comparator_brand_ids == ["E-F05", "E-F03", "E-F10"]
    assert proxy.comparator_source == "agent"
    assert proxy.comparator_rationale == "best-known dog-toy brands"
    assert proxy.measure_overlap and proxy.fit_reason == "dog toys sit in pet goods"
    rule_calls = [
        e.data["params"]
        for e in events
        if e.type == "tool_call" and e.data["tool"] == "qloo_insights_entities"
    ]
    assert rule_calls == [{"seed_entity_ids": [JD], "filter_tags": [DOG], "page": 1}]
    assert any(e.type == "decision" and "chosen by the agent" in e.title for e in events)
    # fetch seeds/targets the picks; the facts carry the stand-in line with the reason
    out = await fetch.run(
        {"resolution": res, "routing": RoutingDecision(analyses=["overlap"], rationale={})}, ctx
    )
    raw = out["raw"]
    assert raw.junior_target_entity_ids == ["E-F05", "E-F03", "E-F10"]
    ov = overlap_evidence(raw, res)
    assert ov.symmetric_percentile is not None
    facts = describe_evidence(Evidence(overlap=ov), res)
    assert facts["stand_ins"] == [
        "Stand-ins for Bad Spaniels: Pet brand 5, Pet brand 3, Pet brand 10 "
        "(chosen by the agent: best-known dog-toy brands)."
    ]
    assert "Pet brand 10" in " ".join(facts["overlap"])


async def test_resolve_tops_up_fewer_than_two_valid_picks(tmp_path: Path) -> None:
    res, _, events, _ = await _resolve_with(tmp_path, _stand_in(["E-F05", "E-NOT-LISTED"]))
    proxy = res.junior_proxy
    # one valid pick kept first, topped up by popularity from the shortlist
    assert proxy.comparator_brand_ids == ["E-F05", "E-F10", "E-F03"]
    assert proxy.comparator_source == "mixed"
    assert any("not on the shortlist were dropped" in e.title for e in events)
    assert any(e.type == "note" and "code topped up by popularity" in e.title for e in events)


async def test_resolve_never_uses_the_other_sides_brand_as_stand_in(tmp_path: Path) -> None:
    """Vans v. MSCHF: Vans was a stand-in for its own opponent. The other side's entity (by id)
    and any brand with its normalised name (a duplicate entity) are removed from the shortlist
    before the model sees it; picking them anyway is invalid (code falls back to the rule)."""
    write_fixtures(tmp_path)
    p = tmp_path / "insights_brand_seed_jack_daniels_filter_pet_tags.json"
    body = json.loads(p.read_text(encoding="utf-8"))
    dup = {**_ent("E-JD-DUP", "JACK DANIELS", [DOG]), "popularity": 0.999}
    same = {**_ent(JD, "Jack Daniel's", [DOG]), "popularity": 1.0}
    body["results"]["entities"] = [same, dup, *body["results"]["entities"]]
    p.write_text(json.dumps(body), encoding="utf-8")
    model = ScriptedChatModel(
        scripts={
            "resolve": list(RESOLVE_LOOP),
            "ResolveDecision": [RESOLVE_DECISION],
            "StandInDecision": [_stand_in([JD, "E-JD-DUP"])],
        }
    )
    ctx, _ = make_ctx(FixtureClient(tmp_path), model)
    proxy = (await resolve.run({"extraction": Extraction.model_validate(EXTRACTION)}, ctx))[
        "resolution"
    ].junior_proxy
    listed = {c["entity_id"] for c in proxy.stand_in_candidates}
    assert JD not in listed and "E-JD-DUP" not in listed
    assert JD not in model.prompts_for("StandInDecision")[0].split("STAND-IN SHORTLIST")[1]
    assert len(proxy.comparator_brand_ids) == 3
    assert JD not in proxy.comparator_brand_ids and "E-JD-DUP" not in proxy.comparator_brand_ids
    assert proxy.comparator_source == "rule"


TOO_FAR = (
    "Qloo's brand categories have no node for dog-toy novelty goods; the nearest is too far "
    "to compare audiences"
)


async def test_measure_overlap_false_skips_overlap_and_carries_fit_reason(
    tmp_path: Path,
) -> None:
    from tearose.agent.nodes.memo import proxy_limitations
    from tearose.scoring import compute_evidence

    res, ctx, events, _ = await _resolve_with(
        tmp_path, _stand_in(["E-F10", "E-F03", "E-F00"], measure_overlap=False, fit_reason=TOO_FAR)
    )
    proxy = res.junior_proxy
    assert proxy.measure_overlap is False and proxy.fit_reason == TOO_FAR
    assert proxy.comparator_source == "agent"  # the picks still stand (fame, bridging, zone)
    assert res.overlap_blocked() == [proxy]
    routing = RoutingDecision(analyses=["overlap", "bridging", "fame"], rationale={})
    n_before = len(ctx.tools.queries)
    out = await fetch.run({"resolution": res, "routing": routing}, ctx)
    new = ctx.tools.queries[n_before:]
    # no overlap paging and no compare; bridging (insights tags) and fame still fetched
    assert not any(
        q.params.get("filter.type") == "urn:entity:brand" or "compare" in q.endpoint for q in new
    )
    assert out["raw"].senior_seed_junior_universe is None
    assert out["raw"].senior_tags and out["raw"].senior_demographics is not None
    assert any("Overlap skipped" in e.title for e in events)
    ev = compute_evidence(out["raw"], res, routing)
    assert ev.overlap is None and ev.bridging is not None and ev.fame is not None
    facts = describe_evidence(ev, res)
    assert TOO_FAR in facts["overlap"][0] and facts["overlap"][0].startswith("Overlap: not")
    lims = proxy_limitations({"resolution": res})
    assert any(TOO_FAR in x for x in lims)


def test_resolve_prompt_describes_the_stand_in_flow() -> None:
    from tearose.agent.nodes.base import load_prompt

    prompt = load_prompt("resolve")
    assert "Propose 3-5" not in prompt and "STAND-IN SHORTLIST" in prompt
    assert "comparator_rationale" in prompt and "measure_overlap" in prompt
    assert "fit_reason" in prompt
    assert resolve.MAX_CALLS == 16 and "At most 16 tool calls" in prompt


# --------------------------------------------------------------------------------------
# reasoning effort (LLM_REASONING_EFFORT)
# --------------------------------------------------------------------------------------


def _settings(**kw: Any) -> Any:
    from tearose.config import Settings

    return Settings(_env_file=None, OPENAI_API_KEY="sk-test", **kw)  # type: ignore[call-arg]


def test_reasoning_effort_passed_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import tearose.config as config
    from tearose.agent.llm import get_chat_model

    monkeypatch.setattr(config, "get_settings", lambda: _settings(llm_reasoning_effort="high"))
    assert get_chat_model().reasoning_effort == "high"  # type: ignore[attr-defined]
    monkeypatch.setattr(config, "get_settings", lambda: _settings(llm_reasoning_effort=None))
    assert get_chat_model().reasoning_effort is None  # type: ignore[attr-defined]


async def test_reasoning_effort_dropped_once_on_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_openai import ChatOpenAI

    import tearose.config as config
    from tearose.agent.llm import drain_model_notes, get_chat_model

    seen: list[str | None] = []

    async def fake(self: Any, messages: Any, stop: Any = None, run_manager: Any = None, **kw: Any):
        seen.append(self.reasoning_effort)
        if self.reasoning_effort is not None:
            raise ValueError("Unsupported parameter: 'reasoning_effort' is not supported")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake)
    monkeypatch.setattr(config, "get_settings", lambda: _settings(llm_reasoning_effort="high"))
    model = get_chat_model()
    reply = await model.ainvoke([HumanMessage("hi")])
    assert reply.content == "ok" and seen == ["high", None]
    notes = drain_model_notes(model)
    assert len(notes) == 1 and "reasoning_effort='high'" in notes[0]
    assert drain_model_notes(model) == []
    await model.ainvoke([HumanMessage("again")])  # stays off: no second failure
    assert seen == ["high", None, None]

    async def other(self: Any, messages: Any, stop: Any = None, run_manager: Any = None, **kw: Any):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(ChatOpenAI, "_agenerate", other)
    fresh = get_chat_model()
    with pytest.raises(RuntimeError):  # an unrelated error is not swallowed
        await fresh.ainvoke([HumanMessage("x")])


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
            "PreliminaryRead": [PRELIM_READ, PRELIM_READ],
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
    # Token accounting is always present; the scripted model reports no tokens, so it reads zero.
    assert r.llm_usage is not None and r.llm_usage.calls == 0 and r.llm_usage.cost_usd is None
    assert r.trace[-1].data["llm_usage"]["calls"] == 0
    assert all("llm_calls" in e.data for e in r.trace if e.type == "node_finished")
    nodes_started = [e.node for e in r.trace if e.type == "node_started"]
    assert nodes_started == [
        "extract", "route", "resolve", "fetch", "score", "interpret", "assess", "memo"
    ]  # fmt: skip
    assert any(
        e.node == "assess" and e.type == "decision"
        and e.title == "Preliminary read: leans toward VIP Products (moderate)"
        for e in r.trace
    )  # fmt: skip

    assert r.extraction and r.routing and r.resolution
    assert set(r.routing.analyses) == {"overlap", "bridging", "fame"}
    assert r.evidence is not None and r.evidence.overlap is not None
    memo = r.memo
    assert memo is not None
    assert memo.headline == "Jack Daniel's fans show little affinity for dog-toy brands."
    # computed in code from the leans (relatedness favors junior, fame favors senior), not scripted
    assert memo.bottom_line == (
        "Taste data cuts against Jack Daniel's on the one confusion factor measured but "
        "supports Jack Daniel's on fame. Mark similarity, intent and actual confusion are read "
        "from the pleadings in the preliminary read, not measured."
    )
    state = engine.state_of("r1")
    assert memo.bottom_line == synthesize_bottom_line(memo.findings, *party_names(state))
    assert memo.limitations[-5:] == list(FIXED_LIMITATIONS)
    assert memo.limitations[0] == INTERPRETATION["limitations"][0]
    assert [s.id for s in memo.sections] == ["summary", "read", "factors", "method", "limitations"]
    # the preliminary read: model fields kept, fixed sentence and read line set in code
    read = memo.preliminary_read
    assert read is not None and read.lean == "newcomer"
    assert read.not_a_prediction == NOT_A_PREDICTION
    assert memo.read_line == (
        "Preliminary read: leans toward VIP Products, moderate confidence; turns on the parody "
        "defence."
    )
    assert memo.read_line == synthesize_read_line(read, *party_names(state))
    read_sec = memo.sections[1]
    assert read_sec.title == "Preliminary read"
    assert read_sec.markdown.startswith(memo.read_line)  # the draft had no read: code wrote it
    assert "parody defence would weigh" in read_sec.markdown  # flip risks listed
    assert NOT_A_PREDICTION in read_sec.markdown
    assert len(memo.appendix_queries) >= 10
    assert memo.appendix_queries == engine.state_of("r1")["queries"]

    # both prompts carry the code-written fact sentences, and no float with > 2 decimals
    # the fixture's Qloo entity is spelled "Jack Daniels"; the facts use the document's spelling
    assert r.resolution.senior.entity_name == "Jack Daniels"
    assert display_names(state) == {"senior": "Jack Daniel's"}
    facts = describe_evidence(r.evidence, r.resolution, names=display_names(state))
    assess_prompt = model.prompts_for("PreliminaryRead")[0]
    assert "DOCUMENT (complaint):" in assess_prompt and "Count II alleges dilution" in assess_prompt
    assert "Jack Daniel's fans rank the dog-toy comparators low" in assess_prompt  # findings
    assert '"preliminary_read"' in model.prompts_for("MemoDraft")[0]
    for schema in ("Interpretation", "PreliminaryRead", "MemoDraft"):
        prompt = model.prompts_for(schema)[0]
        assert "FACTS (computed in code; the only source for numbers)" in prompt
        facts_part = prompt[prompt.index("FACTS (computed in code") :].split("\n\n", 1)[0]
        assert "Jack Daniels" not in facts_part, schema
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
    followup_nodes = [e.node for e in r.trace if e.type == "node_started"][8:]
    assert followup_nodes == [
        "followup", "resolve", "fetch", "score", "interpret", "assess", "memo"
    ]  # fmt: skip
    assert r.memo.preliminary_read is not None
    # the planner saw the current memo including its preliminary read
    assert "current_preliminary_read" in model.prompts_for("FollowupPlan")[0]
    assert "turns on the parody defence" in model.prompts_for("FollowupPlan")[0]
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
    decision["junior"]["comparator_entity_ids"] = [
        "FA4E0000-0000-4000-A000-000000000004"
    ]  # ignored
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
            "PreliminaryRead": [PRELIM_READ],
            "MemoDraft": [MEMO_DRAFT],
        }
    )
    engine = GraphEngine(client=client, model_factory=lambda strong=False: model)
    handle = new_handle()
    await engine.run(handle, TEXT)
    r = handle.result
    assert r.status == "finished", r.error
    assert r.memo is not None and r.memo.preliminary_read is not None
    jp = r.resolution.junior_proxy
    assert len(jp.comparator_brand_names) == 3
    assert jp.comparator_source == "rule"  # the model's proposal is ignored
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
    # same name after normalisation: the document's spelling wins over Qloo's "Jack Daniels";
    # a different entity name ("Jack Daniel's Tennessee Honey") is kept as resolved
    res = proxied_resolution()
    res.senior.entity_name = "Jack Daniels"
    state = {"extraction": ex, "resolution": res}
    assert party_names(state) == ("Jack Daniel's", "VIP Products")
    assert display_names(state) == {"senior": "Jack Daniel's"}  # proxied junior: no override
    assert display_name("Jack Daniels", ex.senior) == "Jack Daniel's"
    assert display_name("Jack Daniel's Tennessee Honey", ex.senior) == (
        "Jack Daniel's Tennessee Honey"
    )
    assert display_name("Jack Daniels", None) == "Jack Daniels"
    # marks written in capitals (as opinions do) never replace the Qloo name
    lv = ex.senior.model_copy(
        update={"name": "Louis Vuitton Malletier", "marks": ["LOUIS VUITTON"]}
    )
    assert display_name("Louis Vuitton", lv) == "Louis Vuitton"
    coach = ex.senior.model_copy(update={"name": "COACH", "marks": ["COACH", "COACH's"]})
    assert display_name("Coach", coach) == "Coach"
    caps_jd = ex.senior.model_copy(update={"name": "JACK DANIEL'S", "marks": ["JACK DANIEL'S"]})
    assert display_name("Jack Daniels", caps_jd) == "Jack Daniels"
    # nothing known: role phrases in the bottom line
    assert party_names({}) == (None, None)


# --------------------------------------------------------------------------------------
# (7) assess: the preliminary read
# --------------------------------------------------------------------------------------

PARODY_TEXT = TEXT + (
    " VIP Products answers that Bad Spaniels is a parody of the whiskey brand and protected "
    "expressive use."
)
OPINION_TEXT = (
    "OPINION. Jack Daniel's Properties, Inc. v. VIP Products LLC. VIP Products sells dog toys "
    '"Bad Spaniels" imitating the JACK DANIEL\'S bottle. VIP argues parody. We hold that the '
    "parody defence fails because the toy uses the mark as a source identifier."
)


def assess_state(text: str, **extraction: Any) -> dict[str, Any]:
    ex = Extraction.model_validate({**EXTRACTION, **extraction})
    return {
        "input_text": text,
        "extraction": ex,
        "routing": RoutingDecision(analyses=["overlap", "fame"], rationale={}),
        "resolution": proxied_resolution(),
        "evidence": Evidence(),
        "findings": [FactorFinding.model_validate(f) for f in INTERPRETATION["findings"]],
        "case_limitations": [],
        "queries": [],
    }


def read_with(**update: Any) -> dict[str, Any]:
    return {**json.loads(json.dumps(PRELIM_READ)), **update}


async def run_memo(client: FixtureClient, state: dict[str, Any], draft: dict[str, Any]) -> Memo:
    model = ScriptedChatModel(scripts={"MemoDraft": [draft]})
    ctx, _ = make_ctx(client, model)
    return (await memo.run(state, ctx))["memo"]


async def test_assess_parody_defence_yields_flip_risk(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={"PreliminaryRead": [PRELIM_READ]})
    ctx, events = make_ctx(client, model)
    state = assess_state(PARODY_TEXT)
    out = await assess.run(state, ctx)
    read: PreliminaryRead = out["preliminary_read"]
    assert any("parody" in r.lower() for r in read.flip_risks)
    assert next(f for f in read.read_factors if f.factor == "defences").lean == "favors_junior"
    assert read.not_a_prediction == NOT_A_PREDICTION  # code resets the fixed sentence
    prompt = model.prompts_for("PreliminaryRead")[0]
    assert "protected expressive use" in prompt  # the document itself reaches the model
    assert "FACTS (computed in code; the only source for numbers)" in prompt
    assert not [e for e in events if e.type == "warning"]

    # the memo's model section paraphrases without stating the lean: the read line goes first
    state["preliminary_read"] = read
    draft = {**MEMO_DRAFT, "sections": [
        *MEMO_DRAFT["sections"],
        {"id": "read", "title": "Read", "markdown": "The pleading raises a parody defence."},
    ]}  # fmt: skip
    m = await run_memo(client, state, draft)
    sec = next(s for s in m.sections if s.id == "read")
    assert [s.id for s in m.sections][:2] == ["summary", "read"]
    assert sec.title == "Preliminary read"
    assert sec.markdown.startswith(m.read_line + "\n\nThe pleading raises a parody defence.")
    assert sec.markdown.endswith(f"_{NOT_A_PREDICTION}_")


async def test_memo_keeps_a_read_section_that_states_the_lean(client: FixtureClient) -> None:
    state = assess_state(TEXT)
    state["preliminary_read"] = PreliminaryRead.model_validate(PRELIM_READ)
    md = f"The read leans towards VIP Products, with moderate confidence.\n\n{NOT_A_PREDICTION}"
    draft = {**MEMO_DRAFT, "sections": [{"id": "read", "title": "x", "markdown": md}]}
    m = await run_memo(client, state, draft)
    assert next(s for s in m.sections if s.id == "read").markdown == md


async def test_assess_opinion_disregards_the_holding(client: FixtureClient) -> None:
    turns_on = (
        "The case most likely turns on the parody defence; assessed from the facts as pleaded; "
        "the court's holding was disregarded."
    )
    model = ScriptedChatModel(scripts={"PreliminaryRead": [read_with(turns_on=turns_on)]})
    ctx, events = make_ctx(client, model)
    out = await assess.run(assess_state(OPINION_TEXT, document_type="opinion"), ctx)
    read = out["preliminary_read"]
    assert read.turns_on.endswith("the court's holding was disregarded.")
    titles = [e.title for e in events if e.type == "note"]
    assert "Court opinion: read from the facts and the parties' arguments only" in titles
    assert "Stated holding disregarded" in titles
    assert "DOCUMENT (opinion):" in model.prompts_for("PreliminaryRead")[0]
    # the read line keeps only what the case turns on
    assert synthesize_read_line(read, "Jack Daniel's", "VIP Products") == (
        "Preliminary read: leans toward VIP Products, moderate confidence; turns on the parody "
        "defence."
    )


async def test_assess_guardrails_letter_and_unknown_data_factors(client: FixtureClient) -> None:
    scripted = read_with(
        lean="older_brand",
        confidence="high",
        data_factors_used=["fame", "similarity_of_marks"],
        flip_risks=[],
    )
    model = ScriptedChatModel(scripts={"PreliminaryRead": [scripted]})
    ctx, events = make_ctx(client, model)
    out = await assess.run(assess_state(TEXT, document_type="cease_and_desist"), ctx)
    read = out["preliminary_read"]
    assert read.confidence == "low"  # a letter is never more than a low-confidence read
    assert read.data_factors_used == ["fame"]
    warnings = [e.title for e in events if e.type == "warning"]
    assert "Letter, not a pleading: confidence lowered to low" in warnings
    assert "Data factors not among the findings dropped" in warnings
    assert "No flip risks listed" in warnings
    decision = next(e for e in events if e.type == "decision")
    assert decision.title == "Preliminary read: leans toward Jack Daniel's (low)"


async def test_assess_failure_leaves_memo_without_a_read(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={})  # no PreliminaryRead scripted: the call fails
    ctx, events = make_ctx(client, model)
    state = assess_state(TEXT)
    out = await assess.run(state, ctx)
    assert out["preliminary_read"] is None and out["errors"][0].startswith("assess:")
    assert any(e.type == "warning" and "Preliminary read failed" in e.title for e in events)
    state.update(out)
    m = await run_memo(client, state, MEMO_DRAFT)
    assert m.read_line == "" and m.preliminary_read is None
    assert "read" not in [s.id for s in m.sections]


async def test_assess_truncates_long_documents(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={"PreliminaryRead": [PRELIM_READ]})
    ctx, events = make_ctx(client, model)
    long_text = TEXT + " filler" * (assess.MAX_DOC_CHARS // 6)
    await assess.run(assess_state(long_text), ctx)
    prompt = model.prompts_for("PreliminaryRead")[0]
    assert f"truncated at {assess.MAX_DOC_CHARS:,}" in prompt
    assert "Count II alleges dilution by tarnishment" in prompt  # extraction key quotes
    assert any(e.title == "Document truncated for the preliminary read" for e in events)


async def test_assess_one_sided_input_caps_confidence_and_says_so(client: FixtureClient) -> None:
    scripted = read_with(
        lean="older_brand",
        confidence="medium",
        one_sided_input=True,
        rationale="The audience data is mixed. On the pleading, the label is imitated.",
        best_defence="The imitated element may be common in the trade and not protectable.",
    )
    model = ScriptedChatModel(scripts={"PreliminaryRead": [scripted]})
    ctx, events = make_ctx(client, model)
    state = assess_state(TEXT)
    out = await assess.run(state, ctx)
    read: PreliminaryRead = out["preliminary_read"]
    assert read.one_sided_input and read.confidence == "low"
    assert read.rationale.endswith(assess.ONE_SIDED_NOTE)
    warnings = [e.title for e in events if e.type == "warning"]
    assert "Plaintiff's pleading only: confidence lowered to low" in warnings
    line = synthesize_read_line(read, "Jack Daniel's", "VIP Products")
    assert line == (
        "Preliminary read: leans toward Jack Daniel's, low confidence; turns on the parody "
        "defence; the defendant's side is not in the record."
    )
    # the memo's read section carries the steelmanned defence
    state.update(out)
    m = await run_memo(client, state, MEMO_DRAFT)
    sec = next(s for s in m.sections if s.id == "read")
    assert "**Strongest defence**: The imitated element may be common" in sec.markdown
    assert m.read_line == line


async def test_assess_one_sided_keeps_a_rationale_that_already_says_so(
    client: FixtureClient,
) -> None:
    rationale = "The audience data is mixed. The defendant's side is not in the record yet."
    scripted = read_with(confidence="low", one_sided_input=True, rationale=rationale)
    model = ScriptedChatModel(scripts={"PreliminaryRead": [scripted]})
    ctx, events = make_ctx(client, model)
    read = (await assess.run(assess_state(TEXT), ctx))["preliminary_read"]
    assert read.rationale == rationale
    assert not [e for e in events if e.type == "warning"]


async def test_assess_two_sided_input_and_missing_best_defence(client: FixtureClient) -> None:
    model = ScriptedChatModel(scripts={"PreliminaryRead": [read_with(best_defence="")]})
    ctx, events = make_ctx(client, model)
    read = (await assess.run(assess_state(PARODY_TEXT), ctx))["preliminary_read"]
    assert not read.one_sided_input and read.confidence == "medium"
    assert "not in the record" not in synthesize_read_line(read, "A", "B")
    assert [e.title for e in events if e.type == "warning"] == ["No best defence stated"]


async def test_assess_warns_when_new_read_factors_are_missing(client: FixtureClient) -> None:
    factors = [f for f in PRELIM_READ["read_factors"]
               if f["factor"] not in ("protectability", "mark_strength")]  # fmt: skip
    model = ScriptedChatModel(scripts={"PreliminaryRead": [read_with(read_factors=factors)]})
    ctx, events = make_ctx(client, model)
    await assess.run(assess_state(TEXT), ctx)
    missing = next(e for e in events if e.title == "Read factors not addressed")
    assert missing.detail == "protectability, mark_strength"


def test_assess_prompt_rules_are_generic() -> None:
    from tearose.agent.nodes.base import load_prompt

    prompt = load_prompt("assess")
    for needle in ("`protectability`", "`mark_strength`", "`best_defence`",
                   "`one_sided_input: true`", "secondary meaning", "functionality",
                   "`too_close_to_call` is required"):  # fmt: skip
        assert needle in prompt
    # the rules are not tuned to any evaluated case: no case, brand or outcome hints
    banned = r"jack daniel|spaniel|vip|adidas|thom browne|bang|monster|reign"
    assert not re.search(banned, prompt, re.I)
    assert READ_FACTORS == (
        "similarity_of_marks", "intent", "actual_confusion", "buyer_care", "protectability",
        "mark_strength", "defences", "other",
    )  # fmt: skip


def test_stored_read_without_new_fields_still_loads() -> None:
    old = {k: v for k, v in PRELIM_READ.items() if k not in ("best_defence", "one_sided_input")}
    read = PreliminaryRead.model_validate(old)
    assert read.best_defence == "" and read.one_sided_input is False
    assert synthesize_read_line(read, "A", "B").endswith("turns on the parody defence.")


def test_stored_memo_without_read_still_loads() -> None:
    m = Memo.model_validate(
        {"headline": "h", "findings": [], "sections": [], "limitations": [],
         "appendix_queries": []}
    )  # fmt: skip
    assert m.read_line == "" and m.preliminary_read is None


def _reply(**usage: Any) -> Any:
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    msg = AIMessage(content="ok")
    msg.usage_metadata = usage or None  # type: ignore[assignment]
    return ChatResult(generations=[ChatGeneration(message=msg)])


async def test_usage_is_summed_over_calls_and_costed_when_prices_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI

    import tearose.config as config
    from tearose.agent.llm import get_chat_model, model_usage, total_usage

    replies = [
        _reply(
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
            input_token_details={"cache_read": 400},
            output_token_details={"reasoning": 150},
        ),
        _reply(input_tokens=500, output_tokens=100, total_tokens=600),
        _reply(),  # a provider that sends no usage counts as a call with zero tokens
    ]

    async def fake(self: Any, messages: Any, stop: Any = None, run_manager: Any = None, **kw: Any):
        return replies.pop(0)

    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake)
    monkeypatch.setattr(
        config, "get_settings", lambda: _settings(llm_model="m1", llm_reasoning_effort="low")
    )
    model = get_chat_model()
    for _ in range(3):
        await model.ainvoke([HumanMessage("hi")])
    u = model_usage(model)
    assert (u.model, u.reasoning_effort, u.calls) == ("m1", "low", 3)
    assert (u.input_tokens, u.cached_input_tokens) == (1500, 400)
    assert (u.output_tokens, u.reasoning_tokens) == (300, 150)
    assert u.cost_usd is None  # no prices configured

    # Prices: fresh input at 2, cached input at 0.5, output at 10 USD per million tokens.
    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: _settings(
            llm_price_input_per_m=2.0,
            llm_price_cached_input_per_m=0.5,
            llm_price_output_per_m=10.0,
        ),
    )
    replies.append(
        _reply(
            input_tokens=1_000_000,
            output_tokens=100_000,
            total_tokens=1_100_000,
            input_token_details={"cache_read": 200_000},
        )
    )
    priced = get_chat_model()
    await priced.ainvoke([HumanMessage("hi")])
    assert model_usage(priced).cost_usd == pytest.approx(0.8 * 2.0 + 0.2 * 0.5 + 0.1 * 10.0)

    # Totals over several instances; a model without a counter (the scripted fake) adds nothing.
    total = total_usage([model, priced, ScriptedChatModel()])
    assert (total.calls, total.input_tokens) == (4, 1_001_500)
    assert total.cost_usd == pytest.approx(model_usage(priced).cost_usd)


def test_usage_add_keeps_cost_unknown_until_one_side_knows_it() -> None:
    from tearose.schemas import LlmUsage

    a = LlmUsage(calls=1, input_tokens=10)
    b = LlmUsage(calls=2, output_tokens=5, cost_usd=0.25)
    assert a.add(a).cost_usd is None
    assert a.add(b).cost_usd == 0.25 and a.add(b).calls == 3
