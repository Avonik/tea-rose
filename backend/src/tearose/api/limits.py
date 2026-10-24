"""Abuse and budget protection: per-IP rate limiting and live-run caps.

Everything is in memory: the app runs as a single uvicorn worker on the Pi.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import orjson
from fastapi import APIRouter, Request
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("tearose.api")

# The app runs behind a reverse proxy on the Pi, so request.client.host is the proxy. We take the
# hop the proxy itself appended to X-Forwarded-For (the right-most entry): left-most entries are
# supplied by the client and can be spoofed. Set to False when exposing uvicorn directly.
TRUST_X_FORWARDED_FOR = True


def client_ip(scope: Scope) -> str:
    if TRUST_X_FORWARDED_FOR:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                hops = [h.strip() for h in value.decode("latin-1").split(",") if h.strip()]
                if hops:
                    return hops[-1]
    client = scope.get("client")
    return client[0] if client else "unknown"


class TokenBucketLimiter:
    """One bucket per key; capacity = per-minute limit, refilled continuously."""

    MAX_KEYS = 10_000

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(max(per_minute, 1))
        self.rate = self.capacity / 60.0  # tokens per second
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)

    def hit(self, key: str) -> float | None:
        """Consume one token. Returns None when allowed, else seconds until the next token."""
        now = self._clock()
        tokens, last = self._buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        if tokens >= 1.0:
            self._buckets[key] = (tokens - 1.0, now)
            if len(self._buckets) > self.MAX_KEYS:
                self._prune(now)
            return None
        self._buckets[key] = (tokens, now)
        return (1.0 - tokens) / self.rate

    def _prune(self, now: float) -> None:
        full_after = self.capacity / self.rate
        self._buckets = {k: v for k, v in self._buckets.items() if now - v[1] < full_after}


class RateLimitMiddleware:
    """Pure ASGI middleware (does not buffer SSE streams) limiting /api/* per client IP."""

    def __init__(self, app: ASGIApp, limiter: TokenBucketLimiter, prefix: str = "/api") -> None:
        self.app = app
        self.limiter = limiter
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        wait = self.limiter.hit(client_ip(scope))
        if wait is None:
            await self.app(scope, receive, send)
            return
        retry = str(max(1, math.ceil(wait)))
        body = orjson.dumps({"detail": "Too many requests, slow down.", "kind": "rate_limit"})
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", retry.encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


class RequestLogMiddleware:
    """One log line per request: method, path, status, duration, client ip."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def _send(message: dict) -> None:  # type: ignore[type-arg]
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                ms = (time.perf_counter() - start) * 1000
                log.info("%s %s %d %.0fms ip=%s", scope["method"], scope["path"], status, ms,
                         client_ip(scope))
            await send(message)

        await self.app(scope, receive, _send)


class RunCaps:
    """Live-run budget: a global counter per UTC day plus a counter per session."""

    def __init__(
        self,
        daily_cap: int,
        session_cap: int,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        self.daily_cap = daily_cap
        self.session_cap = session_cap
        self._today = today
        self._day = today()
        self._daily_used = 0
        self._per_session: dict[str, int] = {}

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._daily_used = 0

    @property
    def daily_used(self) -> int:
        self._roll()
        return self._daily_used

    def runs_left_today(self) -> int:
        return max(0, self.daily_cap - self.daily_used)

    def runs_left_session(self, session_id: str) -> int:
        return max(0, self.session_cap - self._per_session.get(session_id, 0))

    def seconds_until_reset(self) -> int:
        now = datetime.now(UTC)
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
        return max(1, int((midnight - now).total_seconds()))

    def try_consume(self, session_id: str) -> str | None:
        """Count one run. Returns None on success, else a user-facing reason."""
        if self.runs_left_today() <= 0:
            return (f"The daily budget of {self.daily_cap} live analyses is used up. "
                    "Please come back tomorrow (UTC) or explore the showcase cases.")
        if self.runs_left_session(session_id) <= 0:
            return (f"This session has used all {self.session_cap} live analyses. "
                    "The showcase cases remain available.")
        self._daily_used += 1
        self._per_session[session_id] = self._per_session.get(session_id, 0) + 1
        return None


# --- public cap status ------------------------------------------------------------------------


router = APIRouter(prefix="/api", tags=["limits"])


@router.get("/limits")
async def limits(request: Request) -> dict[str, object]:
    ctx = request.app.state.ctx
    return {
        "daily_cap": ctx.caps.daily_cap,
        "daily_used": ctx.caps.daily_used,
        "session_cap": ctx.caps.session_cap,
        "live_mode_enabled": bool(ctx.settings.passcode),
    }
