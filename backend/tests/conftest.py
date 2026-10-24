"""Shared pytest configuration.

`@pytest.mark.llm` tests (real language model) run only with `--run-llm`;
`@pytest.mark.live` tests (live Qloo API) run only with `--run-live`.
"""

from __future__ import annotations

import pytest

_GATED = {"llm": "--run-llm", "live": "--run-live"}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-llm", action="store_true", default=False, help="run tests that call a real LLM"
    )
    parser.addoption(
        "--run-live", action="store_true", default=False, help="run tests against live Qloo"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for marker, option in _GATED.items():
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason=f"needs {option}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)
