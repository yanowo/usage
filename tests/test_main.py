from __future__ import annotations

from typing import Any

import main
from tui import AppViewState
from usage_client import PollOutcome, PollState, UsageSnapshot

CLI_ENV_VARS = [
    "USAGE_MODE",
    "USAGE_WEB_HOST",
    "USAGE_WEB_PORT",
    "USAGE_INTERVAL",
    "USAGE_MOCK",
    "USAGE_FORCE_GROUP",
    "USAG_FORCE_GROUP",
]


def _clear_cli_env(monkeypatch: Any) -> None:
    for name in CLI_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _parse_args(monkeypatch: Any, *args: str, clear_env: bool = True) -> Any:
    if clear_env:
        _clear_cli_env(monkeypatch)
    monkeypatch.setattr("sys.argv", ["usage", *args])
    return main.parse_args()


def _snapshot(percent: int = 42) -> UsageSnapshot:
    return UsageSnapshot(
        current_percent=percent,
        current_reset_at=1_000.0,
        weekly_percent=percent + 1,
        weekly_reset_at=2_000.0,
        current_status="ok",
        polled_at=123.0,
    )


def test_parse_args_defaults(monkeypatch: Any) -> None:
    args = _parse_args(monkeypatch)

    assert args.mock is False
    assert args.interval == 60
    assert args.tui is False
    assert args.web is False
    assert args.desktop is False
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.setup is False
    assert args.unsetup is False
    assert args.force_group is None


def test_parse_args_clamps_interval_to_minimum(monkeypatch: Any) -> None:
    args = _parse_args(monkeypatch, "--interval", "10")

    assert args.interval == 30


def test_parse_args_keeps_larger_interval(monkeypatch: Any) -> None:
    args = _parse_args(monkeypatch, "--interval", "120")

    assert args.interval == 120


def test_parse_args_mock_tui_and_force_group(monkeypatch: Any) -> None:
    args = _parse_args(monkeypatch, "--mock", "--tui", "--force-group", "2")

    assert args.mock is True
    assert args.tui is True
    assert args.force_group == 2


def test_parse_args_setup(monkeypatch: Any) -> None:
    args = _parse_args(monkeypatch, "--setup")

    assert args.setup is True


def test_parse_args_web_host_and_port(monkeypatch: Any) -> None:
    args = _parse_args(monkeypatch, "--web", "--host", "0.0.0.0", "--port", "9000")

    assert args.web is True
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_parse_args_reads_env_defaults(monkeypatch: Any) -> None:
    _clear_cli_env(monkeypatch)
    monkeypatch.setenv("USAGE_MODE", "web")
    monkeypatch.setenv("USAGE_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("USAGE_WEB_PORT", "9001")
    monkeypatch.setenv("USAGE_INTERVAL", "90")
    monkeypatch.setenv("USAGE_MOCK", "1")
    monkeypatch.setenv("USAGE_FORCE_GROUP", "3")

    args = _parse_args(monkeypatch, clear_env=False)

    assert args.web is True
    assert args.desktop is False
    assert args.host == "0.0.0.0"
    assert args.port == 9001
    assert args.interval == 90
    assert args.mock is True
    assert args.force_group == 3


def test_parse_args_cli_values_override_env_defaults(monkeypatch: Any) -> None:
    _clear_cli_env(monkeypatch)
    monkeypatch.setenv("USAGE_MODE", "web")
    monkeypatch.setenv("USAGE_WEB_HOST", "127.0.0.2")
    monkeypatch.setenv("USAGE_WEB_PORT", "9001")
    monkeypatch.setenv("USAGE_INTERVAL", "90")
    monkeypatch.setenv("USAGE_MOCK", "1")

    args = _parse_args(
        monkeypatch,
        "--desktop",
        "--host",
        "0.0.0.0",
        "--port",
        "7777",
        "--interval",
        "120",
        "--no-mock",
        clear_env=False,
    )

    assert args.web is False
    assert args.desktop is True
    assert args.host == "0.0.0.0"
    assert args.port == 7777
    assert args.interval == 120
    assert args.mock is False


def test_parse_args_desktop(monkeypatch: Any) -> None:
    args = _parse_args(monkeypatch, "--desktop")

    assert args.desktop is True


def test_apply_outcome_success_updates_snapshot_and_clears_fatal_message() -> None:
    state = AppViewState(fatal_message="boom")
    snapshot = _snapshot()
    outcome = PollOutcome(state=PollState.SUCCESS, snapshot=snapshot)

    main._apply_outcome(state, outcome)

    assert state.poll_state == PollState.SUCCESS
    assert state.snapshot == snapshot
    assert state.fatal_message is None


def test_apply_outcome_updates_message() -> None:
    state = AppViewState(message="old")
    outcome = PollOutcome(state=PollState.LOADING, message="new")

    main._apply_outcome(state, outcome)

    assert state.message == "new"


def test_apply_outcome_without_snapshot_keeps_existing_snapshot() -> None:
    existing = _snapshot(10)
    state = AppViewState(snapshot=existing)
    outcome = PollOutcome(state=PollState.LOADING)

    main._apply_outcome(state, outcome)

    assert state.snapshot == existing


def test_apply_outcome_non_success_keeps_fatal_message() -> None:
    state = AppViewState(fatal_message="still fatal")
    outcome = PollOutcome(state=PollState.TOKEN_ERROR)

    main._apply_outcome(state, outcome)

    assert state.poll_state == PollState.TOKEN_ERROR
    assert state.fatal_message == "still fatal"
