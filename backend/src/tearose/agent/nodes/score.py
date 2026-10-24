"""score: RawData -> Evidence. Pure code, no model (ARCHITECTURE principle 1)."""

from __future__ import annotations

from typing import Any

from tearose import scoring
from tearose.agent.nodes.base import NodeEvents, RunContext
from tearose.schemas import Evidence
from tearose.scoring.raw import RawData


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


async def run(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    ev = NodeEvents(ctx.emit, "score")
    raw = state.get("raw") or RawData()
    try:
        evidence = scoring.compute_evidence(raw, state.get("resolution"), state.get("routing"))
    except Exception as exc:  # noqa: BLE001 — scoring must be total; record and degrade
        await ev.warning("Scoring raised; evidence left empty", f"{type(exc).__name__}: {exc}")
        return {"evidence": Evidence(), "errors": [f"score: {type(exc).__name__}: {exc}"]}
    parts = []
    if evidence.overlap:
        parts.append(f"overlap percentile {_fmt(evidence.overlap.symmetric_percentile)}")
    if evidence.bridging:
        parts.append(f"bridging percentile {_fmt(evidence.bridging.percentile)}")
    if evidence.fame:
        parts.append(f"fame breadth {_fmt(evidence.fame.breadth_score)}")
    if evidence.zone:
        parts.append(f"zone concentration {_fmt(evidence.zone.concentration_index)}")
    await ev.decision(
        "Scores: " + ("; ".join(parts) or "no evidence computed"),
        "Computed in code from the fetched data; no model involved.",
    )
    return {"evidence": evidence}
