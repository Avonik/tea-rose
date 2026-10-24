"""extract: document text -> Extraction (one structured LLM call, verbatim checks in code)."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from tearose.agent.llm import ainvoke_structured
from tearose.agent.nodes.base import NodeEvents, RunContext, load_prompt
from tearose.schemas import Extraction

MAX_CHARS = 60_000


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().casefold()


def not_verbatim(phrases: list[str], text: str) -> list[str]:
    hay = _norm(text)
    return [p for p in phrases if p.strip() and _norm(p) not in hay]


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "extract")
    text = state["input_text"] or ""
    if len(text) > MAX_CHARS:
        await ev.warning(
            "Document truncated for extraction", f"{len(text):,} → {MAX_CHARS:,} characters"
        )
    messages = [
        SystemMessage(load_prompt("extract")),
        HumanMessage(f"DOCUMENT:\n<<<\n{text[:MAX_CHARS]}\n>>>"),
    ]
    ex = await ainvoke_structured(ctx.model(), Extraction, messages)
    # The schema's side labels are positional; make them consistent.
    ex.senior.side = "senior"
    ex.junior.side = "junior"

    goods = ex.senior.goods + ex.junior.goods
    off = not_verbatim(goods, text)
    if off:
        await ev.warning(
            "Goods phrases not found verbatim in the document",
            "; ".join(off),
            phrases=off,
        )
    off_q = not_verbatim(ex.key_quotes, text)
    if off_q:
        await ev.warning("Key quotes not found verbatim", f"{len(off_q)} quote(s)", quotes=off_q)
    if not ex.claims:
        await ev.warning("No claims identified", "Routing will default to the overlap analysis.")

    await ev.decision(
        f"Parties: {ex.senior.name} (senior) v. {ex.junior.name} (junior)",
        f"Marks: {', '.join(ex.senior.marks) or '?'} v. {', '.join(ex.junior.marks) or '?'}; "
        f"claims: {', '.join(ex.claims) or 'none'}",
        document_type=ex.document_type,
        senior_goods=ex.senior.goods,
        junior_goods=ex.junior.goods,
        claims=list(ex.claims),
    )
    return {"extraction": ex}
