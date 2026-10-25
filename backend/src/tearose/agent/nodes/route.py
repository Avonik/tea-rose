"""route: Extraction -> RoutingDecision (one structured call + deterministic guardrails)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from tearose.agent.llm import ainvoke_structured
from tearose.agent.nodes.base import NodeEvents, RunContext, load_prompt, to_json
from tearose.schemas import Analysis, Extraction, RoutingDecision

CANONICAL: tuple[Analysis, ...] = ("overlap", "bridging", "fame", "zone")

# claim -> analyses it requires, with the reason recorded when a guardrail adds one
_RULES: dict[str, tuple[tuple[Analysis, ...], str]] = {
    "likelihood_of_confusion": (
        ("overlap", "bridging"),
        "likelihood of confusion pleaded ⇒ relatedness/purchaser overlap and bridging the gap",
    ),
    "dilution": (("fame",), "dilution pleaded ⇒ fame (breadth of recognition) is an element"),
    "common_law_priority": (
        ("zone",),
        "common-law priority pleaded ⇒ geographic zone of reputation matters",
    ),
}


def apply_guardrails(
    decision: RoutingDecision, extraction: Extraction
) -> tuple[RoutingDecision, list[tuple[Analysis, str]]]:
    """Return the corrected decision and the (analysis, reason) pairs the guardrails added."""
    chosen = set(decision.analyses)
    rationale = dict(decision.rationale)
    added: list[tuple[Analysis, str]] = []
    for claim in extraction.claims:
        analyses, reason = _RULES.get(claim, ((), ""))
        for a in analyses:
            if a not in chosen:
                chosen.add(a)
                added.append((a, reason))
                rationale[a] = f"Added by guardrail: {reason}."
    if "overlap" not in chosen:
        chosen.add("overlap")
        added.append(("overlap", "overlap always runs"))
        rationale["overlap"] = "Added by guardrail: the overlap analysis always runs."
    for a in CANONICAL:
        rationale.setdefault(
            a,
            "Run." if a in chosen else "Not run: no pleaded claim makes this factor relevant.",
        )
    ordered = [a for a in CANONICAL if a in chosen]
    return RoutingDecision(analyses=ordered, rationale=rationale), added


def apply_override(
    decision: RoutingDecision, override: list[str] | None
) -> tuple[RoutingDecision, list[Analysis]]:
    """Full-coverage runs (showcase): also run every analysis in `override`. One the pleading
    does not call for is recorded as context only ("Measured for context: not pleaded ...");
    the analyses the pleading did call for keep their rationale."""
    if not override:
        return decision, []
    pleaded = set(decision.analyses)
    extra: list[Analysis] = [a for a in CANONICAL if a in set(override) and a not in pleaded]
    if not extra:
        return decision, []
    rationale = dict(decision.rationale)
    for a in extra:
        why = rationale.get(a, "").strip().removeprefix("Not run: ").rstrip(".")
        rationale[a] = "Measured for context: not pleaded" + (f" ({why})." if why else ".")
    ordered = [a for a in CANONICAL if a in pleaded or a in extra]
    return (
        RoutingDecision(analyses=ordered, rationale=rationale, context_only=extra),
        extra,
    )


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "route")
    ex: Extraction = state["extraction"]
    messages = [
        SystemMessage(load_prompt("route")),
        HumanMessage(
            "EXTRACTION:\n"
            + to_json(
                ex.model_dump(
                    mode="json", include={"document_type", "claims", "senior", "junior", "summary"}
                )
            )
        ),
    ]
    try:
        proposed = await ainvoke_structured(ctx.model(), RoutingDecision, messages)
    except Exception as exc:  # noqa: BLE001 — the guardrails alone give a valid routing
        await ev.warning("Routing model failed; using guardrails only", repr(exc))
        proposed = RoutingDecision(analyses=[], rationale={})
    final, added = apply_guardrails(proposed, ex)
    for a, reason in added:
        await ev.decision(f"Guardrail added '{a}'", reason, analysis=a)
    pleaded = list(final.analyses)
    final, extra = apply_override(final, state.get("analyses_override"))
    if extra:
        await ev.decision(
            f"Full coverage: also measuring {', '.join(extra)} for context",
            f"The pleading calls for: {', '.join(pleaded)}. The others are context, not live "
            "factors.",
            pleaded=pleaded,
            context_only=list(extra),
        )
    await ev.decision(
        f"Analyses: {', '.join(final.analyses)}",
        None,
        analyses=list(final.analyses),
        proposed=list(proposed.analyses),
        rationale=final.rationale,
        context_only=list(final.context_only),
    )
    return {"routing": final}
