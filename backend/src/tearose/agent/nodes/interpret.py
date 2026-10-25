"""interpret: Evidence -> FactorFindings + case-specific limitations (one structured call).

Blind mode (eval harness): party names, marks and resolved brand names are replaced by
"Brand A (senior)" / "Brand B (junior)" BEFORE the prompt is built. Code guardrails force
"insufficient_data" where the evidence section is empty and flag survey-style percentages.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from tearose.agent.llm import ainvoke_structured
from tearose.agent.nodes.base import (
    NodeEvents,
    RunContext,
    instruction_block,
    load_prompt,
    to_json,
)
from tearose.schemas import Evidence, Extraction, FactorFinding, Resolution
from tearose.scoring.describe import describe_evidence, facts_block

SENIOR_LABEL = "Brand A (senior)"
JUNIOR_LABEL = "Brand B (junior)"

FACTOR_SECTION = {
    "relatedness_of_goods": "overlap",
    "channels_and_purchasers": "overlap",
    "bridging_the_gap": "bridging",
    "fame": "fame",
    "zone_of_reputation": "zone",
}
_PERCENT_OF_PEOPLE = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s*(?:%|percent)\s+of\s+(?:all\s+|the\s+)?"
    r"(?:consumers|purchasers|buyers|people|respondents|customers|the public)",
    re.I,
)
_SUFFIX = re.compile(
    r",?\s+(?:inc\.?|llc|l\.l\.c\.|corp\.?|corporation|co\.|ltd\.?|company)$", re.I
)


class Interpretation(BaseModel):
    findings: list[FactorFinding]
    limitations: list[str] = Field(
        default_factory=list, description="case-specific limitations only"
    )


# --- blinding ---------------------------------------------------------------------------


def _variants(name: str | None) -> set[str]:
    if not name or len(name.strip()) < 3:
        return set()
    base = name.strip()
    out = {
        base,
        base.replace("'", "’"),
        base.replace("’", "'"),
        base.replace("'", "").replace("’", ""),
    }
    stripped = _SUFFIX.sub("", base)
    if stripped != base:
        out |= _variants(stripped)
    return {v for v in out if len(v) >= 3}


def blind_pairs(extraction: Extraction, resolution: Resolution | None) -> list[tuple[str, str]]:
    """(name, label) pairs, longest name first, for both sides."""
    pairs: dict[str, str] = {}
    for side, label in (("senior", SENIOR_LABEL), ("junior", JUNIOR_LABEL)):
        party = getattr(extraction, side)
        names: list[str | None] = [party.name, *party.marks]
        if resolution is not None:
            brand = getattr(resolution, side)
            names += [brand.entity_name, brand.query]
        for n in names:
            for v in _variants(n):
                pairs.setdefault(v, label)
    return sorted(pairs.items(), key=lambda p: len(p[0]), reverse=True)


def blind_text(text: str, pairs: list[tuple[str, str]]) -> str:
    for name, label in pairs:
        pre = r"\b" if name[0].isalnum() else ""
        post = r"\b" if name[-1].isalnum() else ""
        text = re.sub(pre + re.escape(name) + post, label, text, flags=re.I)
    return text


def maybe_blind(state: dict[str, Any], text: str) -> str:
    if not state.get("blind") or state.get("extraction") is None:
        return text
    return blind_text(text, blind_pairs(state["extraction"], state.get("resolution")))


# --- payload ----------------------------------------------------------------------------


def _round2(x: Any) -> Any:
    """Round every float in a JSON-like structure to 2 decimals (no raw floats in prompts)."""
    if isinstance(x, float):
        return round(x, 2)
    if isinstance(x, dict):
        return {k: _round2(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round2(v) for v in x]
    return x


def fact_sentences(state: dict[str, Any]) -> str:
    """The code-written FACTS block (scoring/describe.py) for the interpret and memo prompts."""
    return facts_block(describe_evidence(state.get("evidence"), state.get("resolution")))


def compact_evidence(evidence: Evidence | None) -> dict[str, Any]:
    """Evidence for the prompt: bulky lists trimmed, floats rounded to 2 decimals."""
    if evidence is None:
        return {}
    d = _round2(evidence.model_dump(mode="json"))
    if d.get("zone"):
        z = d["zone"]
        z["points"] = f"{len(z.get('points') or [])} cells (omitted)"
        z["junior_points"] = f"{len(z.get('junior_points') or [])} cells (omitted)"
    if d.get("overlap"):
        o = d["overlap"]
        for k in ("top_peers_senior_seed", "top_peers_junior_seed", "shared_affinities",
                  "distinct_to_senior", "distinct_to_junior"):  # fmt: skip
            o[k] = (o.get(k) or [])[:10]
    return d


def case_payload(state: dict[str, Any]) -> dict[str, Any]:
    ex: Extraction = state["extraction"]
    res: Resolution | None = state.get("resolution")
    routing = state.get("routing")

    def party(p: Any) -> dict[str, Any]:
        return {"name": p.name, "marks": p.marks, "goods": p.goods, "channels": p.channels,
                "geography": p.geography}  # fmt: skip

    out: dict[str, Any] = {
        "document_type": ex.document_type,
        "claims": list(ex.claims),
        "summary": ex.summary,
        "senior": party(ex.senior),
        "junior": party(ex.junior),
    }
    if routing is not None:
        out["analyses_run"] = list(routing.analyses)
        out["routing_rationale"] = routing.rationale
    if res is not None:
        out["resolution"] = {
            "senior": res.senior.entity_name or "NOT IN QLOO (proxy path)",
            "junior": res.junior.entity_name or "NOT IN QLOO (proxy path)",
            "senior_proxy": res.senior_proxy.model_dump(
                include=_PROXY_FIELDS
            ) if res.senior_proxy else None,
            "junior_proxy": res.junior_proxy.model_dump(
                include=_PROXY_FIELDS
            ) if res.junior_proxy else None,
            "universes": [u.model_dump() for u in res.universes],
        }  # fmt: skip
    return out


_PROXY_FIELDS = {"goods_phrase", "chosen_tag_ids", "fit", "fit_note", "comparator_brand_names"}


def section_has_data(evidence: Evidence | None, section: str) -> bool:
    if evidence is None:
        return False
    if section == "overlap":
        return evidence.overlap is not None and evidence.overlap.symmetric_percentile is not None
    if section == "bridging":
        return evidence.bridging is not None and evidence.bridging.percentile is not None
    if section == "fame":
        f = evidence.fame
        return f is not None and (
            f.breadth_score is not None or f.popularity_percentile is not None
        )
    if section == "zone":
        return evidence.zone is not None and evidence.zone.concentration_index is not None
    return True


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "interpret")
    evidence: Evidence | None = state.get("evidence")
    body = to_json(
        {
            "case": case_payload(state),
            "evidence": compact_evidence(evidence),
            "data_notes": (state.get("raw").notes if state.get("raw") else []),
        }
    )
    body = maybe_blind(state, body)
    facts = maybe_blind(state, fact_sentences(state))
    if state.get("blind"):
        await ev.note("Blind mode: party names replaced before prompting")
    messages = [
        SystemMessage(load_prompt("interpret")),
        HumanMessage(
            f"FACTS (computed in code; the only source for numbers):\n{facts}\n\n"
            f"CASE AND EVIDENCE:\n{body}{maybe_blind(state, instruction_block(state))}"
        ),
    ]
    try:
        out = await ainvoke_structured(ctx.model(strong=True), Interpretation, messages)
    except Exception as exc:  # noqa: BLE001 — the memo can still be written from evidence
        await ev.warning("Interpretation failed; no factor findings", repr(exc))
        return {"findings": [], "case_limitations": [], "errors": [f"interpret: {exc!r}"]}

    findings: list[FactorFinding] = []
    for f in out.findings:
        section = FACTOR_SECTION.get(f.factor)
        if section and not section_has_data(evidence, section) and f.lean != "insufficient_data":
            await ev.warning(
                f"{f.factor}: no {section} evidence; lean forced to insufficient_data",
                f"model said {f.lean}",
            )
            f = f.model_copy(update={"lean": "insufficient_data", "confidence": "low"})
        if _PERCENT_OF_PEOPLE.search(f.finding):
            await ev.warning(
                f"{f.factor}: finding reads like a survey percentage",
                "Affinity is not a share of consumers; review the wording.",
            )
        findings.append(f)
    routed = set(state["routing"].analyses) if state.get("routing") else set()
    covered = {FACTOR_SECTION.get(f.factor) for f in findings}
    for a in sorted(routed - covered):
        await ev.warning(f"No finding addresses the '{a}' analysis")
    await ev.decision(
        f"{len(findings)} factor finding(s)",
        "; ".join(f"{f.factor}: {f.lean}" for f in findings),
        findings=[f.model_dump() for f in findings],
    )
    return {"findings": findings, "case_limitations": list(out.limitations)}
