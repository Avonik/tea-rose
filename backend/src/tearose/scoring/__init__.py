"""Deterministic scoring. No model call may ever live in this package.

Entry point used by the agent graph's `score` node:

    from tearose.scoring import compute_evidence
    evidence: Evidence = compute_evidence(raw, resolution, routing)

where `raw` is a `RawData` bundle of normalized Qloo results fetched by the agent. See
score.py for the definitions (ARCHITECTURE.md, "Scoring definitions").
"""

from tearose.scoring.score import RawData, compute_evidence  # noqa: F401
