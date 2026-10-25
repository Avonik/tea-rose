"""followup: counsel's question -> FollowupPlan, then re-entry into the pipeline.

Re-entry point (decided in graph.py): `recompute_only` goes to score (reusing fetched data);
everything else reruns resolve → fetch → score → interpret → assess → memo with the plan's
instruction in the prompt context. The planner sees the current memo including its preliminary
read, so a question about the read (what it turns on, what could flip it) re-runs from score and
reaches assess and memo as the instruction. Queries keep accumulating across follow-ups.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from tearose.agent.llm import ainvoke_structured
from tearose.agent.nodes.base import NodeEvents, RunContext, load_prompt, to_json
from tearose.agent.nodes.interpret import case_payload

FollowupAction = Literal[
    "re_resolve_junior_goods", "add_comparator", "change_universe", "recompute_only"
]


class FollowupPlan(BaseModel):
    action: FollowupAction
    instruction: str = Field(description="imperative instruction for the downstream steps")
    junior_goods_phrase: str | None = Field(
        default=None, description="re_resolve_junior_goods: the new goods phrase to use verbatim"
    )
    comparator_names: list[str] = Field(default_factory=list)
    rationale: str = ""


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "followup")
    question = (state.get("followup_question") or "").strip()
    memo = state.get("memo")
    read = (memo.preliminary_read if memo else None) or state.get("preliminary_read")
    body = to_json(
        {
            "question": question,
            "case": case_payload(state),
            "current_headline": memo.headline if memo else None,
            "current_findings": [f.model_dump() for f in memo.findings] if memo else [],
            "current_bottom_line": memo.bottom_line if memo else None,
            "current_read_line": memo.read_line if memo else None,
            "current_preliminary_read": read.model_dump() if read is not None else None,
            "current_sections": (
                [{"id": s.id, "title": s.title} for s in memo.sections] if memo else []
            ),
        }
    )
    messages = [SystemMessage(load_prompt("followup")), HumanMessage(f"FOLLOW-UP:\n{body}")]
    try:
        plan = await ainvoke_structured(ctx.model(), FollowupPlan, messages)
    except Exception as exc:  # noqa: BLE001 — rerun from resolve with the raw question
        await ev.warning("Follow-up planning failed; rerunning from resolve", repr(exc))
        plan = FollowupPlan(action="change_universe", instruction=question)

    update: dict[str, Any] = {"followup_action": plan.action, "followup_question": None}
    instr = f"Counsel asked: {question}\nPlan ({plan.action}): {plan.instruction}"
    if plan.comparator_names:
        instr += f"\nComparator brands to try: {', '.join(plan.comparator_names)}"
    ex = state["extraction"]
    if plan.action == "re_resolve_junior_goods" and plan.junior_goods_phrase:
        phrase = plan.junior_goods_phrase.strip()
        ex = ex.model_copy(deep=True)
        ex.junior.goods = [phrase, *[g for g in ex.junior.goods if g != phrase]]
        update["extraction"] = ex
        instr += f"\nUse the junior goods phrase {phrase!r} verbatim for the tag lookup."
    update["instruction"] = instr
    await ev.decision(
        f"Follow-up plan: {plan.action.replace('_', ' ')}",
        plan.instruction,
        plan=plan.model_dump(),
    )
    return update
