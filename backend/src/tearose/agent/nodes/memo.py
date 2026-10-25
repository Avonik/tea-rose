"""memo: findings + evidence + preliminary read -> Memo (one LLM call for prose; bottom line,
read line, appendix and limitations in code)."""

from __future__ import annotations

import re
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
    JUNIOR_LABEL,
    SENIOR_LABEL,
    brand_name,
    case_payload,
    compact_evidence,
    fact_sentences,
    maybe_blind,
    party_names,
)
from tearose.schemas import NOT_A_PREDICTION, FactorFinding, Memo, MemoSection, PreliminaryRead
from tearose.scoring import synthesize_bottom_line, synthesize_read_line

FIXED_LIMITATIONS: tuple[str, ...] = (
    "Affinity is not confusion; this is evidence on the relatedness and purchaser factors, "
    "not a confusion rate.",
    "No survey percentages: Qloo affinities are normalized per query and are not population "
    "shares.",
    "Coverage gaps are stated per brand; proxied findings are marked.",
    "Data reflects current taste, not the year of the dispute.",
    "Not legal advice; a tool for counsel.",
)
READ_SECTION = ("read", "Preliminary read")
SECTION_ORDER = (
    ("summary", "Summary"),
    READ_SECTION,  # only when the run has a preliminary read
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


def read_section(read: PreliminaryRead, read_line: str) -> str:
    """Code-written "Preliminary read" section from the PreliminaryRead fields."""
    parts = [read_line, read.rationale.strip()]
    if read.best_defence.strip():
        parts.append(f"**Strongest defence**: {read.best_defence.strip()}")
    if read.flip_risks:
        parts.append("**What could change it**\n" + "\n".join(f"- {x}" for x in read.flip_risks))
    parts.append(f"_{NOT_A_PREDICTION}_")
    return "\n\n".join(p for p in parts if p)


def _states_lean(markdown: str, read: PreliminaryRead, names: tuple[str | None, ...]) -> bool:
    """True when the section states the read's lean: "too close to call", or "toward <name>"
    for the favoured side (its display name, party brand or blind label)."""
    text = " ".join(markdown.replace("’", "'").split()).casefold()
    if read.lean == "too_close_to_call":
        return "too close to call" in text
    for name in names:
        n = " ".join((name or "").replace("’", "'").split()).casefold().rstrip(" .")
        if n and re.search(r"\btowards?\s+" + re.escape(n), text):
            return True
    return False


def ensure_read_section(
    sec: MemoSection, read: PreliminaryRead, read_line: str, names: tuple[str | None, ...]
) -> MemoSection:
    """The model may paraphrase the read but not change it: without the lean stated, the
    computed read line goes first; the fixed "not a prediction" sentence is always there."""
    md = sec.markdown.strip()
    if not _states_lean(md, read, names):
        md = f"{read_line}\n\n{md}"
    if NOT_A_PREDICTION not in md:
        md = f"{md}\n\n_{NOT_A_PREDICTION}_"
    return sec.model_copy(update={"title": READ_SECTION[1], "markdown": md})


def proxy_limitations(state: dict[str, Any]) -> list[str]:
    """Code-written: how well a proxied side's category matches its goods."""
    res = state.get("resolution")
    out: list[str] = []
    for proxy in (getattr(res, "senior_proxy", None), getattr(res, "junior_proxy", None)):
        if proxy is not None and not proxy.measure_overlap and proxy.fit_reason:
            out.append(
                f"Audience overlap was not measured for the {proxy.side}: {proxy.fit_reason}"
            )
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
    read: PreliminaryRead | None = state.get("preliminary_read")
    senior, junior = party_names(state)
    read_line = synthesize_read_line(read, senior, junior)
    body = to_json(
        {
            "case": case_payload(state),
            "findings": [f.model_dump() for f in findings],
            "preliminary_read": read.model_dump() if read is not None else None,
            "read_line": read_line or None,
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
        if sid == READ_SECTION[0]:
            if read is None:
                continue
            if sec is None or not sec.markdown.strip():
                sec = MemoSection(id=sid, title=title, markdown=read_section(read, read_line))
            else:
                older = read.lean == "older_brand"
                side = (senior, SENIOR_LABEL) if older else (junior, JUNIOR_LABEL)
                sec = ensure_read_section(sec, read, read_line, side)
        elif sec is None or not sec.markdown.strip():
            sec = MemoSection(
                id=sid,
                title=title,
                markdown=_code_section(sid, findings, limitations, len(queries)),
            )
        sections.append(sec)
    sections.extend(by_id.values())

    memo = Memo(
        headline=first_sentence(draft.headline),
        bottom_line=synthesize_bottom_line(findings, senior, junior),  # code, not the model
        read_line=read_line,  # code, from the assess node's structured read
        preliminary_read=read,
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
