"""assess: document + extraction + data findings -> PreliminaryRead (one structured call).

The model reads the DOCUMENT for the factors taste data cannot see (similarity of marks,
intent, actual confusion, buyer care, defences) and weighs them with the interpret findings
into a preliminary read. Code guardrails: the fixed "not a prediction" sentence, letters are
low confidence, data factors must name real findings, outcome words and percentages are
flagged. A failure leaves the memo without a read; it never ends the run.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from tearose.agent.llm import ainvoke_structured
from tearose.agent.nodes.base import (
    NodeEvents,
    RunContext,
    instruction_block,
    load_prompt,
    to_json,
)
from tearose.agent.nodes.interpret import (
    case_payload,
    fact_sentences,
    maybe_blind,
    party_names,
)
from tearose.schemas import (
    NOT_A_PREDICTION,
    READ_FACTORS,
    Extraction,
    FactorFinding,
    PreliminaryRead,
)
from tearose.scoring.read_line import CONFIDENCE_WORD, has_forbidden, lean_target

# the document goes to the prompt up to this many characters; the extraction covers the rest
MAX_DOC_CHARS = 40_000
HOLDING_NOTE = "the court's holding was disregarded"
LETTER_TYPES = ("cease_and_desist",)


def read_title(read: PreliminaryRead, senior: str | None, junior: str | None) -> str:
    """Trace title: "Preliminary read: leans toward Jack Daniel's (moderate)"."""
    target = lean_target(read, senior, junior)
    lean = f"leans {target}" if read.lean != "too_close_to_call" else target
    return f"Preliminary read: {lean} ({CONFIDENCE_WORD[read.confidence]})"


def _document(text: str, extraction: Extraction) -> str:
    if len(text) <= MAX_DOC_CHARS:
        return text
    return (
        f"{text[:MAX_DOC_CHARS]}\n[... truncated at {MAX_DOC_CHARS:,} of {len(text):,} "
        "characters; the EXTRACTION's summary and key quotes cover the whole document ...]"
    )


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "assess")
    ex: Extraction | None = state.get("extraction")
    if ex is None:
        await ev.warning("No extraction; no preliminary read")
        return {"preliminary_read": None}
    findings: list[FactorFinding] = list(state.get("findings") or [])
    text = state.get("input_text") or ""
    if len(text) > MAX_DOC_CHARS:
        await ev.note(
            "Document truncated for the preliminary read",
            f"{len(text):,} → {MAX_DOC_CHARS:,} characters; extraction added",
        )
    if ex.document_type == "opinion":
        await ev.note(
            "Court opinion: read from the facts and the parties' arguments only",
            "Any holding the opinion states is to be disregarded.",
        )
    routing = state.get("routing")
    material = to_json(
        {
            "extraction": ex.model_dump(mode="json"),
            "case": case_payload(state),
            "routing": routing.model_dump(mode="json") if routing is not None else None,
            "findings": [f.model_dump() for f in findings],
        }
    )
    messages = [
        SystemMessage(load_prompt("assess")),
        HumanMessage(
            f"DOCUMENT ({ex.document_type}):\n<<<\n{maybe_blind(state, _document(text, ex))}\n>>>"
            "\n\nFACTS (computed in code; the only source for numbers):\n"
            + maybe_blind(state, fact_sentences(state))
            + "\n\nEXTRACTION, ROUTING AND FINDINGS:\n"
            + maybe_blind(state, material)
            + maybe_blind(state, instruction_block(state))
        ),
    ]
    try:
        read = await ainvoke_structured(ctx.model(strong=True), PreliminaryRead, messages)
    except Exception as exc:  # noqa: BLE001 — the memo is still written, without a read
        await ev.warning("Preliminary read failed; the memo carries none", repr(exc))
        return {"preliminary_read": None, "errors": [f"assess: {exc!r}"]}

    update: dict[str, Any] = {"not_a_prediction": NOT_A_PREDICTION}
    if ex.document_type in LETTER_TYPES and read.confidence != "low":
        await ev.warning(
            "Letter, not a pleading: confidence lowered to low", f"model said {read.confidence}"
        )
        update["confidence"] = "low"
    known = {f.factor for f in findings}
    used = [f for f in read.data_factors_used if f in known]
    if used != read.data_factors_used:
        dropped = sorted(set(read.data_factors_used) - known)
        await ev.warning("Data factors not among the findings dropped", ", ".join(dropped))
        update["data_factors_used"] = used
    missing = [f for f in READ_FACTORS[:-1] if f not in {r.factor for r in read.read_factors}]
    if missing:
        await ev.warning("Read factors not addressed", ", ".join(missing))
    if not read.flip_risks:
        await ev.warning("No flip risks listed")
    prose = [read.turns_on, read.rationale, *read.flip_risks]
    prose += [r.finding for r in read.read_factors]
    if any(has_forbidden(p) for p in prose):
        await ev.warning(
            "Read uses an outcome word or a percentage",
            "A preliminary read is not a prediction; review the wording.",
        )
    read = read.model_copy(update=update)
    if HOLDING_NOTE in read.turns_on.lower():
        await ev.note("Stated holding disregarded", read.turns_on)

    senior, junior = party_names(state)
    await ev.decision(
        read_title(read, senior, junior),
        read.turns_on,
        read=read.model_dump(),
    )
    return {"preliminary_read": read}
