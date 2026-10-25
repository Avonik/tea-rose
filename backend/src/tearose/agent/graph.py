"""The LangGraph pipeline and GraphEngine (the AnalysisEngine used by the API).

Topology:

    START ─┬─> extract -> route -> resolve -> fetch -> score -> interpret -> assess -> memo -> END
           └─> followup ─┬─> resolve   (re-resolve goods / add comparator / change universe)
                         └─> score     (recompute only, reuses fetched data)

Events: every node pushes TraceEvents straight into the RunHandle through the run's emitter
while it runs (node_started, tool_call/tool_result, decision, warning, node_finished). The
engine consumes `graph.astream(stream_mode="values")` and copies the state into
`handle.result` after each node, so partial results are visible during the run.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from tearose.agent.llm import ModelFactory, get_chat_model
from tearose.agent.nodes import (
    assess,
    extract,
    fetch,
    followup,
    interpret,
    memo,
    resolve,
    route,
    score,
)
from tearose.agent.nodes.base import RunContext
from tearose.agent.runs import RunHandle
from tearose.agent.state import AgentState, initial_state
from tearose.agent.tools import ToolContext
from tearose.qloo.client import QlooClient
from tearose.schemas import AnalysisResult, TraceEvent

log = logging.getLogger(__name__)

NodeFn = Callable[[dict[str, Any], RunContext], Awaitable[dict[str, Any]]]
PIPELINE: tuple[tuple[str, NodeFn], ...] = (
    ("extract", extract.run),
    ("route", route.run),
    ("resolve", resolve.run),
    ("fetch", fetch.run),
    ("score", score.run),
    ("interpret", interpret.run),
    ("assess", assess.run),
    ("memo", memo.run),
)


def _wrap(name: str, fn: NodeFn, ctx: RunContext):
    async def node(state: AgentState) -> dict[str, Any]:
        ctx.tools.node = name
        await ctx.emit(TraceEvent(node=name, type="node_started", title=f"{name}: started"))
        t0 = time.perf_counter()
        update = await fn(dict(state), ctx)
        for note in ctx.model_notes():
            await ctx.emit(
                TraceEvent(node=name, type="note", title="Model setting dropped", detail=note)
            )
        new_queries = ctx.tools.drain_queries()
        if new_queries:
            update["queries"] = new_queries
        await ctx.emit(
            TraceEvent(
                node=name,
                type="node_finished",
                title=f"{name}: done",
                data={
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                    "queries": len(new_queries),
                },
            )
        )
        return update

    node.__name__ = f"{name}_node"
    return node


def _entry(state: AgentState) -> str:
    return "followup" if state.get("followup_question") else "extract"


def _after_followup(state: AgentState) -> str:
    if state.get("followup_action") == "recompute_only" and state.get("raw") is not None:
        return "score"
    return "resolve"


def build_graph(ctx: RunContext):
    g = StateGraph(AgentState)
    for name, fn in (*PIPELINE, ("followup", followup.run)):
        g.add_node(name, _wrap(name, fn, ctx))
    g.add_conditional_edges(START, _entry, {"extract": "extract", "followup": "followup"})
    names = [n for n, _ in PIPELINE]
    for a, b in zip(names, names[1:], strict=False):
        g.add_edge(a, b)
    g.add_edge("memo", END)
    g.add_conditional_edges("followup", _after_followup, {"resolve": "resolve", "score": "score"})
    return g.compile()


_RESULT_FIELDS = ("extraction", "routing", "resolution", "evidence", "memo")


def _apply(result: AnalysisResult, values: dict[str, Any]) -> None:
    for f in _RESULT_FIELDS:
        if values.get(f) is not None:
            setattr(result, f, values[f])


def state_from_result(result: AnalysisResult) -> AgentState:
    """Rebuild enough state for a follow-up when the in-memory state is gone (restart)."""
    st = initial_state(result.run_id, result.mode, result.input_excerpt)
    for f in _RESULT_FIELDS:
        st[f] = getattr(result, f)  # type: ignore[literal-required]
    if result.memo is not None:
        st["queries"] = list(result.memo.appendix_queries)
        st["findings"] = list(result.memo.findings)
        st["preliminary_read"] = result.memo.preliminary_read
    return st


class GraphEngine:
    """AnalysisEngine backed by the LangGraph pipeline."""

    def __init__(
        self,
        client: QlooClient | None = None,
        model_factory: ModelFactory | None = None,
        *,
        blind: bool = False,
        keep_states: int = 64,
        analyses_override: list[str] | None = None,
    ) -> None:
        self._client = client
        self._model_factory = model_factory or get_chat_model
        self.blind = blind
        self.analyses_override = analyses_override
        self._keep = keep_states
        self._states: OrderedDict[str, AgentState] = OrderedDict()

    @property
    def client(self) -> QlooClient:
        if self._client is None:
            from tearose.qloo.client import get_qloo_client

            self._client = get_qloo_client()
        return self._client

    def state_of(self, run_id: str) -> AgentState | None:
        return self._states.get(run_id)

    def _remember(self, run_id: str, state: AgentState) -> None:
        self._states[run_id] = state
        self._states.move_to_end(run_id)
        while len(self._states) > self._keep:
            self._states.popitem(last=False)

    async def run(self, handle: RunHandle, text: str) -> None:
        state = initial_state(
            handle.run_id,
            handle.result.mode,
            text,
            blind=self.blind,
            analyses_override=self.analyses_override,
        )
        await self._execute(handle, state, "extract", "Run started", query_offset=0)

    async def followup(self, handle: RunHandle, question: str) -> None:
        base = self._states.get(handle.run_id) or state_from_result(handle.result)
        if base.get("extraction") is None:
            await handle.emit(
                TraceEvent(node="followup", type="run_failed", title="Nothing to follow up on")
            )
            await handle.set_status("failed", error="follow-up requires a completed extraction")
            return
        state: AgentState = {**base, "followup_question": question, "errors": []}  # type: ignore[typeddict-item]
        await self._execute(
            handle,
            state,
            "followup",
            f"Follow-up: {question[:80]}",
            query_offset=len(base.get("queries") or []),
        )

    async def _execute(
        self, handle: RunHandle, state: AgentState, first: str, title: str, *, query_offset: int
    ) -> None:
        await handle.set_status("running")
        await handle.emit(
            TraceEvent(node=first, type="run_started", title=title, data={"mode": state["mode"]})
        )
        tools = ToolContext(self.client, handle.emit, query_offset=query_offset)
        ctx = RunContext(
            client=self.client, model_factory=self._model_factory, emit=handle.emit, tools=tools
        )
        graph = build_graph(ctx)
        final: dict[str, Any] = dict(state)
        try:
            async for values in graph.astream(state, stream_mode="values"):
                final = values
                _apply(handle.result, values)
        except Exception as exc:  # noqa: BLE001 — every failure ends the run visibly
            log.exception("run %s failed in %s", handle.run_id, tools.node)
            msg = f"{tools.node}: {type(exc).__name__}: {exc}"
            await handle.emit(
                TraceEvent(node=tools.node, type="run_failed", title="Run failed", detail=msg)
            )
            await handle.set_status("failed", error=msg)
            return
        self._remember(handle.run_id, final)  # type: ignore[arg-type]
        memo_ = final.get("memo")
        await handle.emit(
            TraceEvent(
                node="memo",
                type="run_finished",
                title="Memo ready",
                detail=memo_.headline if memo_ else None,
                data={"queries": len(final.get("queries") or []), "errors": final.get("errors")},
            )
        )
        await handle.set_status("finished")
