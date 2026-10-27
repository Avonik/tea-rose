"""Chat-model factory (OpenAI-compatible) plus a scripted fake model for tests.

`get_chat_model()` is the only place a real model is constructed. Nodes receive a
`ModelFactory` so tests can inject `ScriptedChatModel` and never touch the network.

Structured output goes through `ainvoke_structured`: native `.with_structured_output()`
(function calling) first, then a JSON-mode fallback that parses the reply text.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable, Sequence
from functools import cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from tearose.schemas import LlmUsage

ModelFactory = Callable[[bool], BaseChatModel]

log = logging.getLogger(__name__)


def reasoning_rejected(exc: BaseException) -> bool:
    """A provider error that plausibly rejects the reasoning_effort parameter."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return status in (400, 422) or "reasoning" in str(exc).lower()


LLM_TIMEOUT_S = 180


@cache
def _fallback_chat_class() -> type[BaseChatModel]:
    """ChatOpenAI that drops `reasoning_effort` once when the provider rejects it: the call is
    retried without it, the model keeps it off, and a note is queued for the run trace."""
    from langchain_openai import ChatOpenAI

    class ReasoningFallbackChatOpenAI(ChatOpenAI):
        fallback_notes: list[str] = Field(default_factory=list, exclude=True)
        usage: LlmUsage = Field(default_factory=LlmUsage, exclude=True)

        def _count(self, result: ChatResult) -> ChatResult:
            self.usage = self.usage.add(usage_of(result, self.model_name, self.reasoning_effort))
            return result

        def _drop_reasoning(self, exc: BaseException) -> bool:
            if self.reasoning_effort is None or not reasoning_rejected(exc):
                return False
            note = (
                f"The model provider rejected reasoning_effort={self.reasoning_effort!r} "
                f"({type(exc).__name__}: {str(exc)[:160]}); retried without it."
            )
            log.warning(note)
            self.fallback_notes.append(note)
            self.reasoning_effort = None
            return True

        async def _agenerate(self, messages: Any, stop: Any = None, run_manager: Any = None,
                             **kwargs: Any) -> ChatResult:  # fmt: skip
            try:
                return self._count(await super()._agenerate(messages, stop, run_manager, **kwargs))
            except Exception as exc:
                if not self._drop_reasoning(exc):
                    raise
            return self._count(await super()._agenerate(messages, stop, run_manager, **kwargs))

        def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None,
                      **kwargs: Any) -> ChatResult:  # fmt: skip
            try:
                return self._count(super()._generate(messages, stop, run_manager, **kwargs))
            except Exception as exc:
                if not self._drop_reasoning(exc):
                    raise
            return self._count(super()._generate(messages, stop, run_manager, **kwargs))

    return ReasoningFallbackChatOpenAI


def usage_of(result: ChatResult, model: str = "", effort: str | None = None) -> LlmUsage:
    """One call's tokens from the reply's usage_metadata (zero when the provider sent none)."""
    tokens: dict[str, Any] = {}
    for g in result.generations:
        meta = getattr(g.message, "usage_metadata", None)
        if meta:
            tokens = dict(meta)
            break
    in_details = tokens.get("input_token_details") or {}
    out_details = tokens.get("output_token_details") or {}
    usage = LlmUsage(
        model=model,
        reasoning_effort=effort,
        calls=1,
        input_tokens=int(tokens.get("input_tokens") or 0),
        cached_input_tokens=int(in_details.get("cache_read") or 0),
        output_tokens=int(tokens.get("output_tokens") or 0),
        reasoning_tokens=int(out_details.get("reasoning") or 0),
    )
    usage.cost_usd = cost_usd(usage)
    return usage


def cost_usd(usage: LlmUsage) -> float | None:
    """The cost at the configured LLM_PRICE_* rates (USD per million tokens); None without them."""
    from tearose.config import get_settings

    s = get_settings()
    if s.llm_price_input_per_m is None or s.llm_price_output_per_m is None:
        return None
    cached_rate = (
        s.llm_price_input_per_m
        if s.llm_price_cached_input_per_m is None
        else s.llm_price_cached_input_per_m
    )
    fresh = usage.input_tokens - usage.cached_input_tokens
    return (
        fresh * s.llm_price_input_per_m
        + usage.cached_input_tokens * cached_rate
        + usage.output_tokens * s.llm_price_output_per_m
    ) / 1_000_000


def model_usage(model: Any) -> LlmUsage:
    """What a model instance has consumed so far (empty for models that do not count)."""
    usage = getattr(model, "usage", None)
    return usage if isinstance(usage, LlmUsage) else LlmUsage()


def total_usage(models: Sequence[Any]) -> LlmUsage:
    total = LlmUsage()
    for m in models:
        total = total.add(model_usage(m))
    return total


def drain_model_notes(model: Any) -> list[str]:
    """Notes a model queued for the trace (reasoning_effort fallback), cleared on read."""
    notes = getattr(model, "fallback_notes", None)
    if not isinstance(notes, list) or not notes:
        return []
    out = list(notes)
    notes.clear()
    return out


def get_chat_model(strong: bool = False) -> BaseChatModel:
    """The production model. `strong=True` uses `llm_model_strong` when configured;
    `llm_reasoning_effort` is passed as `reasoning_effort` when set."""
    from tearose.config import get_settings

    s = get_settings()
    model = (s.llm_model_strong or s.llm_model) if strong else s.llm_model
    kwargs: dict[str, object] = {}
    if s.llm_temperature is not None:  # gpt-5 family rejects any explicit temperature
        kwargs["temperature"] = s.llm_temperature
    if s.llm_reasoning_effort:
        kwargs["reasoning_effort"] = s.llm_reasoning_effort
    return _fallback_chat_class()(
        model=model,
        api_key=s.llm_api_key or None,
        base_url=s.llm_base_url,
        timeout=LLM_TIMEOUT_S,  # a hung provider call must fail, not stall a run for an hour
        max_retries=2,
        **kwargs,  # type: ignore[arg-type]
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
