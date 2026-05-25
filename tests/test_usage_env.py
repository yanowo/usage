from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from usage_env import env_bool, env_choice, env_int, env_int_first, env_str, load_dotenv


def test_load_dotenv_sets_missing_values_without_overriding(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("USAGE_WEB_PORT", "9999")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "USAGE_WEB_HOST=0.0.0.0",
                "USAGE_WEB_PORT=8765",
                'USAGE_MODE="web"',
                "export USAGE_INTERVAL=90",
            ]
        ),
        encoding="utf-8",
    )

    load_dotenv([env_path])

    assert os.environ["USAGE_WEB_HOST"] == "0.0.0.0"
    assert os.environ["USAGE_WEB_PORT"] == "9999"
    assert os.environ["USAGE_MODE"] == "web"
    assert os.environ["USAGE_INTERVAL"] == "90"


def test_env_helpers_parse_values(monkeypatch: Any) -> None:
    monkeypatch.setenv("USAGE_MOCK", "yes")
    monkeypatch.setenv("USAGE_MODE", "desktop")
    monkeypatch.setenv("USAGE_INTERVAL", "120")
    monkeypatch.setenv("USAGE_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("USAG_FORCE_GROUP", "2")

    assert env_bool("USAGE_MOCK") is True
    assert env_choice("USAGE_MODE", {"web", "desktop", "tui"}, "") == "desktop"
    assert env_int("USAGE_INTERVAL", 60, min_value=30) == 120
    assert env_str("USAGE_WEB_HOST", "127.0.0.1") == "0.0.0.0"
    assert env_int_first(("USAGE_FORCE_GROUP", "USAG_FORCE_GROUP"), None) == 2


def test_env_helpers_fall_back_on_invalid_values(monkeypatch: Any) -> None:
    monkeypatch.setenv("USAGE_MOCK", "maybe")
    monkeypatch.setenv("USAGE_MODE", "invalid")
    monkeypatch.setenv("USAGE_INTERVAL", "10")

    assert env_bool("USAGE_MOCK", True) is True
    assert env_choice("USAGE_MODE", {"web", "desktop", "tui"}, "") == ""
    assert env_int("USAGE_INTERVAL", 60, min_value=30) == 60
