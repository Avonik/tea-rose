"""Pre-registered back-test: does Qloo's brand-overlap signal agree with how courts weighed the
relatedness-of-goods and channels/purchasers factors?

Four idempotent CLI steps, each writing to backend/eval/ (see backend/eval/README.md, "Harness"):

    uv run python -m tearose.eval.backtest prepare   # CSV -> mapping.csv     (no Qloo calls)
    uv run python -m tearose.eval.backtest resolve   # mapping -> resolved.json (/search, /v2/tags,
                                                     #   insights tags)
    uv run python -m tearose.eval.backtest score     # resolved -> scores.json (insights + scoring)
    uv run python -m tearose.eval.backtest report    # mapping + scores -> results/backtest_<date>

No language model is called anywhere in this package: every choice (query string, entity pick,
tag pick, comparator pick) is a deterministic rule written down here, so the Qloo signal is
evaluated on its own.
"""
