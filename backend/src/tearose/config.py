"""Application settings. Everything configurable lives here and is read from env / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Qloo ---------------------------------------------------------------
    qloo_mode: Literal["fixture", "live"] = "fixture"
    qloo_api_key: str = ""
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    qloo_timeout_s: float = 20.0
    qloo_max_rps: float = 4.0  # client-side token bucket; tune after the live test
    qloo_cache_path: Path = BACKEND_DIR / "data" / "cache" / "qloo_cache.sqlite"
    qloo_record_raw_dir: Path | None = BACKEND_DIR / "data" / "live"  # raw responses, gitignored
    fixtures_dir: Path = BACKEND_DIR / "fixtures" / "qloo"

    # --- LLM (OpenAI-compatible) ------------------------------------------------
    llm_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    llm_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    llm_model: str = "gpt-5-mini"
    llm_model_strong: str | None = None  # optional stronger model for the interpret step
    llm_temperature: float | None = None  # None = provider default (gpt-5 rejects explicit values)
    # reasoning models: low | medium | high, sent as reasoning_effort; None = provider default.
    # A provider that rejects the parameter gets one retry without it (noted in the trace).
    llm_reasoning_effort: str | None = None
    # USD per million tokens, for the cost line in the trace and the result (None = tokens only).
    llm_price_input_per_m: float | None = None
    llm_price_cached_input_per_m: float | None = None  # falls back to the input price
    llm_price_output_per_m: float | None = None

    # --- Access control and budget protection -----------------------------------
    passcode: str = ""  # live mode is disabled when empty
    session_secret: str = "change-me"
    session_ttl_hours: int = 12
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    cap_live_runs_per_day: int = 60
    cap_live_runs_per_session: int = 15
    rate_limit_per_minute: int = 60  # per IP, all API routes

    # --- Paths ------------------------------------------------------------------
    data_dir: Path = BACKEND_DIR / "data"
    samples_dir: Path = BACKEND_DIR / "data" / "samples"
    showcase_dir: Path = BACKEND_DIR / "data" / "showcase"  # pre-computed results (committed)
    runs_dir: Path = BACKEND_DIR / "data" / "runs"  # live run results (gitignored)
    frontend_dist: Path = REPO_DIR / "frontend" / "dist"

    # --- Server -----------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]
    secure_cookies: bool = True  # set False only for plain-http local dev


@lru_cache
def get_settings() -> Settings:
    return Settings()
