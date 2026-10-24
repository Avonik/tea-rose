"""Sample court documents for the intake dropdown (data/samples/*.txt)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

HEADER_LINES = 3  # each sample starts with a 3-line source header

router = APIRouter(prefix="/api/samples", tags=["samples"])


def _samples(directory: Path) -> dict[str, Path]:
    """name (file stem) -> path. Only regular .txt files directly inside the directory, so a
    request can never address anything else (no path traversal)."""
    if not directory.is_dir():
        return {}
    return {p.stem: p for p in sorted(directory.glob("*.txt")) if p.is_file()}


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines()[HEADER_LINES:]:
        if line.strip():
            return line.strip()
    return fallback


@router.get("")
async def list_samples(request: Request) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for name, path in _samples(request.app.state.ctx.settings.samples_dir).items():
        text = path.read_text(encoding="utf-8", errors="replace")
        out.append({"name": name, "title": _title(text, name), "bytes": path.stat().st_size})
    return out


@router.get("/{name}", response_class=PlainTextResponse)
async def get_sample(name: str, request: Request) -> PlainTextResponse:
    samples = _samples(request.app.state.ctx.settings.samples_dir)
    path = samples.get(name.removesuffix(".txt"))
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown sample.")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))
