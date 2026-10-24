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
    RoutingDecision,
    TraceEvent,
)


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
        r.memo = Memo(
            headline="Jack Daniel's purchasers show little affinity for pet-supply brands.",
            findings=[
                FactorFinding(
                    factor="relatedness_of_goods",
                    lean="favors_junior",
                    confidence="medium",
                    finding="Scripted placeholder finding.",
                ),
            ],
            sections=[MemoSection(id="summary", title="Summary", markdown="Scripted placeholder.")],
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
