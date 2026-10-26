"""Pre-compute showcase cases so the public front door costs nothing per visitor.

Usage (needs an LLM key; Qloo mode from .env):

    uv run python -m tearose.eval.precompute_showcase            # all cases in the manifest
    uv run python -m tearose.eval.precompute_showcase bad_spaniels taco_tuesday
    uv run python -m tearose.eval.precompute_showcase --all-analyses   # full question coverage

`--all-analyses` makes the route node run overlap, bridging, fame AND zone regardless of what
was pleaded (GraphEngine(analyses_override=...)); the routing rationale records the analyses
the pleading did not call for as "Measured for context: not pleaded", and the interpret step
marks their findings as context, not live factors. The showcase uses it so that every case
answers all three customer questions (overlap, fame, zone) plus bridging.

Manifest: backend/data/showcase/manifest.json
    {"cases": [{"slug": "bad_spaniels", "sample": "bad_spaniels_complaint", "title": "..."}]}

Each case runs through the full GraphEngine (same code path as a live run) and is written to
backend/data/showcase/<slug>.json as an AnalysisResult with showcase_slug set. The API loads
that directory at startup. Results are generated on the server and gitignored: they contain
Qloo-derived numbers but no raw responses.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from tearose.agent.engine import AnalysisEngine, get_engine
from tearose.agent.nodes.route import CANONICAL
from tearose.agent.runs import RunStore
from tearose.config import get_settings
from tearose.schemas import AnalysisResult, TraceEvent


def _load_manifest(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("cases", []))


ALL_ANALYSES_FLAG = "--all-analyses"


def make_engine(all_analyses: bool) -> AnalysisEngine:
    """The app's engine, or one that runs every analysis (unpleaded ones as context)."""
    if not all_analyses:
        return get_engine()
    from tearose.agent.graph import GraphEngine

    return GraphEngine(analyses_override=list(CANONICAL))


async def _run_case(
    case: dict[str, str],
    text: str,
    out_dir: Path,
    mode: str,
    *,
    all_analyses: bool = False,
) -> AnalysisResult:
    engine = make_engine(all_analyses)
    store = RunStore()
    result = AnalysisResult(
        run_id=f"showcase-{case['slug']}",
        status="queued",
        mode=mode,  # type: ignore[arg-type]
        showcase_slug=case["slug"],
        input_excerpt=text[:600],
    )
    handle = store.create(result)

    async def _print_events() -> None:
        async for ev in handle.events():
            ev: TraceEvent
            if ev.type in ("decision", "warning", "node_finished", "run_failed"):
                print(f"  [{ev.node}] {ev.title}")

    t0 = time.perf_counter()
    printer = asyncio.create_task(_print_events())
    await engine.run(handle, text)
    await printer
    elapsed = time.perf_counter() - t0
    if case.get("title") and handle.result.extraction:
        handle.result.extraction.title = case["title"]
    out = out_dir / f"{case['slug']}.json"
    out.write_text(handle.result.model_dump_json(indent=2), encoding="utf-8")
    n_q = len(handle.result.memo.appendix_queries) if handle.result.memo else 0
    print(f"-> {out.name}: {handle.result.status}, {n_q} queries, {elapsed:.1f}s")
    return handle.result


async def main(argv: list[str]) -> int:
    s = get_settings()
    out_dir = s.showcase_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = _load_manifest(out_dir / "manifest.json")
    all_analyses = ALL_ANALYSES_FLAG in argv
    wanted = {a for a in argv if not a.startswith("--")} or {c["slug"] for c in cases}
    failures = 0
    for case in cases:
        if case["slug"] not in wanted:
            continue
        sample = s.samples_dir / f"{case['sample']}.txt"
        if not sample.exists():
            print(f"!! {case['slug']}: sample missing: {sample}")
            failures += 1
            continue
        print(f"== {case['slug']} ({sample.name}, mode={s.qloo_mode})")
        try:
            res = await _run_case(
                case,
                sample.read_text(encoding="utf-8"),
                out_dir,
                s.qloo_mode,
                all_analyses=all_analyses,
            )
            failures += res.status != "finished"
        except Exception as e:  # noqa: BLE001 — report and continue with the next case
            print(f"!! {case['slug']}: {type(e).__name__}: {e}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
