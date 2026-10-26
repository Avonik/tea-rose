"""HTTP API tests: httpx AsyncClient over ASGITransport, ScriptedEngine, temp data dirs."""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pypdf import PdfWriter

from tearose.agent.engine import ScriptedEngine
from tearose.agent.runs import RunHandle, RunStore
from tearose.api.app import create_app
from tearose.api.showcase import summarize
from tearose.config import Settings
from tearose.schemas import AnalysisResult, Extraction, Memo, Party, PreliminaryRead

PASSCODE = "open-sesame"
TIMEOUT_S = 5.0

ClientFactory = Callable[..., Any]


# --- fixtures ----------------------------------------------------------------------------------


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    def _make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "passcode": PASSCODE,
            "session_secret": "test-secret",
            "secure_cookies": False,
            "rate_limit_per_minute": 10_000,
            "showcase_dir": tmp_path / "showcase",
            "samples_dir": tmp_path / "samples",
            "runs_dir": tmp_path / "runs",
            "frontend_dist": tmp_path / "no-dist",
            "qloo_mode": "fixture",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return _make


@asynccontextmanager
async def client_for(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def make_app(make_settings: Callable[..., Settings]) -> Callable[..., FastAPI]:
    def _make(engine: Any = None, **overrides: Any) -> FastAPI:
        settings = make_settings(**overrides)
        return create_app(
            settings=settings,
            engine=engine or ScriptedEngine(delay_s=0),
            store=RunStore(settings.runs_dir),
        )

    return _make


async def login(client: httpx.AsyncClient, passcode: str = PASSCODE) -> httpx.Response:
    return await client.post("/api/auth/login", json={"passcode": passcode})


async def wait_status(
    client: httpx.AsyncClient, run_id: str, statuses: tuple[str, ...] = ("finished", "failed")
) -> dict[str, Any]:
    async def _poll() -> dict[str, Any]:
        while True:
            body = (await client.get(f"/api/analyze/{run_id}")).json()
            if body["status"] in statuses:
                return body
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(_poll(), TIMEOUT_S)


def parse_sse(raw: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        ev: dict[str, str] = {}
        for line in block.split("\n"):
            if not line or line.startswith(":"):
                continue
            key, _, value = line.partition(":")
            ev[key] = value.removeprefix(" ")
        if "event" in ev or "data" in ev:
            events.append(ev)
    return events


async def read_events(client: httpx.AsyncClient, run_id: str, after: int = 0) -> list[dict]:
    async def _read() -> str:
        async with client.stream("GET", f"/api/analyze/{run_id}/events?after={after}") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            return "".join([chunk async for chunk in resp.aiter_text()])

    return parse_sse(await asyncio.wait_for(_read(), TIMEOUT_S))


def pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# --- health, root, static ------------------------------------------------------------------------


async def test_health(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        r = await c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "fixture"
    assert body["version"]


async def test_root_without_frontend_points_to_health(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        r = await c.get("/")
    assert r.status_code == 200
    assert r.json()["health"] == "/api/health"


async def test_spa_fallback(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>tea rose</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    async with client_for(make_app(frontend_dist=dist)) as c:
        index = await c.get("/run/abc123")
        asset = await c.get("/assets/app.js")
        api_missing = await c.get("/api/does-not-exist")
        health = await c.get("/api/health")
        escape = await c.get("/%2E%2E/secret.txt")
    assert index.status_code == 200 and "tea rose" in index.text
    assert asset.status_code == 200 and "console.log" in asset.text
    assert api_missing.status_code == 404
    assert health.json()["status"] == "ok"
    assert "nope" not in escape.text


# --- showcase ------------------------------------------------------------------------------------


def _showcase_result() -> AnalysisResult:
    return AnalysisResult(
        run_id="showcase-jd",
        status="finished",
        mode="fixture",
        input_excerpt="Complaint ...",
        extraction=Extraction(
            document_type="opinion",
            title="Jack Daniel's Properties, Inc. v. VIP Products LLC (2023)",
            senior=Party(side="senior", name="Jack Daniel's"),
            junior=Party(side="junior", name="VIP Products"),
            claims=["likelihood_of_confusion", "dilution"],
            summary="Parody dog toy.",
        ),
        memo=Memo(
            headline="Whiskey buyers barely overlap with dog-toy buyers.",
            findings=[],
            sections=[],
            limitations=[],
            appendix_queries=[],
        ),
    )


async def test_showcase_list_and_detail(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    showcase = tmp_path / "showcase"
    showcase.mkdir()
    (showcase / "jack-daniels.json").write_text(_showcase_result().model_dump_json(), "utf-8")
    (showcase / "broken.json").write_text("{not json", encoding="utf-8")
    async with client_for(make_app()) as c:
        listing = await c.get("/api/showcase")
        detail = await c.get("/api/showcase/jack-daniels")
        missing = await c.get("/api/showcase/nope")
    assert listing.status_code == 200
    [summary] = listing.json()
    assert summary["slug"] == "jack-daniels"
    assert summary["parties"] == "Jack Daniel's v. VIP Products"
    assert summary["one_liner"].startswith("Whiskey buyers")
    assert summary["year"] == 2023
    assert "dilution" in summary["tags"]
    assert detail.status_code == 200
    assert detail.json()["showcase_slug"] == "jack-daniels"
    assert missing.status_code == 404


def test_showcase_summary_carries_the_read() -> None:
    res = _showcase_result()
    assert res.memo is not None
    res.memo.preliminary_read = PreliminaryRead(
        lean="newcomer",
        confidence="medium",
        turns_on="The case most likely turns on the parody defence.",
        rationale="Data half. Reading half.",
        best_defence="Parody.",
        one_sided_input=True,
    )
    s = summarize("jack-daniels", res)
    assert (s.read_lean, s.read_confidence, s.read_one_sided) == ("newcomer", "medium", True)
    assert s.read_turns_on == "The case most likely turns on the parody defence."
    assert s.read_best_defence == "Parody."


async def test_showcase_missing_dir_is_empty(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        r = await c.get("/api/showcase")
    assert r.status_code == 200
    assert r.json() == []


# --- samples -------------------------------------------------------------------------------------


async def test_samples_listing_and_text(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    samples = tmp_path / "samples"
    samples.mkdir()
    text = "source: PACER\ncase: 1:23-cv-1\nretrieved: 2026-10-01\n\nCOMPLAINT FOR X\n..."
    (samples / "acme.txt").write_bytes(text.encode())
    (samples / "notes.env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    async with client_for(make_app()) as c:
        listing = await c.get("/api/samples")
        one = await c.get("/api/samples/acme")
        with_ext = await c.get("/api/samples/acme.txt")
        not_txt = await c.get("/api/samples/notes.env")
        traversal = await c.get("/api/samples/..%2Foutside")
        traversal2 = await c.get("/api/samples/%2E%2E%2Foutside.txt")
    assert listing.json() == [
        {"name": "acme", "title": "COMPLAINT FOR X", "bytes": len(text.encode())}
    ]
    assert one.status_code == 200
    assert one.headers["content-type"].startswith("text/plain")
    assert one.text == text
    assert with_ext.status_code == 200
    assert not_txt.status_code == 404
    assert traversal.status_code == 404
    assert traversal2.status_code == 404


# --- auth ----------------------------------------------------------------------------------------


async def test_login_sets_cookie_and_me(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(secure_cookies=True)) as c:
        before = (await c.get("/api/auth/me")).json()
        r = await login(c)
    assert before["authenticated"] is False
    assert before["runs_left_session"] is None
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("tearose_session=")
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=lax" in lowered and "secure" in lowered
    assert "max-age=43200" in lowered


async def test_me_and_logout(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(cap_live_runs_per_session=4)) as c:
        await login(c)
        me = (await c.get("/api/auth/me")).json()
        token = c.cookies.get("tearose_session")
        out = await c.post("/api/auth/logout")
        after = (await c.get("/api/auth/me")).json()
        # a replayed cookie from before logout is rejected too
        c.cookies.set("tearose_session", token)
        replay = await c.post("/api/analyze", json={"text": "x"})
    assert me == {"authenticated": True, "runs_left_today": 60, "runs_left_session": 4}
    assert out.status_code == 200
    assert after["authenticated"] is False
    assert replay.status_code == 401


async def test_wrong_passcode_401(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        r = await login(c, "wrong")
    assert r.status_code == 401
    assert "tearose_session" not in r.headers.get("set-cookie", "")


async def test_tampered_cookie_rejected(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        c.cookies.set("tearose_session", "forged.token.value")
        r = await c.post("/api/analyze", json={"text": "hello"})
    assert r.status_code == 401


async def test_lockout_after_failures(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(login_max_failures=3, login_lockout_minutes=15)) as c:
        codes = [(await login(c, "nope")).status_code for _ in range(3)]
        locked = await login(c, "nope")
        locked_even_if_correct = await login(c)
        other_ip = await c.post(
            "/api/auth/login", json={"passcode": PASSCODE},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
    assert codes == [401, 401, 401]
    assert locked.status_code == 429
    assert 0 < int(locked.headers["retry-after"]) <= 15 * 60
    assert locked_even_if_correct.status_code == 429
    assert other_ip.status_code == 200


async def test_empty_passcode_disables_live_mode(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(passcode="")) as c:
        r = await login(c, "")
        limits = (await c.get("/api/limits")).json()
    assert r.status_code == 503
    assert r.json()["detail"] == "live mode disabled"
    assert limits["live_mode_enabled"] is False


# --- analyze -------------------------------------------------------------------------------------


async def test_analyze_requires_session(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        post = await c.post("/api/analyze", json={"text": "hello"})
        get = await c.get("/api/analyze/abc")
        events = await c.get("/api/analyze/abc/events")
        follow = await c.post("/api/analyze/abc/followup", json={"question": "why?"})
    assert [post.status_code, get.status_code, events.status_code, follow.status_code] == [
        401, 401, 401, 401
    ]


async def test_analyze_happy_path_and_events(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        await login(c)
        r = await c.post("/api/analyze", json={"text": "  COMPLAINT. Jack Daniel's v. VIP.  "})
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        result = await wait_status(c, run_id)
        events = await read_events(c, run_id)
        tail = await read_events(c, run_id, after=len(result["trace"]) - 2)
        limits = (await c.get("/api/limits")).json()
    assert result["status"] == "finished"
    assert result["input_excerpt"] == "COMPLAINT. Jack Daniel's v. VIP."
    assert result["memo"]["headline"]
    # the preliminary read serialises with the memo (scripted engine)
    assert result["memo"]["read_line"].startswith("Preliminary read: leans toward VIP Products")
    read = result["memo"]["preliminary_read"]
    assert read["lean"] == "newcomer" and read["not_a_prediction"].startswith("A preliminary")
    assert [s["id"] for s in result["memo"]["sections"]][:2] == ["summary", "read"]
    trace = [e for e in events if e["event"] == "trace"]
    assert len(trace) >= 5
    first = json.loads(trace[0]["data"])
    assert first["seq"] == 1 and trace[0]["id"] == "1"
    assert [int(e["id"]) for e in trace] == list(range(1, len(trace) + 1))
    assert events[-1]["event"] == "done"
    assert json.loads(events[-1]["data"])["status"] == "finished"
    assert [e["event"] for e in tail] == ["trace", "trace", "done"]
    assert limits["daily_used"] == 1


async def test_events_stream_live_run(make_app: Callable[..., FastAPI]) -> None:
    """Open the stream while the run is still in progress; it must deliver everything."""
    async with client_for(make_app(engine=ScriptedEngine(delay_s=0.02))) as c:
        await login(c)
        run_id = (await c.post("/api/analyze", json={"text": "doc"})).json()["run_id"]
        events = await read_events(c, run_id)
    assert sum(e["event"] == "trace" for e in events) >= 5
    assert events[-1]["event"] == "done"


async def test_analyze_unknown_and_foreign_runs(make_app: Callable[..., FastAPI]) -> None:
    app = make_app()
    async with client_for(app) as alice, client_for(app) as bob:
        await login(alice)
        await login(bob)
        run_id = (await alice.post("/api/analyze", json={"text": "doc"})).json()["run_id"]
        await wait_status(alice, run_id)
        unknown = await alice.get("/api/analyze/nope")
        foreign = await bob.get(f"/api/analyze/{run_id}")
        foreign_events = await bob.get(f"/api/analyze/{run_id}/events")
        foreign_follow = await bob.post(
            f"/api/analyze/{run_id}/followup", json={"question": "why?"}
        )
    assert unknown.status_code == 404
    assert foreign.status_code == 403
    assert foreign_events.status_code == 403
    assert foreign_follow.status_code == 403


async def test_followup(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        await login(c)
        run_id = (await c.post("/api/analyze", json={"text": "doc"})).json()["run_id"]
        done = await wait_status(c, run_id)
        seen = len(done["trace"])
        r = await c.post(f"/api/analyze/{run_id}/followup", json={"question": "Use whiskey tags"})
        assert r.status_code == 202 and r.json() == {"run_id": run_id}
        await asyncio.sleep(0)  # let the follow-up task start
        after = await wait_status(c, run_id)
        new = await read_events(c, run_id, after=seen)
    assert len(after["trace"]) > seen
    assert any(json.loads(e["data"])["node"] == "followup" for e in new if e["event"] == "trace")


async def test_session_cap(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(cap_live_runs_per_session=1)) as c:
        await login(c)
        first = await c.post("/api/analyze", json={"text": "doc one"})
        second = await c.post("/api/analyze", json={"text": "doc two"})
        me = (await c.get("/api/auth/me")).json()
    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["kind"] == "cap"
    assert second.json()["detail"]
    assert "retry-after" in second.headers
    assert me["runs_left_session"] == 0


async def test_daily_cap(make_app: Callable[..., FastAPI]) -> None:
    app = make_app(cap_live_runs_per_day=1)
    async with client_for(app) as a, client_for(app) as b:
        await login(a)
        await login(b)
        assert (await a.post("/api/analyze", json={"text": "doc"})).status_code == 202
        blocked = await b.post("/api/analyze", json={"text": "doc"})
        limits = (await b.get("/api/limits")).json()
    assert blocked.status_code == 429 and blocked.json()["kind"] == "cap"
    assert limits == {
        "daily_cap": 1, "daily_used": 1, "session_cap": 15, "live_mode_enabled": True
    }


async def test_invalid_input_does_not_consume_cap(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(cap_live_runs_per_session=1)) as c:
        await login(c)
        empty = await c.post("/api/analyze", json={"text": "   "})
        bad = await c.post("/api/analyze", json={"nope": 1})
        ok = await c.post("/api/analyze", json={"text": "real text"})
    assert empty.status_code == 400
    assert bad.status_code == 422
    assert ok.status_code == 202


async def test_engine_failure_marks_run_failed(make_app: Callable[..., FastAPI]) -> None:
    class Boom:
        async def run(self, handle: RunHandle, text: str) -> None:
            await handle.set_status("running")
            raise RuntimeError("qloo exploded")

        async def followup(self, handle: RunHandle, question: str) -> None:
            raise NotImplementedError

    async with client_for(make_app(engine=Boom())) as c:
        await login(c)
        run_id = (await c.post("/api/analyze", json={"text": "doc"})).json()["run_id"]
        result = await wait_status(c, run_id)
        events = await read_events(c, run_id)
    assert result["status"] == "failed"
    assert "qloo exploded" in result["error"]
    assert json.loads(events[-1]["data"])["status"] == "failed"


# --- uploads -------------------------------------------------------------------------------------


async def test_upload_txt(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        await login(c)
        files = {"file": ("complaint.txt", b"COMPLAINT\nAcme v. Widget", "text/plain")}
        r = await c.post("/api/analyze", files=files)
        assert r.status_code == 202
        result = await wait_status(c, r.json()["run_id"])
    assert result["input_excerpt"].startswith("COMPLAINT")


async def test_upload_pdf_without_text_rejected(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        await login(c)
        files = {"file": ("scan.pdf", pdf_bytes(), "application/pdf")}
        r = await c.post("/api/analyze", files=files)
    assert r.status_code == 400
    assert "text" in r.json()["detail"].lower()


async def test_upload_corrupt_pdf_and_wrong_type(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        await login(c)
        corrupt = await c.post(
            "/api/analyze", files={"file": ("x.pdf", b"%PDF-1.7 garbage", "application/pdf")}
        )
        docx = await c.post("/api/analyze", files={"file": ("x.docx", b"PK\x03\x04", "x/y")})
        missing = await c.post("/api/analyze", files={"other": ("a.txt", b"hi", "text/plain")})
    assert corrupt.status_code == 400
    assert docx.status_code == 415
    assert missing.status_code == 400


async def test_upload_too_large(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app()) as c:
        await login(c)
        big = b"a" * (2 * 1024 * 1024 + 1)
        upload = await c.post("/api/analyze", files={"file": ("big.txt", big, "text/plain")})
        as_json = await c.post("/api/analyze", json={"text": big.decode()})
    assert upload.status_code == 413
    assert as_json.status_code == 413


# --- rate limiting -------------------------------------------------------------------------------


async def test_rate_limit(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(rate_limit_per_minute=3)) as c:
        codes = [(await c.get("/api/health")).status_code for _ in range(4)]
        limited = await c.get("/api/health")
        other_ip = await c.get("/api/health", headers={"X-Forwarded-For": "198.51.100.7"})
        non_api = await c.get("/")
    assert codes == [200, 200, 200, 429]
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["kind"] == "rate_limit"
    assert other_ip.status_code == 200
    assert non_api.status_code == 200


async def test_cors_preflight(make_app: Callable[..., FastAPI]) -> None:
    async with client_for(make_app(cors_origins=["http://localhost:5173"])) as c:
        r = await c.options(
            "/api/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers["access-control-allow-credentials"] == "true"
