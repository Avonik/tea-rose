"""Shared plumbing for nodes: run context, trace emitter, prompt loading, the tool loop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from tearose.agent.llm import ModelFactory, drain_model_notes
from tearose.agent.tools import Emit, ToolContext, dumps
from tearose.qloo.client import QlooClient
from tearose.schemas import TraceEvent

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class RunContext:
    """Everything a node needs besides the state. One per graph invocation."""

    client: QlooClient
    model_factory: ModelFactory
    emit: Emit
    tools: ToolContext
    models: list[BaseChatModel] = field(default_factory=list)

    def model(self, strong: bool = False) -> BaseChatModel:
        m = self.model_factory(strong)
        if not any(x is m for x in self.models):
            self.models.append(m)
        return m

    def model_notes(self) -> list[str]:
        """Trace notes the models queued since the last call (reasoning_effort fallback)."""
        return [n for m in self.models for n in drain_model_notes(m)]


class NodeEvents:
    """Emitter bound to one node: node_started / decision / note / warning / node_finished."""

    def __init__(self, emit: Emit, node: str) -> None:
        self._emit = emit
        self.node = node

    async def _send(self, type_: str, title: str, detail: str | None, data: dict[str, Any]):
        await self._emit(
            TraceEvent(node=self.node, type=type_, title=title, detail=detail, data=data)
        )

    async def started(self, title: str | None = None, **data: Any) -> None:
        await self._send("node_started", title or f"{self.node}: started", None, data)

    async def finished(self, title: str | None = None, **data: Any) -> None:
        await self._send("node_finished", title or f"{self.node}: done", None, data)

    async def decision(self, title: str, detail: str | None = None, **data: Any) -> None:
        await self._send("decision", title, detail, data)

    async def note(self, title: str, detail: str | None = None, **data: Any) -> None:
        await self._send("note", title, detail, data)

    async def warning(self, title: str, detail: str | None = None, **data: Any) -> None:
        await self._send("warning", title, detail, data)


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def to_json(obj: Any, **dump_kwargs: Any) -> str:
    """Compact JSON for prompts; pydantic models dumped in JSON mode without None fields."""
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json", exclude_none=True, **dump_kwargs)
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


def instruction_block(state: dict[str, Any]) -> str:
    instr = state.get("instruction")
    if not instr:
        return ""
    return f"\n\nFOLLOW-UP INSTRUCTION FROM COUNSEL (takes priority where it applies):\n{instr}"


def first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return m.group(1) if m else text


async def run_tool_loop(
    model: BaseChatModel,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    *,
    max_calls: int,
    ev: NodeEvents,
    used: int = 0,
) -> int:
    """Let the model call tools until it stops or the cap is reached. Mutates `messages`.

    Returns the total number of tool calls made (including `used` from earlier rounds).
    Every tool_call in an AIMessage is answered with a ToolMessage, even when capped.
    """
    bound = model.bind_tools(tools)
    by_name = {t.name: t for t in tools}
    calls = used
    while calls < max_calls:
        ai = await bound.ainvoke(messages)
        if not isinstance(ai, AIMessage):
            ai = AIMessage(content=str(getattr(ai, "content", ai)))
        messages.append(ai)
        if not ai.tool_calls:
            break
        for tc in ai.tool_calls:
            tc_id = tc.get("id") or f"call_{calls}"
            if calls >= max_calls:
                content = dumps({"error": f"tool-call cap of {max_calls} reached; stop now"})
            elif (tool := by_name.get(tc["name"])) is None:
                content = dumps({"error": f"unknown tool {tc['name']!r}"})
            else:
                calls += 1
                try:
                    content = str(await tool.ainvoke(tc.get("args") or {}))
                except Exception as exc:  # noqa: BLE001 — the model gets the error, run goes on
                    await ev.warning(f"{tc['name']} raised", f"{type(exc).__name__}: {exc}")
                    content = dumps({"error": f"{type(exc).__name__}: {exc}"})
            messages.append(ToolMessage(content=content, tool_call_id=tc_id, name=tc["name"]))
    if calls >= max_calls:
        await ev.warning(f"Tool-call cap reached ({max_calls})", "Remaining gaps go to code.")
    return calls
