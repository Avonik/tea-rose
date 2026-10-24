"""In-memory run registry shared by the API (reads, streams) and the engine (writes).

Single-process by design (one uvicorn worker on the Pi). Finished live runs are also persisted
to settings.runs_dir as JSON so a restart does not lose them.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from pathlib import Path

from tearose.schemas import AnalysisResult, RunStatus, TraceEvent


class RunHandle:
    """One analysis run: its evolving result plus an event stream."""

    def __init__(self, result: AnalysisResult, persist_dir: Path | None = None) -> None:
        self.result = result
        self._cond = asyncio.Condition()
        self._persist_dir = persist_dir

    @property
    def run_id(self) -> str:
        return self.result.run_id

    async def emit(self, event: TraceEvent) -> TraceEvent:
        async with self._cond:
            event.seq = len(self.result.trace) + 1
            self.result.trace.append(event)
            self._cond.notify_all()
        return event

    async def set_status(self, status: RunStatus, error: str | None = None) -> None:
        async with self._cond:
            self.result.status = status
            if error:
                self.result.error = error
            self._cond.notify_all()
        if status in ("finished", "failed"):
            self.persist()

    async def events(self, after_seq: int = 0) -> AsyncIterator[TraceEvent]:
        """Replay events after `after_seq`, then yield live ones until the run ends."""
        idx = after_seq
        while True:
            async with self._cond:
                while idx >= len(self.result.trace) and self.result.status in ("queued", "running"):
                    await self._cond.wait()
                batch = self.result.trace[idx:]
                idx = len(self.result.trace)
                done = self.result.status in ("finished", "failed")
            for ev in batch:
                yield ev
            if done and idx >= len(self.result.trace):
                return

    def persist(self) -> None:
        if not self._persist_dir or self.result.showcase_slug:
            return
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        path = self._persist_dir / f"{self.run_id}.json"
        path.write_text(self.result.model_dump_json(indent=2), encoding="utf-8")


class RunStore:
    def __init__(self, persist_dir: Path | None = None) -> None:
        self._runs: dict[str, RunHandle] = {}
        self._persist_dir = persist_dir

    def create(self, result: AnalysisResult) -> RunHandle:
        handle = RunHandle(result, self._persist_dir)
        self._runs[result.run_id] = handle
        return handle

    def get(self, run_id: str) -> RunHandle | None:
        h = self._runs.get(run_id)
        if h is None and self._persist_dir:
            path = self._persist_dir / f"{run_id}.json"
            if path.exists():
                res = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
                h = self.create(res)
        return h

    def __len__(self) -> int:
        return len(self._runs)

    @staticmethod
    def new_run_id() -> str:
        return secrets.token_urlsafe(9)


def load_result(path: Path) -> AnalysisResult:
    return AnalysisResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
