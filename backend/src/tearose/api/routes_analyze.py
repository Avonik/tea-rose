"""Live analysis: start a run, read its state, stream its trace (SSE), ask follow-ups.

Runs are private to the session that started them; ownership lives in ApiContext.run_owners.
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator, Coroutine
from typing import Annotated, Any

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sse_starlette.sse import EventSourceResponse

from tearose.agent.engine import AnalysisEngine
from tearose.agent.runs import RunHandle, RunStore
from tearose.api.auth import require_session
from tearose.api.context import ApiContext, get_ctx
from tearose.schemas import AnalysisResult, TraceEvent

log = logging.getLogger("tearose.api")

MAX_INPUT_BYTES = 2 * 1024 * 1024
EXCERPT_CHARS = 600
_MULTIPART_OVERHEAD = 64 * 1024

router = APIRouter(prefix="/api/analyze", tags=["analyze"])

SessionId = Annotated[str, Depends(require_session)]
Ctx = Annotated[ApiContext, Depends(get_ctx)]


class AnalyzeText(BaseModel):
    text: str


class FollowupBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


# --- input -----------------------------------------------------------------------------------


def _too_large() -> HTTPException:
    return HTTPException(status_code=413, detail="Input is larger than 2 MB.")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read the PDF.") from exc


async def read_input(request: Request) -> str:
    """Text from a JSON body {text} or a multipart `file` (.txt/.pdf). Raises 4xx on bad input."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_INPUT_BYTES + _MULTIPART_OVERHEAD:
        raise _too_large()
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form(max_files=1, max_fields=4)
        try:
            upload = form.get("file")
            if upload is None or isinstance(upload, str):
                raise HTTPException(status_code=400, detail="Missing multipart field 'file'.")
            data = await upload.read(MAX_INPUT_BYTES + 1)
            name = (upload.filename or "").lower()
        finally:
            await form.close()
        if len(data) > MAX_INPUT_BYTES:
            raise _too_large()
        if name.endswith(".pdf") or data.startswith(b"%PDF-"):
            text = await asyncio.to_thread(_pdf_text, data)
        elif name.endswith(".txt") or not name:
            text = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(status_code=415, detail="Upload a .txt or .pdf file.")
        empty_msg = "No extractable text in the file (a scanned PDF needs OCR first)."
    else:
        body = await request.body()
        if len(body) > MAX_INPUT_BYTES:
            raise _too_large()
        try:
            text = AnalyzeText.model_validate_json(body).text
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Send JSON {text} or a file.") from exc
        empty_msg = "The text is empty."
    text = text.replace("\x00", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=empty_msg)
    return text


# --- background execution ----------------------------------------------------------------------


def _resolve_engine(ctx: ApiContext) -> AnalysisEngine:
    if ctx.engine is None:
        from tearose.agent.engine import get_engine

        try:
            ctx.engine = get_engine()
        except ImportError as exc:
            log.error("analysis engine unavailable: %s", exc)
            raise HTTPException(status_code=503, detail="Analysis engine unavailable.") from exc
    return ctx.engine


def _schedule(ctx: ApiContext, handle: RunHandle, coro: Coroutine[Any, Any, None]) -> None:
    async def _guarded() -> None:
        try:
            await coro
        except asyncio.CancelledError:
            await handle.set_status("failed", "Run cancelled (server shutting down).")
            raise
        except Exception as exc:
            log.exception("run %s failed", handle.run_id)
            msg = f"{type(exc).__name__}: {exc}"
            await handle.emit(
                TraceEvent(node="engine", type="run_failed", title="Run failed", detail=msg)
            )
            await handle.set_status("failed", msg)

    task = asyncio.create_task(_guarded(), name=f"run-{handle.run_id}")
    ctx.tasks.add(task)
    task.add_done_callback(ctx.tasks.discard)


def _owned_handle(ctx: ApiContext, run_id: str, sid: str) -> RunHandle:
    handle = ctx.store.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="Unknown run.")
    if ctx.run_owners.get(run_id) != sid:
        raise HTTPException(status_code=403, detail="This run belongs to another session.")
    return handle


# --- routes ------------------------------------------------------------------------------------


@router.post("", status_code=202)
async def start_analysis(
    request: Request,
    sid: SessionId,
    ctx: Ctx,
) -> JSONResponse:
    text = await read_input(request)
    engine = _resolve_engine(ctx)
    reason = ctx.caps.try_consume(sid)
    if reason is not None:
        return JSONResponse(
            {"detail": reason, "kind": "cap"},
            status_code=429,
            headers={"Retry-After": str(ctx.caps.seconds_until_reset())},
        )
    result = AnalysisResult(
        run_id=RunStore.new_run_id(),
        status="queued",
        mode=ctx.settings.qloo_mode,
        input_excerpt=text[:EXCERPT_CHARS],
    )
    handle = ctx.store.create(result)
    ctx.run_owners[result.run_id] = sid
    _schedule(ctx, handle, engine.run(handle, text))
    log.info("run %s queued (%d chars)", result.run_id, len(text))
    return JSONResponse({"run_id": result.run_id}, status_code=202)


@router.get("/{run_id}", response_model=AnalysisResult)
async def get_analysis(
    run_id: str, sid: SessionId, ctx: Ctx
) -> AnalysisResult:
    return _owned_handle(ctx, run_id, sid).result


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    sid: SessionId,
    ctx: Ctx,
    after: Annotated[int | None, Query(ge=0)] = None,
) -> EventSourceResponse:
    handle = _owned_handle(ctx, run_id, sid)
    if after is None:  # EventSource reconnects send Last-Event-ID instead
        last = request.headers.get("last-event-id", "")
        after = int(last) if last.isdigit() else 0
    start = after

    async def gen() -> AsyncIterator[dict[str, str]]:
        async for ev in handle.events(start):
            yield {"event": "trace", "id": str(ev.seq), "data": ev.model_dump_json()}
        res = handle.result
        yield {
            "event": "done",
            "data": orjson.dumps({"status": res.status, "error": res.error}).decode(),
        }

    return EventSourceResponse(gen(), ping=15, headers={"X-Accel-Buffering": "no"})


@router.post("/{run_id}/followup", status_code=202)
async def followup(
    run_id: str,
    body: FollowupBody,
    sid: SessionId,
    ctx: Ctx,
) -> JSONResponse:
    handle = _owned_handle(ctx, run_id, sid)
    if handle.result.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail="The run is still in progress.")
    engine = _resolve_engine(ctx)
    _schedule(ctx, handle, engine.followup(handle, body.question.strip()))
    return JSONResponse({"run_id": run_id}, status_code=202)
