"""Passcode login, signed session cookie, per-IP lockout, and the `require_session` dependency.

Sessions are stateless: the cookie carries a signed random session id (itsdangerous). The server
only keeps per-session run counters (RunCaps), run ownership and a small revocation list.
"""

from __future__ import annotations

import logging
import math
import secrets
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field

from tearose.api.limits import client_ip

if TYPE_CHECKING:
    from tearose.api.context import ApiContext

log = logging.getLogger("tearose.api")

COOKIE_NAME = "tearose_session"
_SALT = "tearose-session-v1"


class SessionSigner:
    def __init__(self, secret: str, ttl_s: int, clock: Callable[[], float] = time.time) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)
        self.ttl_s = ttl_s
        self._clock = clock
        self._revoked: dict[str, float] = {}  # session id -> expiry of the revocation entry

    def issue(self) -> tuple[str, str]:
        sid = secrets.token_urlsafe(18)
        return sid, self._serializer.dumps({"sid": sid})

    def verify(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            data = self._serializer.loads(token, max_age=self.ttl_s)
        except BadSignature:  # includes SignatureExpired
            return None
        sid = data.get("sid") if isinstance(data, dict) else None
        if not isinstance(sid, str) or sid in self._revoked:
            return None
        return sid

    def revoke(self, sid: str) -> None:
        now = self._clock()
        self._revoked = {k: exp for k, exp in self._revoked.items() if exp > now}
        self._revoked[sid] = now + self.ttl_s


class LoginGuard:
    """Per-IP failure counter: `max_failures` failures within the window lock the IP out."""

    def __init__(
        self, max_failures: int, lockout_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_failures = max_failures
        self.lockout_s = lockout_s
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}

    def retry_after(self, ip: str) -> int | None:
        until = self._locked_until.get(ip)
        if until is None:
            return None
        remaining = until - self._clock()
        if remaining <= 0:
            del self._locked_until[ip]
            return None
        return max(1, math.ceil(remaining))

    def record_failure(self, ip: str) -> None:
        now = self._clock()
        q = self._failures.setdefault(ip, deque())
        while q and now - q[0] > self.lockout_s:
            q.popleft()
        q.append(now)
        if len(q) >= self.max_failures:
            self._locked_until[ip] = now + self.lockout_s
            del self._failures[ip]
            log.warning("login lockout for ip=%s", ip)

    def record_success(self, ip: str) -> None:
        self._failures.pop(ip, None)


def _ctx(request: Request) -> ApiContext:
    return request.app.state.ctx


def current_session(request: Request) -> str | None:
    return _ctx(request).signer.verify(request.cookies.get(COOKIE_NAME))


def require_session(request: Request) -> str:
    """FastAPI dependency: the caller's session id, or 401."""
    sid = current_session(request)
    if sid is None:
        raise HTTPException(status_code=401, detail="Not authenticated. Enter the passcode first.")
    return sid


class LoginBody(BaseModel):
    passcode: str = Field(max_length=256)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginBody, request: Request) -> Response:
    ctx = _ctx(request)
    settings = ctx.settings
    if not settings.passcode:
        raise HTTPException(status_code=503, detail="live mode disabled")
    ip = client_ip(request.scope)
    retry = ctx.login_guard.retry_after(ip)
    if retry is not None:
        return JSONResponse(
            {"detail": "Too many failed attempts. Try again later.", "kind": "lockout"},
            status_code=429,
            headers={"Retry-After": str(retry)},
        )
    ok = secrets.compare_digest(body.passcode.encode(), settings.passcode.encode())
    if not ok:
        ctx.login_guard.record_failure(ip)
        raise HTTPException(status_code=401, detail="Wrong passcode.")
    ctx.login_guard.record_success(ip)
    sid, token = ctx.signer.issue()
    resp = JSONResponse({
        "authenticated": True,
        "runs_left_today": ctx.caps.runs_left_today(),
        "runs_left_session": ctx.caps.runs_left_session(sid),
    })
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )
    log.info("login ok ip=%s", ip)
    return resp


@router.post("/logout")
async def logout(request: Request) -> Response:
    ctx = _ctx(request)
    sid = current_session(request)
    if sid is not None:
        ctx.signer.revoke(sid)
    resp = JSONResponse({"authenticated": False})
    resp.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=ctx.settings.secure_cookies
    )
    return resp


@router.get("/me")
async def me(request: Request) -> dict[str, object]:
    ctx = _ctx(request)
    sid = current_session(request)
    return {
        "authenticated": sid is not None,
        "runs_left_today": ctx.caps.runs_left_today(),
        "runs_left_session": ctx.caps.runs_left_session(sid) if sid is not None else None,
    }
