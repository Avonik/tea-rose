"""AnalysisEngine: the seam between the API layer and the agent graph.

The API creates a RunHandle, then schedules `engine.run(handle, text)` as a background task and
streams `handle.events()`. The graph implementation lives in agent/graph.py (GraphEngine).
ScriptedEngine is a deterministic stand-in for API tests and frontend development.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from tearose.agent.runs import RunHandle
from tearose.schemas import (
    Extraction,
    FactorFinding,
    Memo,
    MemoSection,
    Party,
    PreliminaryRead,
    ReadFactor,
    RoutingDecision,
    TraceEvent,
)
from tearose.scoring import synthesize_bottom_line, synthesize_read_line

# the scripted read the mock runs carry (tests, frontend development)
SCRIPTED_READ = PreliminaryRead(
    lean="newcomer",
    confidence="medium",
    turns_on="The case most likely turns on the parody defence and the relatedness of the goods.",
    rationale=(
        "The audience data shows little overlap between whiskey drinkers and dog-toy buyers, "
        "while the senior brand's audience is broad. On the pleading, the marks are close by "
        "design and the junior user pleads parody; no actual confusion is alleged."
    ),
    flip_risks=[
        "A court that rejects the parody defence would weigh the near-identical trade dress "
        "more heavily.",
        "A consumer survey showing source confusion would change the confusion factors.",
        "The junior user is measured through stand-in dog-toy brands, not its own audience.",
    ],
    read_factors=[
        ReadFactor(factor="similarity_of_marks", lean="favors_senior", confidence="high",
                   basis="document", finding='The toy imitates the "bottle shape" and label.'),
        ReadFactor(factor="intent", lean="neutral", confidence="low", basis="document",
                   finding="Intent to parody, not to confuse, is asserted."),
        ReadFactor(factor="actual_confusion", lean="insufficient_data", confidence="low",
                   basis="document", finding="Not alleged."),
        ReadFactor(factor="buyer_care", lean="insufficient_data", confidence="low",
                   basis="document", finding="Not alleged."),
        ReadFactor(factor="protectability", lean="favors_senior", confidence="medium",
                   basis="document", finding="The senior trade dress is registered."),
        ReadFactor(factor="mark_strength", lean="favors_senior", confidence="medium",
                   basis="document", finding="A long-used, widely known mark."),
        ReadFactor(factor="defences", lean="favors_junior", confidence="medium",
                   basis="document", finding="Parody is pleaded as a defence."),
    ],
    best_defence="Parody: the toy comments on the senior label rather than naming its source.",
    data_factors_used=["relatedness_of_goods"],
)  # fmt: skip


class AnalysisEngine(Protocol):
    async def run(self, handle: RunHandle, text: str) -> None:
        """Populate handle.result step by step, emitting TraceEvents; set status at the end."""

    async def followup(self, handle: RunHandle, question: str) -> None:
        """Answer a follow-up question by re-running the affected part of the pipeline."""


def get_engine() -> AnalysisEngine:
    """Default engine for the app. Imported lazily so the API can start without LangGraph."""
    from tearose.agent.graph import GraphEngine

    return GraphEngine()


class ScriptedEngine:
    """Emits a plausible trace and a minimal result without any model or Qloo call."""

    def __init__(self, delay_s: float = 0.05) -> None:
        self.delay_s = delay_s

    async def _step(self, handle: RunHandle, node: str, title: str, detail: str | None = None):
        await handle.emit(TraceEvent(node=node, type="node_started", title=f"{node}: started"))
        await asyncio.sleep(self.delay_s)
        await handle.emit(TraceEvent(node=node, type="decision", title=title, detail=detail))
        await handle.emit(TraceEvent(node=node, type="node_finished", title=f"{node}: done"))

    async def run(self, handle: RunHandle, text: str) -> None:
        r = handle.result
        await handle.set_status("running")
        await handle.emit(TraceEvent(node="extract", type="run_started", title="Run started"))
        await self._step(handle, "extract", "Parties: Jack Daniel's Properties v. VIP Products")
        r.extraction = Extraction(
            document_type="complaint",
            title="Jack Daniel's Properties, Inc. v. VIP Products LLC",
            senior=Party(
                side="senior",
                name="Jack Daniel's Properties",
                marks=["Jack Daniel's"],
                goods=["Tennessee whiskey"],
            ),
            junior=Party(
                side="junior", name="VIP Products LLC", marks=["Bad Spaniels"], goods=["dog toys"]
            ),
            claims=["likelihood_of_confusion", "dilution"],
            summary="Scripted placeholder result for development.",
        )
        await self._step(handle, "route", "Running overlap, bridging and fame (dilution pleaded)")
        r.routing = RoutingDecision(
            analyses=["overlap", "bridging", "fame"],
            rationale={
                "overlap": "confusion pleaded",
                "bridging": "confusion pleaded",
                "fame": "dilution pleaded",
                "zone": "no priority dispute",
            },
        )
        await self._step(handle, "resolve", "Junior brand not in Qloo; proxy via 'dog toys' tags")
        await self._step(handle, "fetch", "7 Qloo queries, 1 retry with a wider tag")
        await self._step(handle, "score", "Symmetric overlap percentile 0.18")
        await self._step(handle, "interpret", "Relatedness: favors junior; fame: favors senior")
        await self._step(
            handle, "assess", "Preliminary read: leans toward VIP Products (moderate)",
            SCRIPTED_READ.turns_on,
        )  # fmt: skip
        read_line = synthesize_read_line(SCRIPTED_READ, "Jack Daniel's", "VIP Products")
        findings = [
            FactorFinding(
                factor="relatedness_of_goods",
                lean="favors_junior",
                confidence="medium",
                finding="Scripted placeholder finding.",
            ),
        ]
        r.memo = Memo(
            headline="Jack Daniel's purchasers show little affinity for pet-supply brands.",
            bottom_line=synthesize_bottom_line(findings),
            read_line=read_line,
            preliminary_read=SCRIPTED_READ,
            findings=findings,
            sections=[
                MemoSection(id="summary", title="Summary", markdown="Scripted placeholder."),
                MemoSection(
                    id="read",
                    title="Preliminary read",
                    markdown=f"{read_line}\n\n{SCRIPTED_READ.not_a_prediction}",
                ),
            ],
            limitations=["Affinity is not confusion.", "No survey percentages."],
            appendix_queries=[],
        )
        await handle.emit(TraceEvent(node="memo", type="run_finished", title="Memo ready"))
        await handle.set_status("finished")

    async def followup(self, handle: RunHandle, question: str) -> None:
        await handle.set_status("running")
        await self._step(handle, "followup", f"Re-ran resolve for: {question[:60]}")
        await handle.emit(TraceEvent(node="followup", type="run_finished", title="Updated"))
        await handle.set_status("finished")
