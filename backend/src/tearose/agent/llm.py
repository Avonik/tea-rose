"""Chat-model factory (OpenAI-compatible) plus a scripted fake model for tests.

`get_chat_model()` is the only place a real model is constructed. Nodes receive a
`ModelFactory` so tests can inject `ScriptedChatModel` and never touch the network.

Structured output goes through `ainvoke_structured`: native `.with_structured_output()`
(function calling) first, then a JSON-mode fallback that parses the reply text.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

ModelFactory = Callable[[bool], BaseChatModel]


def get_chat_model(strong: bool = False) -> BaseChatModel:
    """The production model. `strong=True` uses `llm_model_strong` when configured."""
    from langchain_openai import ChatOpenAI

    from tearose.config import get_settings

    s = get_settings()
    model = (s.llm_model_strong or s.llm_model) if strong else s.llm_model
    return ChatOpenAI(
        model=model,
        api_key=s.llm_api_key or None,
        base_url=s.llm_base_url,
        temperature=s.llm_temperature,
    )


# --------------------------------------------------------------------------------------
# Structured output with a JSON-mode fallback
# --------------------------------------------------------------------------------------


def extract_json(text: str) -> str:
    """The outermost JSON object in `text` (tolerates code fences and chatter)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model reply")
    return text[start : end + 1]


def content_text(msg: BaseMessage) -> str:
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)


async def ainvoke_structured[M: BaseModel](
    model: BaseChatModel, schema: type[M], messages: Sequence[BaseMessage]
) -> M:
    """Return a validated `schema` instance. Native structured output first, JSON mode second."""
    msgs = list(messages)
    try:
        runnable = model.with_structured_output(schema, method="function_calling")
        out = await runnable.ainvoke(msgs)
        if isinstance(out, schema):
            return out
        if isinstance(out, dict):
            return schema.model_validate(out)
        raise TypeError(f"structured output returned {type(out).__name__}")
    except Exception as first:  # noqa: BLE001 — any provider quirk falls through to JSON mode
        schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        msgs.append(
            HumanMessage(
                "Respond with ONE JSON object only (no prose, no code fence) that validates "
                f"against this JSON schema:\n{schema_json}"
            )
        )
        json_model: Any = model
        if type(model).__name__ == "ChatOpenAI":
            json_model = model.bind(response_format={"type": "json_object"})
        try:
            reply = await json_model.ainvoke(msgs)
            return schema.model_validate_json(extract_json(content_text(reply)))
        except Exception as second:  # noqa: BLE001
            raise ValueError(
                f"{schema.__name__}: structured output failed ({first!r}); "
                f"JSON fallback failed ({second!r})"
            ) from second


# --------------------------------------------------------------------------------------
# Scripted fake model (tests, local dev without a key)
# --------------------------------------------------------------------------------------


def step_key(messages: Sequence[BaseMessage]) -> str:
    """The node a prompt belongs to: the first `# word` heading of the system prompt."""
    for m in messages:
        if isinstance(m, SystemMessage):
            hit = re.match(r"\s*#\s*([\w-]+)", content_text(m))
            if hit:
                return hit.group(1).lower()
    return "default"


def tool_call(name: str, **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call"}


def ai_tools(*calls: dict[str, Any], content: str = "") -> AIMessage:
    """An AIMessage requesting the given tool calls (build them with `tool_call`)."""
    return AIMessage(content=content, tool_calls=list(calls))


def _as_messages(value: Any) -> list[BaseMessage]:
    if hasattr(value, "to_messages"):
        return list(value.to_messages())
    if isinstance(value, BaseMessage):
        return [value]
    return list(value)


class ScriptedChatModel(BaseChatModel):
    """A chat model that replays scripted responses, keyed by purpose.

    Keys: structured calls use the schema class name ("Extraction", "RoutingDecision", ...);
    plain and tool-calling calls use the node name taken from the system prompt's first
    heading ("resolve", "fetch", ...). Each key is a FIFO list whose items may be an
    AIMessage, a str/dict/BaseModel (becomes the reply content), or a callable receiving the
    messages. An exhausted plain/tool key answers "done" (no tool calls, which ends a tool
    loop); an exhausted structured key raises. Every call is recorded in `calls` as
    (key, messages) so tests can assert on prompts.
    """

    scripts: dict[str, list[Any]] = Field(default_factory=dict)
    calls: list[tuple[str, list[BaseMessage]]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def prompts_for(self, key: str) -> list[str]:
        """All message texts sent under `key`, joined per call."""
        return ["\n".join(content_text(m) for m in msgs) for k, msgs in self.calls if k == key]

    def _next(self, key: str, messages: list[BaseMessage], structured: bool) -> Any:
        self.calls.append((key, list(messages)))
        queue = self.scripts.get(key)
        if not queue:
            if structured:
                raise LookupError(f"no scripted response left for {key!r}")
            return AIMessage(content="done")
        item = queue.pop(0)
        if callable(item) and not isinstance(item, BaseModel | type):
            item = item(messages)
        return item

    @staticmethod
    def _to_ai(item: Any) -> AIMessage:
        if isinstance(item, AIMessage):
            for tc in item.tool_calls:
                tc["id"] = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            return item
        if isinstance(item, BaseModel):
            return AIMessage(content=item.model_dump_json())
        if isinstance(item, dict | list):
            return AIMessage(content=json.dumps(item))
        return AIMessage(content=str(item))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        item = self._next(step_key(messages), messages, structured=False)
        return ChatResult(generations=[ChatGeneration(message=self._to_ai(item))])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:  # type: ignore[override]
        return self  # tool calls are scripted; the tool list is irrelevant

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:  # type: ignore[override]
        def _convert(value: Any) -> Any:
            msgs = _as_messages(value)
            item = self._next(schema.__name__, msgs, structured=True)
            if isinstance(item, schema):
                return item
            if isinstance(item, BaseModel):
                item = item.model_dump()
            if isinstance(item, AIMessage):
                item = content_text(item)
            if isinstance(item, str):
                return schema.model_validate_json(extract_json(item))
            return schema.model_validate(item)

        async def _aconvert(value: Any) -> Any:
            return _convert(value)

        return RunnableLambda(_convert, afunc=_aconvert)
