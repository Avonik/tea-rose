"""Shared pytest configuration.

`@pytest.mark.llm` tests (real language model) run only with `--run-llm`;
`@pytest.mark.live` tests (live Qloo API) run only with `--run-live`.

Safety: backend/.env may hold QLOO_MODE=live and real keys. Process env vars take precedence
over .env in pydantic-settings, so unless `--run-live` / `--run-llm` is given we pin fixture
mode and blank both API keys in `pytest_configure` (before any test module or app factory reads
Settings) and again per test, clearing the cached Settings each time.
"""

from __future__ import annotations

import os

import pytest

_GATED = {"llm": "--run-llm", "live": "--run-live"}
FORCED_ENV = {"QLOO_MODE": "fixture", "QLOO_API_KEY": "", "OPENAI_API_KEY": ""}


def _gated_run(config: pytest.Config) -> bool:
    return any(config.getoption(opt) for opt in _GATED.values())


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-llm", action="store_true", default=False, help="run tests that call a real LLM"
    )
    parser.addoption(
        "--run-live", action="store_true", default=False, help="run tests against live Qloo"
    )


def pytest_configure(config: pytest.Config) -> None:
    if not _gated_run(config):
        os.environ.update(FORCED_ENV)


@pytest.fixture(autouse=True)
def _force_fixture_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    from tearose.config import get_settings

    if not _gated_run(request.config):
        for k, v in FORCED_ENV.items():
            monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for marker, option in _GATED.items():
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason=f"needs {option}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)
