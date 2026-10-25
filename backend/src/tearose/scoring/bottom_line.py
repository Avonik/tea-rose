"""The memo's synthesised bottom line, computed from factor leans in code (no model call).

Neutral by construction: it counts which side each factor's lean favours, names the senior mark
and the junior user symmetrically, and always states what the taste graph cannot speak to.
A clause whose counted findings are all low-confidence carries " (low confidence)".
"""

from __future__ import annotations

from tearose.schemas import FactorFinding, FactorLean

CONFUSION_FACTORS: tuple[str, ...] = (
    "relatedness_of_goods",
    "channels_and_purchasers",
    "bridging_the_gap",
)
SILENT_CLAUSE = "It is silent on mark similarity, intent and actual confusion."

_VERB: dict[str, str] = {
    "favors_senior": "supports the senior mark",
    "favors_junior": "cuts against the senior mark",
    "neutral": "is neutral",
}


def _factors(n: int) -> str:
    return "factor" if n == 1 else "factors"


def _of(c: int, n: int) -> str:
    """'2 of 3 confusion factors', 'all 3 confusion factors', 'both ...', 'the one ...'."""
    if n == 1:
        return "the one confusion factor measured"
    if c == n:
        return "both confusion factors measured" if n == 2 else f"all {n} confusion factors"
    return f"{c} of {n} confusion {_factors(n)}"


def _finding(findings: list[FactorFinding], factor: str) -> FactorFinding | None:
    return next((f for f in findings if f.factor == factor), None)


def _lean(findings: list[FactorFinding], factor: str) -> FactorLean | None:
    f = _finding(findings, factor)
    return f.lean if f is not None else None


def _all_low(findings: list[FactorFinding]) -> bool:
    """True when the clause counts at least one finding and every one has low confidence."""
    return bool(findings) and all(f.confidence == "low" for f in findings)


LOW = " (low confidence)"


def synthesize_bottom_line(findings: list[FactorFinding]) -> str:
    """One deterministic bottom line from the factor leans; see ARCHITECTURE.md, "Memo"."""
    confusion = [f for f in findings if f.factor in CONFUSION_FACTORS]
    measured = [f for f in confusion if f.lean != "insufficient_data"]
    missing = len(confusion) - len(measured)
    n = len(measured)
    s = sum(f.lean == "favors_senior" for f in measured)
    j = sum(f.lean == "favors_junior" for f in measured)

    direction: str | None = None  # the uniform direction of the confusion factors, if any
    if not confusion:
        lead = ""
    elif n == 0:
        lead = "is inconclusive on the confusion factors"
    elif s and j:
        lead = f"supports the senior mark on {s} confusion {_factors(s)} and the junior user on {j}"
    elif s:
        lead, direction = f"{_VERB['favors_senior']} on {_of(s, n)}", "favors_senior"
    elif j:
        lead, direction = f"{_VERB['favors_junior']} on {_of(j, n)}", "favors_junior"
    else:
        lead, direction = f"is neutral on {_of(n, n)}", "neutral"
    low = n > 0 and _all_low(measured)
    if missing:
        has = "has" if missing == 1 else "have"
        tag = "low confidence; " if low else ""
        lead += f" ({tag}{missing} {_factors(missing)} {has} insufficient data)"
    elif low:
        lead += LOW

    parts = [lead] if lead else []
    fame_f = _finding(findings, "fame")
    fame = fame_f.lean if fame_f is not None else None
    fame_low = LOW if fame_f is not None and fame_f.confidence == "low" else ""
    if fame in _VERB:
        if not lead:
            parts.append(f"{_VERB[fame]} on fame")
        elif fame == direction:
            parts.append("and on fame")
        elif fame == "neutral":
            parts.append("and is neutral on fame")
        elif direction == "favors_senior":
            parts.append("but not on fame")
        elif direction in ("favors_junior", "neutral"):
            parts.append(f"but {_VERB[fame]} on fame")
        else:
            parts.append(f"and {_VERB[fame]} on fame")
        parts[-1] += fame_low

    body = " ".join(parts)
    zone_f = _finding(findings, "zone_of_reputation")
    zone = {
        "favors_senior": "shows a wide zone of reputation",
        "favors_junior": "shows a narrow zone of reputation",
    }.get(zone_f.lean if zone_f is not None else "")
    if zone and zone_f is not None and zone_f.confidence == "low":
        zone += LOW
    if zone:
        body = f"{body}, and {zone}" if body else zone

    if not body:
        return f"Taste data produced no factor findings. {SILENT_CLAUSE}"
    return f"Taste data {body}. {SILENT_CLAUSE}"
