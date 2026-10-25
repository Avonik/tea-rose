"""The memo's one-sentence preliminary read, computed in code from a PreliminaryRead.

"Preliminary read: leans toward Jack Daniel's, moderate confidence; turns on the parody
defence." A read on the plaintiff's pleading alone ends "...; the defendant's side is not in
the record." The lean and confidence come from the model's structured fields; the sentence is
built here so it can never carry an outcome word ("win", "verdict", ...) or a percentage.
"""

from __future__ import annotations

import re

from tearose.schemas import PreliminaryRead

SENIOR_ROLE = "the older brand"
JUNIOR_ROLE = "the newcomer"
CONFIDENCE_WORD = {"high": "high", "medium": "moderate", "low": "low"}
# appended when the input is the plaintiff's pleading only
ONE_SIDED_CAVEAT = "the defendant's side is not in the record"

# words a preliminary read must never carry (it is not a prediction or a probability)
FORBIDDEN = re.compile(
    r"%|\bpercent(?:age)?s?\b|\bprobab\w*|\bpredict\w*|\bverdicts?\b|\bwin(?:s|ning|ner|ners)?\b"
    r"|\bwon\b|\blos(?:e|es|ing|er|ers|t)\b",
    re.I,
)


def has_forbidden(text: str) -> bool:
    return bool(FORBIDDEN.search(text or ""))


def _name(name: str | None, role: str) -> str:
    name = " ".join((name or "").split()).rstrip(" .,;:")
    return name if name and not has_forbidden(name) else role


def lean_target(read: PreliminaryRead, senior: str | None, junior: str | None) -> str:
    """'toward Jack Daniel's' / 'toward VIP Products' / 'too close to call'."""
    if read.lean == "older_brand":
        return f"toward {_name(senior, SENIOR_ROLE)}"
    if read.lean == "newcomer":
        return f"toward {_name(junior, JUNIOR_ROLE)}"
    return "too close to call"


MAX_CLAUSE = 150


def turns_on_clause(turns_on: str) -> str:
    """The object of 'turns on' from the model's sentence ("The case most likely turns on the
    parody defence." -> "the parody defence"), or "" when none can be taken safely."""
    text = " ".join((turns_on or "").split())
    m = re.search(r"\bturns?\s+on\s+(.+)", text, flags=re.I)
    if not m:
        return ""
    clause = re.split(r"[.;:!?](?:\s|$)|;", m.group(1))[0].strip(" ,.;:")
    if len(clause) > MAX_CLAUSE:  # long sentence: keep the first idea, cut at a natural boundary
        head = clause[:MAX_CLAUSE]
        boundaries = (", and ", " and whether ", ", ", "; ")
        cut = max(head.rfind(b) for b in boundaries)
        clause = (head[:cut] if cut > 40 else head.rsplit(" ", 1)[0]).strip(" ,.;:")
    if not clause or has_forbidden(clause):
        return ""
    return clause


def synthesize_read_line(
    read: PreliminaryRead | None,
    senior_name: str | None = None,
    junior_name: str | None = None,
) -> str:
    """One sentence from the read's lean, confidence and turns_on (plus the one-sided caveat
    when only the plaintiff's pleading was read); "" without a read."""
    if read is None:
        return ""
    target = lean_target(read, senior_name, junior_name)
    lean = f"leans {target}" if read.lean != "too_close_to_call" else target
    line = f"Preliminary read: {lean}, {CONFIDENCE_WORD[read.confidence]} confidence"
    clause = turns_on_clause(read.turns_on)
    if clause:
        line += f"; turns on {clause}"
    if read.one_sided_input:
        line += f"; {ONE_SIDED_CAVEAT}"
    return line + "."
