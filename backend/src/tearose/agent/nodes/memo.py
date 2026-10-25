"""memo: findings + evidence -> Memo (one LLM call for prose; bottom line, appendix and
limitations in code)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from tearose.agent.llm import ainvoke_structured
from tearose.agent.nodes.base import (
    NodeEvents,
    RunContext,
    first_sentence,
    instruction_block,
    load_prompt,
    to_json,
)
from tearose.agent.nodes.interpret import (  # noqa: F401 - brand_name re-exported
    brand_name,
    case_payload,
    compact_evidence,
    fact_sentences,
    maybe_blind,
    party_names,
)
from tearose.schemas import FactorFinding, Memo, MemoSection
from tearose.scoring import synthesize_bottom_line

FIXED_LIMITATIONS: tuple[str, ...] = (
    "Affinity is not confusion; this is evidence on the relatedness and purchaser factors, "
    "not a confusion rate.",
    "No survey percentages: Qloo affinities are normalized per query and are not population "
    "shares.",
    "Coverage gaps are stated per brand; proxied findings are marked.",
    "Data reflects current taste, not the year of the dispute.",
    "Not legal advice; a tool for counsel.",
)
SECTION_ORDER = (
    ("summary", "Summary"),
    ("factors", "Factor-by-factor"),
    ("method", "Method"),
    ("limitations", "Limitations"),
)


class MemoDraft(BaseModel):
    headline: str
    sections: list[MemoSection]


def _lean(f: FactorFinding) -> str:
    return f.lean.replace("_", " ")


def _code_section(sid: str, findings: list[FactorFinding], limitations: list[str], nq: int) -> str:
    if sid == "summary":
        return " ".join(
            f"{f.factor.replace('_', ' ').capitalize()}: {_lean(f)}." for f in findings
        ) or ("No factor findings were produced.")
    if sid == "factors":
        return (
            "\n\n".join(
                f"**{f.factor.replace('_', ' ').capitalize()}** ({_lean(f)}, {f.confidence} "
                f"confidence). {f.finding}"
                for f in findings
            )
            or "No factor findings were produced."
        )
    if sid == "method":
        return (
            f"Tea Rose ran {nq} Qloo queries (listed in the appendix). Scores are computed in "
            "code from ranks within each query; the language model chose what to measure and "
            "wrote this prose, but produced no number."
        )
    return "\n".join(f"- {x}" for x in limitations)


def proxy_limitations(state: dict[str, Any]) -> list[str]:
    """Code-written: how well a proxied side's category matches its goods."""
    res = state.get("resolution")
    out: list[str] = []
    for proxy in (getattr(res, "senior_proxy", None), getattr(res, "junior_proxy", None)):
        if proxy is None or proxy.fit not in ("nearest", "partial"):
            continue
        names = ", ".join(
            str(o.get("name")) for o in proxy.tag_options if o.get("id") in proxy.chosen_tag_ids
        )
        what = (
            "nearest category, no exact match in Qloo's brand taxonomy"
            if proxy.fit == "nearest"
            else "a related or broader category, not an exact match"
        )
        out.append(
            f"The {proxy.side}'s goods ({proxy.goods_phrase!r}) are represented by "
            f"{names or 'proxy categories'}: {what}."
        )
    return out


def dedupe(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in xs if x.strip() and not (x.strip() in seen or seen.add(x.strip()))]


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "memo")
    findings: list[FactorFinding] = list(state.get("findings") or [])
    queries = list(state.get("queries") or [])
    limitations = dedupe(
        [*(state.get("case_limitations") or []), *proxy_limitations(state), *FIXED_LIMITATIONS]
    )
    body = to_json(
        {
            "case": case_payload(state),
            "findings": [f.model_dump() for f in findings],
            "evidence": compact_evidence(state.get("evidence")),
            "limitations": limitations,
            "query_count": len(queries),
            "data_notes": (state.get("raw").notes if state.get("raw") else []),
        }
    )
    messages = [
        SystemMessage(load_prompt("memo")),
        HumanMessage(
            "FACTS (computed in code; the only source for numbers):\n"
            + maybe_blind(state, fact_sentences(state))
            + "\n\nMATERIAL:\n"
            + maybe_blind(state, body)
            + maybe_blind(state, instruction_block(state))
        ),
    ]
    try:
        draft = await ainvoke_structured(ctx.model(), MemoDraft, messages)
    except Exception as exc:  # noqa: BLE001 — a code-written memo beats no memo
        await ev.warning("Memo model failed; memo written from findings in code", repr(exc))
        draft = MemoDraft(headline="Taste-graph evidence summary.", sections=[])

    by_id = {s.id: s for s in draft.sections}
    sections: list[MemoSection] = []
    for sid, title in SECTION_ORDER:
        sec = by_id.pop(sid, None)
        if sec is None or not sec.markdown.strip():
            sec = MemoSection(
                id=sid,
                title=title,
                markdown=_code_section(sid, findings, limitations, len(queries)),
            )
        sections.append(sec)
    sections.extend(by_id.values())

    memo = Memo(
        headline=first_sentence(draft.headline),
        bottom_line=synthesize_bottom_line(findings, *party_names(state)),  # code, not the model
        findings=findings,
        sections=sections,
        limitations=limitations,
        appendix_queries=queries,
    )
    await ev.decision(
        "Memo ready",
        memo.headline,
        sections=[s.id for s in sections],
        queries=len(queries),
    )
    return {"memo": memo}
