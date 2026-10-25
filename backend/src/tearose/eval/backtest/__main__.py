"""CLI: uv run python -m tearose.eval.backtest {prepare|resolve|score|report} [options]."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from tearose.config import get_settings
from tearose.eval.backtest import HARNESS_VERSION, prepare, report, resolve, score_step
from tearose.eval.backtest.common import (
    CASES_CSV,
    MAPPING_CSV,
    RESOLVED_NAME,
    SCORES_NAME,
    Recorder,
    default_out_dir,
    read_csv,
    read_json,
    sha256_file,
    write_json,
)
from tearose.qloo.client import get_qloo_client


def _print(title: str, data: dict[str, Any]) -> None:
    print(f"[{title}]")
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def _with_client(fn: Any) -> Any:
    client = get_qloo_client()
    try:
        return await fn(Recorder(client, live=get_settings().qloo_mode == "live"))
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tearose.eval.backtest", description=__doc__)
    ap.add_argument("step", choices=["prepare", "resolve", "score", "report"])
    ap.add_argument("--cases", type=Path, default=CASES_CSV, help="labelled cases CSV")
    ap.add_argument("--mapping", type=Path, default=MAPPING_CSV, help="pre-registered mapping")
    ap.add_argument(
        "--out", type=Path, default=None,
        help="output dir for resolved/scores/results (default: backend/eval in live mode, "
        "backend/eval/_fixture otherwise)",
    )  # fmt: skip
    ap.add_argument("--force", action="store_true", help="prepare: overwrite a differing mapping")
    ap.add_argument("--all", action="store_true", help="resolve: also rows outside every metric")
    ap.add_argument("--frontend", action="store_true", help="report: update backtest.json even "
                    "when not a live run")  # fmt: skip
    ap.add_argument("--no-frontend", action="store_true", help="report: never touch frontend")
    args = ap.parse_args(argv)

    mode = get_settings().qloo_mode
    out_dir: Path = args.out or default_out_dir(mode)

    if args.step == "prepare":
        _print("prepare", prepare.run(args.cases, args.mapping, force=args.force))
        return

    if not args.mapping.exists():
        raise SystemExit(f"{args.mapping} not found: run `prepare` first (and commit it).")
    mapping = read_csv(args.mapping)

    if args.step == "resolve":
        rows = resolve.selected_rows(mapping, args.all)
        doc = asyncio.run(
            _with_client(lambda rec: resolve.run(rec, rows, mode, sha256_file(args.mapping)))
        )
        write_json(out_dir / RESOLVED_NAME, doc)
        _print("resolve", {"mode": mode, "out": str(out_dir / RESOLVED_NAME),
                           **resolve.summarize(doc)})  # fmt: skip
    elif args.step == "score":
        resolved = read_json(out_dir / RESOLVED_NAME)
        if resolved.get("mapping_sha256") != sha256_file(args.mapping):
            raise SystemExit("resolved.json was built from a different mapping.csv; re-run resolve")
        if resolved.get("harness_version", 1) != HARNESS_VERSION:
            raise SystemExit(
                f"resolved.json was built by harness v{resolved.get('harness_version', 1)}; "
                f"re-run resolve (current harness v{HARNESS_VERSION})"
            )
        doc = asyncio.run(_with_client(lambda rec: score_step.run(rec, resolved)))
        write_json(out_dir / SCORES_NAME, doc)
        _print("score", {"mode": mode, "out": str(out_dir / SCORES_NAME),
                         **score_step.summarize(doc)})  # fmt: skip
    else:
        scores = read_json(out_dir / SCORES_NAME)
        update = (scores.get("qloo_mode") == "live" or args.frontend) and not args.no_frontend
        _print("report", report.run(mapping, scores, out_dir / "results", update))


if __name__ == "__main__":
    main()
