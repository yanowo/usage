from __future__ import annotations

import json
import logging
import os
import queue
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from history_loader import UsageEntry

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(os.path.expanduser("~/.codex/sessions"))
STATE_DB = Path(os.path.expanduser("~/.codex/state_5.sqlite"))
LOGS_DB = Path(os.path.expanduser("~/.codex/logs_2.sqlite"))
FIVE_HOUR_WINDOW_MINUTES = 5 * 60
WEEKLY_WINDOW_MINUTES = 7 * 24 * 60
RATE_LIMIT_LOG_TARGET = "codex_api::endpoint::responses_websocket"
RATE_LIMIT_LOG_ROW_LOOKBACK = 2_000_000
WEBSOCKET_EVENT_MARKER = "websocket event:"
APP_SERVER_TIMEOUT_SECONDS = 8.0
APP_SERVER_INIT_ID = 1
APP_SERVER_RATE_LIMITS_ID = 2
CODEX_COMMAND_ENV = "USAGE_CODEX_COMMAND"


@dataclass(slots=True)
class CodexRateLimits:
    five_hour_pct: float | None
    five_hour_resets_at: float | None
    seven_day_pct: float | None
    seven_day_resets_at: float | None
    updated_at: str = ""


def load_entries(hours_back: int = 0) -> list[UsageEntry]:
    if not SESSIONS_DIR.is_dir():
        return []

    entries: list[UsageEntry] = []
    seen: set[str] = set()
    cutoff = datetime.now(UTC) - timedelta(hours=hours_back) if hours_back > 0 else None
    cutoff_ts = cutoff.timestamp() if cutoff else None
    models = _load_thread_models()

    for jsonl_path in SESSIONS_DIR.rglob("*.jsonl"):
        if cutoff_ts is not None:
            try:
                if jsonl_path.stat().st_mtime < cutoff_ts:
                    continue
            except OSError as exc:
                logger.warning("failed to stat session log %s: %s", jsonl_path, exc)
                continue
        entry = _parse_jsonl(jsonl_path, models, cutoff)
        if entry is None or entry.session_id in seen:
            continue
        seen.add(entry.session_id)
        entries.append(entry)

    entries.sort(key=lambda entry: entry.timestamp)
    return entries


def load_rate_limits() -> CodexRateLimits | None:
    app_server_rate_limits = _load_app_server_rate_limits()
    if app_server_rate_limits is not None:
        return app_server_rate_limits

    candidates: list[CodexRateLimits] = []
    candidates.extend(_load_log_rate_limit_candidates())
    if not SESSIONS_DIR.is_dir():
        return max(candidates, key=_rate_limits_sort_key) if candidates else None
    for path in _recent_jsonl_files():
        rate_limits = _extract_rate_limits(path)
        if rate_limits is not None:
            candidates.append(rate_limits)
    if not candidates:
        return None
    return max(candidates, key=_rate_limits_sort_key)


def latest_sessions_mtime() -> float | None:
    if not SESSIONS_DIR.is_dir():
        return None
    latest: float | None = None
    for path in SESSIONS_DIR.rglob("*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            logger.warning("failed to stat codex session %s: %s", path, exc)
            continue
        latest = mtime if latest is None else max(latest, mtime)
    return latest


def latest_usage_source_mtime() -> float | None:
    latest = latest_sessions_mtime()
    for path in _logs_db_paths():
        mtime = _path_mtime(path)
        if mtime is None:
            continue
        latest = mtime if latest is None else max(latest, mtime)
    return latest


def _load_thread_models() -> dict[str, str]:
    if not STATE_DB.exists():
        return {}
    try:
        with sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT id, model FROM threads WHERE model IS NOT NULL",
            ).fetchall()
    except (OSError, sqlite3.Error):
        if os.environ.get("USAGE_DEBUG") == "1":
            logger.warning("codex thread models load failed", exc_info=True)
        return {}
    return {
        thread_id: model
        for thread_id, model in rows
        if isinstance(thread_id, str) and isinstance(model, str) and model
    }


def _recent_jsonl_files() -> list[Path]:
    paths_with_mtime: list[tuple[float, Path]] = []
    for path in SESSIONS_DIR.rglob("*.jsonl"):
        try:
            paths_with_mtime.append((path.stat().st_mtime, path))
        except OSError as exc:
            logger.warning("failed to stat codex session %s: %s", path, exc)
    paths_with_mtime.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in paths_with_mtime[:20]]


def _load_log_rate_limit_candidates() -> list[CodexRateLimits]:
    if not LOGS_DB.exists():
        return []
    try:
        with sqlite3.connect(f"file:{LOGS_DB}?mode=ro", uri=True) as conn:
            max_row = conn.execute("SELECT MAX(id) FROM logs").fetchone()
            max_id = max_row[0] if max_row else None
            if not isinstance(max_id, int):
                return []
            min_id = max(0, max_id - RATE_LIMIT_LOG_ROW_LOOKBACK)
            rows = conn.execute(
                """
                SELECT id, ts, feedback_log_body
                FROM logs
                WHERE id >= ?
                  AND target = ?
                  AND feedback_log_body LIKE '%codex.rate_limits%'
                ORDER BY id DESC
                LIMIT 100
                """,
                (min_id, RATE_LIMIT_LOG_TARGET),
            ).fetchall()
    except (OSError, sqlite3.Error):
        if os.environ.get("USAGE_DEBUG") == "1":
            logger.warning("codex rate limit logs load failed", exc_info=True)
        return []

    candidates: list[CodexRateLimits] = []
    for _row_id, ts, body in rows:
        if not isinstance(body, str):
            continue
        event = _event_json_from_log_body(body)
        if event is None or event.get("type") != "codex.rate_limits":
            continue
        updated_at = _timestamp_from_unix_seconds(ts)
        rate_limits = _rate_limits_from_payload(_as_dict(event.get("rate_limits")), updated_at)
        if rate_limits is not None:
            candidates.append(rate_limits)
    return candidates


def _load_app_server_rate_limits() -> CodexRateLimits | None:
    codex_command = _codex_command()
    if codex_command is None:
        return None
    try:
        proc = subprocess.Popen(
            [*codex_command, "app-server", "--disable", "plugins"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None

    lines: queue.Queue[str] = queue.Queue()

    def read_stdout() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            lines.put(line)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + APP_SERVER_TIMEOUT_SECONDS
        _write_app_server_request(proc, _app_server_initialize_request())
        if _wait_for_app_server_response(lines, APP_SERVER_INIT_ID, deadline) is None:
            return None
        _write_app_server_request(proc, _app_server_rate_limits_request())
        response = _wait_for_app_server_response(lines, APP_SERVER_RATE_LIMITS_ID, deadline)
        if response is None:
            return None
        return _rate_limits_from_app_server_response(response)
    except (BrokenPipeError, OSError):
        return None
    finally:
        _stop_app_server_process(proc)


def _codex_command() -> list[str] | None:
    configured = os.environ.get(CODEX_COMMAND_ENV, "").strip()
    if configured:
        return _split_configured_command(configured)

    path = shutil.which("codex")
    if path:
        return [path]

    candidates = _codex_executable_candidates()
    candidates.sort(key=lambda candidate: _path_mtime(candidate) or 0.0, reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate)]
    return None


def _split_configured_command(command: str) -> list[str]:
    # Preserve Windows backslashes even when tests or CI run on POSIX systems.
    if _starts_with_windows_path(command):
        return [_strip_wrapping_quotes(part) for part in shlex.split(command, posix=False)]
    return shlex.split(command)


def _starts_with_windows_path(command: str) -> bool:
    value = command.lstrip()
    if value[:1] in ("'", '"'):
        value = value[1:]
    return (len(value) >= 3 and value[1:3] == ":\\") or value.startswith("\\\\")


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _codex_executable_candidates(home: Path | None = None) -> list[Path]:
    root = home or Path.home()
    candidates: list[Path] = []
    for extensions_dir in (
        root / ".vscode" / "extensions",
        root / ".vscode-insiders" / "extensions",
    ):
        for pattern in _codex_extension_patterns():
            candidates.extend(extensions_dir.glob(pattern))
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "npm" / "codex.cmd")
    return candidates


def _codex_extension_patterns() -> tuple[str, ...]:
    if sys.platform == "win32":
        return ("openai.chatgpt-*/bin/windows-x86_64/codex.exe",)
    if sys.platform == "darwin":
        return (
            "openai.chatgpt-*/bin/macos-*/codex",
            "openai.chatgpt-*/bin/darwin-*/codex",
        )
    return ("openai.chatgpt-*/bin/linux-*/codex",)


def _app_server_initialize_request() -> dict[str, Any]:
    return {
        "id": APP_SERVER_INIT_ID,
        "method": "initialize",
        "params": {
            "clientInfo": {
                "name": "usage",
                "title": "usage",
                "version": "0.0.0",
            },
            "capabilities": None,
        },
    }


def _app_server_rate_limits_request() -> dict[str, Any]:
    return {
        "id": APP_SERVER_RATE_LIMITS_ID,
        "method": "account/rateLimits/read",
    }


def _write_app_server_request(
    proc: subprocess.Popen[str],
    request: dict[str, Any],
) -> None:
    if proc.stdin is None:
        raise BrokenPipeError
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()


def _wait_for_app_server_response(
    lines: queue.Queue[str],
    request_id: int,
    deadline: float,
) -> dict[str, Any] | None:
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            line = lines.get(timeout=max(0.01, min(0.2, remaining)))
        except queue.Empty:
            continue
        data = _load_json_line(line)
        if data is not None and data.get("id") == request_id:
            return data
    return None


def _stop_app_server_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


def _rate_limits_from_app_server_response(response: dict[str, Any]) -> CodexRateLimits | None:
    result = _as_dict(response.get("result"))
    by_limit_id = _as_dict(result.get("rateLimitsByLimitId"))
    rate_limits = _as_dict(by_limit_id.get("codex"))
    if not rate_limits:
        rate_limits = _as_dict(result.get("rateLimits"))
    return _rate_limits_from_payload(rate_limits, datetime.now(UTC).isoformat())


def _extract_rate_limits(path: Path) -> CodexRateLimits | None:
    last_rate_limits: tuple[dict[str, Any], str] | None = None
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                data = _load_json_line(line)
                if data is None or data.get("type") != "event_msg":
                    continue
                payload = _as_dict(data.get("payload"))
                if payload.get("type") != "token_count":
                    continue
                rate_limits = _as_dict(payload.get("rate_limits"))
                if rate_limits:
                    last_rate_limits = (rate_limits, _as_str(data.get("timestamp")))
    except OSError as exc:
        logger.warning("failed to read codex session %s: %s", path, exc)
        return None
    if last_rate_limits is None:
        return None
    rate_limits, updated_at = last_rate_limits
    return _rate_limits_from_payload(rate_limits, updated_at)


def _rate_limits_from_payload(
    rate_limits: dict[str, Any],
    updated_at: str,
) -> CodexRateLimits | None:
    five_hour = _limit_by_window(
        rate_limits,
        FIVE_HOUR_WINDOW_MINUTES,
        ("five_hour", "5h", "primary"),
    )
    weekly = _limit_by_window(
        rate_limits,
        WEEKLY_WINDOW_MINUTES,
        ("weekly", "seven_day", "7d", "secondary"),
    )
    five_pct = _limit_used_percent(five_hour)
    five_reset = _limit_resets_at(five_hour)
    seven_pct = _limit_used_percent(weekly)
    seven_reset = _limit_resets_at(weekly)
    now_ts = datetime.now(UTC).timestamp()
    if five_reset is not None and five_reset < now_ts:
        five_pct = 0.0
    if seven_reset is not None and seven_reset < now_ts:
        seven_pct = 0.0
    if five_pct is None and seven_pct is None:
        return None
    return CodexRateLimits(
        five_hour_pct=five_pct,
        five_hour_resets_at=five_reset,
        seven_day_pct=seven_pct,
        seven_day_resets_at=seven_reset,
        updated_at=updated_at,
    )


def _event_json_from_log_body(body: str) -> dict[str, Any] | None:
    marker_index = body.find(WEBSOCKET_EVENT_MARKER)
    if marker_index < 0:
        return None
    start = body.find("{", marker_index + len(WEBSOCKET_EVENT_MARKER))
    if start < 0:
        return None
    end = _balanced_json_object_end(body, start)
    if end is None:
        return None
    try:
        event = json.loads(body[start:end])
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _balanced_json_object_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _rate_limits_sort_key(rate_limits: CodexRateLimits) -> float:
    updated = _parse_timestamp(rate_limits.updated_at)
    return updated.timestamp() if updated is not None else 0.0


def _limit_by_window(
    rate_limits: dict[str, Any],
    window_minutes: int,
    fallback_keys: tuple[str, ...],
) -> dict[str, Any]:
    for value in rate_limits.values():
        limit = _as_dict(value)
        if _limit_window_minutes(limit) == float(window_minutes):
            return limit
    for key in fallback_keys:
        limit = _as_dict(rate_limits.get(key))
        if limit:
            return limit
    return {}


def _limit_used_percent(limit: dict[str, Any]) -> float | None:
    value = _as_optional_float(limit.get("used_percent"))
    if value is not None:
        return value
    value = _as_optional_float(limit.get("used_percentage"))
    if value is not None:
        return value
    value = _as_optional_float(limit.get("usedPercent"))
    if value is not None:
        return value
    remaining = _as_optional_float(limit.get("remaining_percent"))
    if remaining is None:
        remaining = _as_optional_float(limit.get("remaining_percentage"))
    if remaining is None:
        return None
    return 100.0 - remaining


def _limit_resets_at(limit: dict[str, Any]) -> float | None:
    value = _as_optional_float(limit.get("resets_at"))
    if value is not None:
        return value
    value = _as_optional_float(limit.get("reset_at"))
    if value is not None:
        return value
    return _as_optional_float(limit.get("resetsAt"))


def _limit_window_minutes(limit: dict[str, Any]) -> float | None:
    value = _as_optional_float(limit.get("window_minutes"))
    if value is not None:
        return value
    return _as_optional_float(limit.get("windowDurationMins"))


def _parse_jsonl(path: Path, models: dict[str, str], cutoff: datetime | None) -> UsageEntry | None:
    session_id = ""
    session_timestamp = ""
    project = "unknown"
    last_usage: dict[str, Any] | None = None
    last_usage_timestamp = ""
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                data = _load_json_line(line)
                if data is None:
                    continue
                if data.get("type") == "session_meta":
                    payload = _as_dict(data.get("payload"))
                    session_id = _as_str(payload.get("id"))
                    session_timestamp = _as_str(payload.get("timestamp"))
                    project = _project_from_cwd(_as_str(payload.get("cwd")))
                    continue
                if data.get("type") != "event_msg":
                    continue
                payload = _as_dict(data.get("payload"))
                if payload.get("type") != "token_count":
                    continue
                usage = _as_dict(_as_dict(payload.get("info")).get("total_token_usage"))
                if usage:
                    last_usage = usage
                    last_usage_timestamp = _as_str(data.get("timestamp"))
    except OSError as exc:
        logger.warning("failed to parse codex session %s: %s", path, exc)
        return None
    timestamp = _parse_timestamp(last_usage_timestamp) or _parse_timestamp(session_timestamp)
    if not session_id or last_usage is None or timestamp is None:
        return None
    if cutoff is not None and timestamp < cutoff:
        return None
    cached = _as_int(last_usage.get("cached_input_tokens"))
    input_tokens = max(0, _as_int(last_usage.get("input_tokens")) - cached)
    output_tokens = _as_int(last_usage.get("output_tokens")) + _as_int(
        last_usage.get("reasoning_output_tokens"),
    )
    if input_tokens == 0 and output_tokens == 0:
        return None
    return UsageEntry(
        timestamp=timestamp,
        session_id=session_id,
        message_id=session_id,
        request_id="",
        model=models.get(session_id, "unknown"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=0,
        cache_read_tokens=cached,
        cost_usd=None,
        project=project,
    )


def _load_json_line(line: str) -> dict[str, Any] | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _timestamp_from_unix_seconds(value: Any) -> str:
    seconds = _as_optional_float(value)
    if seconds is None:
        return ""
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def _project_from_cwd(cwd: str) -> str:
    return Path(os.path.expanduser(cwd)).name if cwd else "unknown"


def _logs_db_paths() -> tuple[Path, Path, Path]:
    return (
        LOGS_DB,
        LOGS_DB.with_name(f"{LOGS_DB.name}-wal"),
        LOGS_DB.with_name(f"{LOGS_DB.name}-shm"),
    )


def _path_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
