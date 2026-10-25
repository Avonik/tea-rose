"""Pre-computed showcase results: loaded once at startup from settings.showcase_dir."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from tearose.schemas import AnalysisResult, ShowcaseSummary

log = logging.getLogger("tearose.api")

_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def load_showcase(directory: Path) -> dict[str, AnalysisResult]:
    """Every `*.json` in `directory` as AnalysisResult, keyed by file stem. Tolerates a missing
    directory and skips (with a warning) files that do not validate."""
    results: dict[str, AnalysisResult] = {}
    if not directory.is_dir():
        log.info("showcase dir %s not found; no showcase cases", directory)
        return results
    for path in sorted(directory.glob("*.json")):
        try:
            res = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # one broken file must not take the app down
            log.warning("skipping showcase file %s: %s", path.name, exc)
            continue
        if res.showcase_slug is None:
            res.showcase_slug = path.stem
        results[path.stem] = res
    log.info("loaded %d showcase case(s)", len(results))
    return results


def summarize(slug: str, res: AnalysisResult) -> ShowcaseSummary:
    ex = res.extraction
    title = ex.title if ex else slug.replace("-", " ").replace("_", " ").title()
    parties = f"{ex.senior.name} v. {ex.junior.name}" if ex else ""
    one_liner = res.memo.headline if res.memo else (ex.summary if ex else "")
    year_match = _YEAR.search(title)
    tags: list[str] = []
    if ex:
        tags.extend(c.replace("_", " ") for c in ex.claims if c != "other")
    if res.resolution and (res.resolution.senior_proxy or res.resolution.junior_proxy):
        tags.append("proxy path")
    return ShowcaseSummary(
        slug=slug,
        title=title,
        parties=parties,
        year=int(year_match.group(0)) if year_match else None,
        one_liner=one_liner,
        tags=tags,
        read_line=(res.memo.read_line if res.memo else ""),
    )


router = APIRouter(prefix="/api/showcase", tags=["showcase"])


@router.get("", response_model=list[ShowcaseSummary])
async def list_showcase(request: Request) -> list[ShowcaseSummary]:
    return request.app.state.ctx.showcase_summaries


@router.get("/{slug}", response_model=AnalysisResult)
async def get_showcase(slug: str, request: Request) -> AnalysisResult:
    res = request.app.state.ctx.showcase.get(slug)
    if res is None:
        raise HTTPException(status_code=404, detail="Unknown showcase case.")
    return res
