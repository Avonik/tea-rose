"""SQLite cache for raw Qloo responses, keyed by endpoint + canonical params.

Qloo allows private server-side caching without a time limit. The cache file lives under
backend/data/cache/ and is gitignored. Never commit it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def cache_key(endpoint: str, params: dict[str, Any]) -> str:
    canon = json.dumps({"e": endpoint, "p": params}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


class ResponseCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS responses (
                   key TEXT PRIMARY KEY,
                   endpoint TEXT NOT NULL,
                   params TEXT NOT NULL,
                   status INTEGER NOT NULL,
                   body TEXT NOT NULL,
                   created_at REAL NOT NULL
               )"""
        )
        self._conn.commit()

    def get(self, endpoint: str, params: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
        row = self._conn.execute(
            "SELECT status, body FROM responses WHERE key = ?", (cache_key(endpoint, params),)
        ).fetchone()
        if row is None:
            return None
        return int(row[0]), json.loads(row[1])

    def put(self, endpoint: str, params: dict[str, Any], status: int, body: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?, ?)",
            (
                cache_key(endpoint, params),
                endpoint,
                json.dumps(params, sort_keys=True),
                status,
                json.dumps(body),
                time.time(),
            ),
        )
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
