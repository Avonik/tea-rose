"""AgentState: what flows between the graph's nodes.

Pydantic models are stored as-is (no checkpointer). `queries` and `errors` accumulate via
reducers: a node returns only the new items. TraceEvents are not kept in state; they are
pushed to the RunHandle the moment a node emits them.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from tearose.qloo.models import QlooQuery
from tearose.schemas import (
    Evidence,
    Extraction,
    FactorFinding,
    Memo,
    Resolution,
    RoutingDecision,
)
from tearose.scoring.raw import RawData


class AgentState(TypedDict, total=False):
    run_id: str
    mode: Literal["fixture", "live"]
    input_text: str
    extraction: Extraction | None
    routing: RoutingDecision | None
    resolution: Resolution | None
    raw: RawData | None
    evidence: Evidence | None
    findings: list[FactorFinding]  # from interpret
    case_limitations: list[str]  # case-specific limitations from interpret
    memo: Memo | None
    queries: Annotated[list[QlooQuery], operator.add]
    followup_question: str | None
    followup_action: str | None  # FollowupPlan.action of the last follow-up
    instruction: str | None  # follow-up instruction fed to resolve/fetch/interpret/memo prompts
    blind: bool  # eval harness: prompts see "Brand A (senior)" / "Brand B (junior)"
    errors: Annotated[list[str], operator.add]


def initial_state(
    run_id: str, mode: Literal["fixture", "live"], text: str, *, blind: bool = False
) -> AgentState:
    return AgentState(
        run_id=run_id,
        mode=mode,
        input_text=text,
        extraction=None,
        routing=None,
        resolution=None,
        raw=None,
        evidence=None,
        findings=[],
        case_limitations=[],
        memo=None,
        queries=[],
        followup_question=None,
        followup_action=None,
        instruction=None,
        blind=blind,
        errors=[],
    )
