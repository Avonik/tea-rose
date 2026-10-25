"""Pre-registered back-test: does Qloo's brand-overlap signal agree with how courts weighed the
relatedness-of-goods and channels/purchasers factors?

Four idempotent CLI steps, each writing to backend/eval/ (see backend/eval/README.md, "Harness"):

    uv run python -m tearose.eval.backtest prepare   # CSV -> mapping.csv     (no Qloo calls)
    uv run python -m tearose.eval.backtest resolve   # mapping -> resolved.json (/search, /v2/tags,
                                                     #   insights tags)
    uv run python -m tearose.eval.backtest score     # resolved -> scores.json (insights + scoring)
    uv run python -m tearose.eval.backtest report    # mapping + scores -> results/backtest_<date>

Identification (harness v3): `resolve` runs the PRODUCT's model-driven resolve node by default
(`--resolver agent`, see agent_resolver.py), so the back-test measures the pipeline as shipped;
`--resolver rule` keeps the v2 code-only name rule. Scoring and reporting call no model: every
number comes from deterministic code.

Harness versions: 1 = the pre-registered rules (run 1, 2026-10-25, kept as the record);
2 = post-hoc fixes documented under "Deviations from pre-registration" in backend/eval/README.md
(universe = the brand's own category tags, censored ranks + direct target affinity, corrected
test-preparation synonym); 3 = identification by the product's model-driven resolver instead
of the name rule (scoring unchanged). Labels and mapping.csv are unchanged between versions.
"""

HARNESS_VERSION = 3
