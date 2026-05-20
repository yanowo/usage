from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import codex_loader


@pytest.fixture(autouse=True)
def _isolate_codex_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(codex_loader, "LOGS_DB", tmp_path / "logs_2.sqlite")
    monkeypatch.setattr(codex_loader, "_load_app_server_rate_limits", lambda: None)


def _write_session(
    path: Path,
    *,
    session_id: str,
    timestamp: str,
    usage: dict[str, int],
    cwd: str = "/tmp/demo",
) -> None:
    lines = [
        {
            "type": "session_meta",
            "payload": {"id": session_id, "timestamp": timestamp, "cwd": cwd},
        },
        {
            "type": "event_msg",
            "timestamp": timestamp,
            "payload": {"type": "token_count", "info": {"total_token_usage": usage}},
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")


def _write_rate_log(path: Path, *, ts: int, rate_limits: dict[str, object]) -> None:
    event = {
        "type": "codex.rate_limits",
        "rate_limits": rate_limits,
    }
    body = f"prefix {codex_loader.WEBSOCKET_EVENT_MARKER} {json.dumps(event)} suffix"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                target TEXT NOT NULL,
                feedback_log_body TEXT
            )
            """,
        )
        conn.execute(
            "INSERT INTO logs (ts, target, feedback_log_body) VALUES (?, ?, ?)",
            (ts, codex_loader.RATE_LIMIT_LOG_TARGET, body),
        )


def test_load_entries_returns_empty_list_when_sessions_dir_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", tmp_path / "missing")

    assert codex_loader.load_entries() == []


def test_load_entries_parses_valid_jsonl_and_filters_by_hours_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(
        codex_loader,
        "_load_thread_models",
        lambda: {"session-old": "gpt-test", "session-new": "gpt-test"},
    )
    old_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    new_ts = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    _write_session(
        sessions_dir / "old.jsonl",
        session_id="session-old",
        timestamp=old_ts,
        usage={"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3},
    )
    _write_session(
        sessions_dir / "new.jsonl",
        session_id="session-new",
        timestamp=new_ts,
        usage={"input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 7},
    )

    all_entries = codex_loader.load_entries()
    recent_entries = codex_loader.load_entries(hours_back=1)

    assert [entry.input_tokens for entry in all_entries] == [8, 15]
    assert [entry.output_tokens for entry in all_entries] == [3, 7]
    assert all(entry.model == "gpt-test" for entry in all_entries)
    assert len(recent_entries) == 1
    assert recent_entries[0].input_tokens == 15
    assert recent_entries[0].output_tokens == 7


def test_parse_jsonl_skips_bad_lines_and_missing_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(
        "\n".join(
            [
                "{bad json",
                json.dumps({"type": "event_msg", "payload": {"type": "token_count"}}),
                json.dumps({"type": "session_meta", "payload": {"id": "s1"}}),
            ]
        ),
        encoding="utf-8",
    )

    assert codex_loader._parse_jsonl(path, {}, None) is None


def test_parse_timestamp_accepts_expected_iso8601_variants() -> None:
    expected = datetime(2026, 1, 1, tzinfo=UTC)

    assert codex_loader._parse_timestamp("2026-01-01T00:00:00Z") == expected
    assert codex_loader._parse_timestamp("2026-01-01T00:00:00+00:00") == expected
    assert codex_loader._parse_timestamp("2026-01-01T00:00:00") == expected


def test_load_rate_limits_returns_none_when_sessions_dir_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", tmp_path / "missing")

    assert codex_loader.load_rate_limits() is None


def test_latest_sessions_mtime_returns_latest_jsonl_mtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    first = sessions_dir / "first.jsonl"
    second = sessions_dir / "nested" / "second.jsonl"
    first.parent.mkdir(parents=True, exist_ok=True)
    second.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    first_ts = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    second_ts = datetime(2026, 1, 2, tzinfo=UTC).timestamp()
    os.utime(first, (first_ts, first_ts))
    os.utime(second, (second_ts, second_ts))

    assert codex_loader.latest_sessions_mtime() == second_ts


def test_latest_usage_source_mtime_includes_codex_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    logs_db = tmp_path / "logs_2.sqlite"
    logs_wal = logs_db.with_name(f"{logs_db.name}-wal")
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(codex_loader, "LOGS_DB", logs_db)
    session_path = sessions_dir / "session.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("{}", encoding="utf-8")
    logs_db.write_text("", encoding="utf-8")
    logs_wal.write_text("", encoding="utf-8")
    session_ts = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    logs_ts = datetime(2026, 1, 2, tzinfo=UTC).timestamp()
    wal_ts = datetime(2026, 1, 3, tzinfo=UTC).timestamp()
    os.utime(session_path, (session_ts, session_ts))
    os.utime(logs_db, (logs_ts, logs_ts))
    os.utime(logs_wal, (wal_ts, wal_ts))

    assert codex_loader.latest_usage_source_mtime() == wal_ts


def test_event_json_from_log_body_extracts_balanced_json() -> None:
    event = {
        "type": "codex.rate_limits",
        "note": 'brace } and quote " inside',
        "rate_limits": {"primary": {"used_percent": 25.0}},
    }
    body = f"prefix {codex_loader.WEBSOCKET_EVENT_MARKER} {json.dumps(event)} trailing text"

    assert codex_loader._event_json_from_log_body(body) == event


def test_load_rate_limits_reads_primary_and_secondary_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    now = datetime.now(UTC)
    payload = {
        "type": "event_msg",
        "timestamp": now.isoformat(),
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 25.0, "resets_at": now.timestamp() + 60},
                "secondary": {"used_percent": 70.0, "resets_at": now.timestamp() + 120},
            },
        },
    }
    path = sessions_dir / "rate.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = codex_loader.load_rate_limits()

    assert result == codex_loader.CodexRateLimits(
        five_hour_pct=25.0,
        five_hour_resets_at=now.timestamp() + 60,
        seven_day_pct=70.0,
        seven_day_resets_at=now.timestamp() + 120,
        updated_at=now.isoformat(),
    )


def test_load_rate_limits_prefers_app_server_rate_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", tmp_path / "missing")
    monkeypatch.setattr(
        codex_loader,
        "_load_app_server_rate_limits",
        lambda: codex_loader.CodexRateLimits(
            five_hour_pct=58.0,
            five_hour_resets_at=4102444800.0,
            seven_day_pct=25.0,
            seven_day_resets_at=4102448400.0,
            updated_at=datetime.now(UTC).isoformat(),
        ),
    )

    result = codex_loader.load_rate_limits()

    assert result is not None
    assert result.five_hour_pct == 58.0
    assert result.seven_day_pct == 25.0


def test_codex_command_uses_configured_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(codex_loader.CODEX_COMMAND_ENV, "C:\\Tools\\codex.exe")

    assert codex_loader._codex_command() == ["C:\\Tools\\codex.exe"]


def test_codex_command_finds_vscode_extension_when_path_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(codex_loader.CODEX_COMMAND_ENV, raising=False)
    monkeypatch.setattr("codex_loader.shutil.which", lambda _command: None)
    monkeypatch.setattr("codex_loader.Path.home", lambda: tmp_path)
    older = (
        tmp_path
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-1"
        / "bin"
        / "windows-x86_64"
        / "codex.exe"
    )
    newer = (
        tmp_path
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-2"
        / "bin"
        / "windows-x86_64"
        / "codex.exe"
    )
    older.parent.mkdir(parents=True, exist_ok=True)
    newer.parent.mkdir(parents=True, exist_ok=True)
    older.write_text("", encoding="utf-8")
    newer.write_text("", encoding="utf-8")
    older_ts = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    newer_ts = datetime(2026, 1, 2, tzinfo=UTC).timestamp()
    os.utime(older, (older_ts, older_ts))
    os.utime(newer, (newer_ts, newer_ts))

    assert codex_loader._codex_command() == [str(newer)]


def test_rate_limits_from_app_server_response_supports_camel_case_windows() -> None:
    response = {
        "id": 2,
        "result": {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 58.0,
                    "windowDurationMins": 300,
                    "resetsAt": 4102444800,
                },
                "secondary": {
                    "usedPercent": 25.0,
                    "windowDurationMins": 10080,
                    "resetsAt": 4102448400,
                },
            },
            "rateLimitsByLimitId": {
                "codex": {
                    "limitId": "codex",
                    "primary": {
                        "usedPercent": 59.0,
                        "windowDurationMins": 300,
                        "resetsAt": 4102444801,
                    },
                    "secondary": {
                        "usedPercent": 26.0,
                        "windowDurationMins": 10080,
                        "resetsAt": 4102448401,
                    },
                }
            },
        },
    }

    result = codex_loader._rate_limits_from_app_server_response(response)

    assert result is not None
    assert result.five_hour_pct == 59.0
    assert result.five_hour_resets_at == 4102444801
    assert result.seven_day_pct == 26.0
    assert result.seven_day_resets_at == 4102448401


def test_load_rate_limits_reads_codex_rate_limit_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "missing-sessions"
    logs_db = tmp_path / "logs_2.sqlite"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(codex_loader, "LOGS_DB", logs_db)
    ts = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
    _write_rate_log(
        logs_db,
        ts=ts,
        rate_limits={
            "primary": {
                "used_percent": 26.0,
                "window_minutes": 300,
                "reset_at": 4102444800,
            },
            "secondary": {
                "used_percent": 42.0,
                "window_minutes": 10080,
                "reset_at": 4102448400,
            },
        },
    )

    result = codex_loader.load_rate_limits()

    assert result is not None
    assert result.five_hour_pct == 26.0
    assert result.five_hour_resets_at == 4102444800
    assert result.seven_day_pct == 42.0
    assert result.seven_day_resets_at == 4102448400
    assert result.updated_at == datetime.fromtimestamp(ts, UTC).isoformat()


def test_load_rate_limits_prefers_newer_source_between_logs_and_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    logs_db = tmp_path / "logs_2.sqlite"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(codex_loader, "LOGS_DB", logs_db)
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = older + timedelta(minutes=1)
    path = sessions_dir / "rate.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "event_msg",
                "timestamp": older.isoformat(),
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {"used_percent": 15.0, "window_minutes": 300},
                        "secondary": {"used_percent": 18.0, "window_minutes": 10080},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _write_rate_log(
        logs_db,
        ts=int(newer.timestamp()),
        rate_limits={
            "primary": {"used_percent": 25.0, "window_minutes": 300},
            "secondary": {"used_percent": 20.0, "window_minutes": 10080},
        },
    )

    result = codex_loader.load_rate_limits()

    assert result is not None
    assert result.five_hour_pct == 25.0
    assert result.seven_day_pct == 20.0


def test_load_rate_limits_uses_window_minutes_not_primary_secondary_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    now = datetime.now(UTC)
    payload = {
        "type": "event_msg",
        "timestamp": now.isoformat(),
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {
                    "used_percent": 70.0,
                    "window_minutes": 10080,
                    "resets_at": now.timestamp() + 120,
                },
                "secondary": {
                    "used_percent": 25.0,
                    "window_minutes": 300,
                    "resets_at": now.timestamp() + 60,
                },
            },
        },
    }
    path = sessions_dir / "swapped.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = codex_loader.load_rate_limits()

    assert result is not None
    assert result.five_hour_pct == 25.0
    assert result.five_hour_resets_at == now.timestamp() + 60
    assert result.seven_day_pct == 70.0
    assert result.seven_day_resets_at == now.timestamp() + 120


def test_load_rate_limits_supports_named_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    now = datetime.now(UTC)
    payload = {
        "type": "event_msg",
        "timestamp": now.isoformat(),
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "five_hour": {"used_percentage": 0.0, "reset_at": now.timestamp() + 60},
                "seven_day": {"used_percentage": 9.0, "reset_at": now.timestamp() + 120},
            },
        },
    }
    path = sessions_dir / "named.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = codex_loader.load_rate_limits()

    assert result is not None
    assert result.five_hour_pct == 0.0
    assert result.five_hour_resets_at == now.timestamp() + 60
    assert result.seven_day_pct == 9.0
    assert result.seven_day_resets_at == now.timestamp() + 120


def test_load_rate_limits_converts_remaining_percent_to_used_percent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    now = datetime.now(UTC)
    payload = {
        "type": "event_msg",
        "timestamp": now.isoformat(),
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {
                    "remaining_percent": 85.0,
                    "window_minutes": 300,
                    "resets_at": now.timestamp() + 60,
                },
                "secondary": {
                    "remaining_percentage": 60.0,
                    "window_minutes": 10080,
                    "resets_at": now.timestamp() + 120,
                },
            },
        },
    }
    path = sessions_dir / "remaining.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = codex_loader.load_rate_limits()

    assert result is not None
    assert result.five_hour_pct == 15.0
    assert result.seven_day_pct == 40.0


def test_load_rate_limits_returns_newest_token_event_across_recent_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(codex_loader, "SESSIONS_DIR", sessions_dir)
    now = datetime.now(UTC)

    newest_payload = {
        "type": "event_msg",
        "timestamp": now.isoformat(),
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 21.0, "window_minutes": 300},
                "secondary": {"used_percent": 34.0, "window_minutes": 10080},
            },
        },
    }
    older_payload = {
        "type": "event_msg",
        "timestamp": (now - timedelta(minutes=10)).isoformat(),
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 99.0, "window_minutes": 300},
                "secondary": {"used_percent": 88.0, "window_minutes": 10080},
            },
        },
    }
    newest_path = sessions_dir / "newest.jsonl"
    older_path = sessions_dir / "older-but-written-last.jsonl"
    newest_path.parent.mkdir(parents=True, exist_ok=True)
    newest_path.write_text(json.dumps(newest_payload), encoding="utf-8")
    older_path.write_text(json.dumps(older_payload), encoding="utf-8")

    result = codex_loader.load_rate_limits()

    assert result is not None
    assert result.five_hour_pct == 21.0
    assert result.seven_day_pct == 34.0
    assert result.updated_at == now.isoformat()
