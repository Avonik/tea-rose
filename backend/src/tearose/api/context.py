"""Per-app state shared by the routers, stored on `app.state.ctx`."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import Request

from tearose.agent.engine import AnalysisEngine
from tearose.agent.runs import RunStore
from tearose.api.auth import LoginGuard, SessionSigner
from tearose.api.limits import RunCaps
from tearose.config import Settings
from tearose.schemas import AnalysisResult, ShowcaseSummary


@dataclass
class ApiContext:
    settings: Settings
    store: RunStore
    signer: SessionSigner
    login_guard: LoginGuard
    caps: RunCaps
    engine: AnalysisEngine | None = None  # resolved lazily via get_engine() when None
    showcase: dict[str, AnalysisResult] = field(default_factory=dict)
    showcase_summaries: list[ShowcaseSummary] = field(default_factory=list)
    run_owners: dict[str, str] = field(default_factory=dict)  # run_id -> session id
    tasks: set[asyncio.Task[None]] = field(default_factory=set)  # keep background runs alive


def get_ctx(request: Request) -> ApiContext:
    return request.app.state.ctx
