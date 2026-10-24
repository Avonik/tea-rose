"""FastAPI app factory, static frontend serving, and the `tearose` console entry point."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from tearose import __version__
from tearose.agent.engine import AnalysisEngine
from tearose.agent.runs import RunStore
from tearose.api import auth, limits, routes_analyze, routes_samples, showcase
from tearose.api.auth import LoginGuard, SessionSigner
from tearose.api.context import ApiContext
from tearose.api.limits import (
    RateLimitMiddleware,
    RequestLogMiddleware,
    RunCaps,
    TokenBucketLimiter,
)
from tearose.config import Settings, get_settings

log = logging.getLogger("tearose.api")


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA: real files when they exist, otherwise index.html."""
    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        if full_path:
            candidate = (root / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        if not index.is_file():
            raise HTTPException(status_code=404, detail="Frontend not built.")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app(
    settings: Settings | None = None,
    engine: AnalysisEngine | None = None,
    store: RunStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if settings.session_secret == "change-me" and settings.passcode:
        log.warning("SESSION_SECRET is the default; set a random value before going live")

    ctx = ApiContext(
        settings=settings,
        store=store if store is not None else RunStore(settings.runs_dir),
        signer=SessionSigner(settings.session_secret, settings.session_ttl_hours * 3600),
        login_guard=LoginGuard(settings.login_max_failures, settings.login_lockout_minutes * 60),
        caps=RunCaps(settings.cap_live_runs_per_day, settings.cap_live_runs_per_session),
        engine=engine,
    )
    ctx.showcase = showcase.load_showcase(settings.showcase_dir)
    ctx.showcase_summaries = [showcase.summarize(s, r) for s, r in ctx.showcase.items()]

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for task in list(ctx.tasks):
            task.cancel()
        if ctx.tasks:
            await asyncio.gather(*ctx.tasks, return_exceptions=True)

    app = FastAPI(title="Tea Rose", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx

    # add_middleware wraps outward: the last one added runs first.
    limiter = TokenBucketLimiter(settings.rate_limit_per_minute)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    app.add_middleware(RequestLogMiddleware)

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.qloo_mode, "version": __version__}

    app.include_router(showcase.router)
    app.include_router(routes_samples.router)
    app.include_router(auth.router)
    app.include_router(limits.router)
    app.include_router(routes_analyze.router)

    if settings.frontend_dist.is_dir():
        _mount_frontend(app, settings.frontend_dist)
    else:

        @app.get("/", include_in_schema=False)
        async def root(request: Request) -> dict[str, str]:
            return {"name": "Tea Rose API", "health": "/api/health", "docs": "/docs"}

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    uvicorn.run(
        "tearose.api.app:app",
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        workers=1,  # in-memory runs, caps and rate limits require a single process
    )


app = create_app()
