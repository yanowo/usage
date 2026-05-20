from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime

import codex_loader
from history_loader import load_entries
from pricing import calculate_cost
from usage_client import ClaudeUsageClient, PollOutcome, PollState
from usage_rate import GROUP_NAMES, UsageRateTracker

CLAUDE_COLOR = (244 / 255, 145 / 255, 100 / 255)
CODEX_COLOR = (88 / 255, 214 / 255, 230 / 255)
WARN_COLOR = (255 / 255, 196 / 255, 57 / 255)
DANGER_COLOR = (255 / 255, 69 / 255, 58 / 255)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QuotaRowState:
    title: str
    percent: float | None
    percent_text: str
    reset_text: str
    color: tuple[float, float, float]
    available: bool = True


@dataclass(slots=True)
class PopoverState:
    claude_session: QuotaRowState
    claude_weekly: QuotaRowState
    codex_session: QuotaRowState
    codex_weekly: QuotaRowState
    rate_text: str
    status_text: str
    today_text: str
    show_install_button: bool = False


@dataclass(slots=True)
class UsageViewResult:
    state: PopoverState
    outcome: PollOutcome
    codex_5h_pct: int | None
    fetched_at: float


def format_human_time(seconds: float) -> str:
    if seconds <= 0:
        return "0m"
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def bar_color(pct: float, brand: tuple[float, float, float]) -> tuple[float, float, float]:
    if pct >= 80:
        return DANGER_COLOR
    if pct >= 50:
        return WARN_COLOR
    return brand


def quota_row(
    title: str,
    pct: float | None,
    resets_at: float | None,
    now: float,
    color: tuple[float, float, float],
) -> QuotaRowState:
    if pct is None or resets_at is None:
        return missing_row(title, color)
    pct = max(0.0, min(100.0, float(pct)))
    return QuotaRowState(
        title=title,
        percent=pct,
        percent_text=f"{format_percent(pct)}% 已用",
        reset_text=f"重置 {format_human_time(resets_at - now)}",
        color=bar_color(pct, color),
        available=True,
    )


def missing_row(title: str, color: tuple[float, float, float]) -> QuotaRowState:
    return QuotaRowState(
        title=title,
        percent=None,
        percent_text="--",
        reset_text="重置 --",
        color=color,
        available=False,
    )


def today_title(mock: bool = False) -> str:
    if mock:
        return "今日：$45.20 (50,193,442 tokens)"

    today = datetime.now().astimezone().date()
    total_tokens = 0
    total_cost = 0.0

    entries = load_entries(hours_back=24) + codex_loader.load_entries(hours_back=24)
    for entry in entries:
        if entry.timestamp.astimezone().date() != today:
            continue
        total_tokens += entry.total_tokens
        total_cost += calculate_cost(entry)

    return f"今日：${total_cost:.2f} ({total_tokens:,} tokens)"


def format_percent(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def empty_state() -> PopoverState:
    return PopoverState(
        claude_session=missing_row("Session", CLAUDE_COLOR),
        claude_weekly=missing_row("Weekly", CLAUDE_COLOR),
        codex_session=missing_row("Session", CODEX_COLOR),
        codex_weekly=missing_row("Weekly", CODEX_COLOR),
        rate_text="速率：--",
        status_text="狀態：載入中",
        today_text="今日：$0.00 (0 tokens)",
        show_install_button=False,
    )


def error_state(message: str, mock: bool) -> PopoverState:
    state = empty_state()
    state.status_text = f"狀態：錯誤 ({message})"
    state.today_text = today_title(mock)
    state.show_install_button = False
    return state


def codex_rows(mock: bool = False) -> tuple[tuple[QuotaRowState, QuotaRowState], int | None]:
    if mock:
        now = time.time()
        rows = (
            quota_row("Session", 12.0, now + (4 * 3600) + (15 * 60), now, CODEX_COLOR),
            quota_row("Weekly", 28.0, now + (4 * 86400), now, CODEX_COLOR),
        )
        return rows, 12

    try:
        rate_limits = codex_loader.load_rate_limits()
    except Exception:
        if os.environ.get("USAGE_DEBUG") == "1":
            logger.warning("codex rate limits load failed", exc_info=True)
        rate_limits = None

    if rate_limits is None:
        rows = missing_row("Session", CODEX_COLOR), missing_row("Weekly", CODEX_COLOR)
        return rows, None

    now = time.time()
    codex_5h_pct = (
        round(rate_limits.five_hour_pct) if rate_limits.five_hour_pct is not None else None
    )
    rows = (
        quota_row(
            "Session",
            rate_limits.five_hour_pct,
            rate_limits.five_hour_resets_at,
            now,
            CODEX_COLOR,
        ),
        quota_row(
            "Weekly",
            rate_limits.seven_day_pct,
            rate_limits.seven_day_resets_at,
            now,
            CODEX_COLOR,
        ),
    )
    return rows, codex_5h_pct


def state_from_outcome(
    outcome: PollOutcome,
    codex_quota_rows: tuple[QuotaRowState, QuotaRowState],
    *,
    rate_group: int,
    mock: bool,
) -> PopoverState:
    now = time.time()
    today_text = today_title(mock)
    group_name = GROUP_NAMES[rate_group]

    if outcome.state == PollState.SUCCESS and outcome.snapshot is not None:
        snapshot = outcome.snapshot
        claude_session = quota_row(
            "Session",
            float(snapshot.current_percent) if snapshot.current_percent is not None else None,
            snapshot.current_reset_at,
            now,
            CLAUDE_COLOR,
        )
        claude_weekly = quota_row(
            "Weekly",
            float(snapshot.weekly_percent) if snapshot.weekly_percent is not None else None,
            snapshot.weekly_reset_at,
            now,
            CLAUDE_COLOR,
        )
        status_text = f"狀態：{outcome.message or '✓ 已同步'}"
    else:
        claude_session = missing_row("Session", CLAUDE_COLOR)
        claude_weekly = missing_row("Weekly", CLAUDE_COLOR)
        status_text = f"狀態：{outcome.message or '無資料'}"

    return PopoverState(
        claude_session=claude_session,
        claude_weekly=claude_weekly,
        codex_session=codex_quota_rows[0],
        codex_weekly=codex_quota_rows[1],
        rate_text=f"速率：{group_name}",
        status_text=status_text,
        today_text=today_text,
        show_install_button=outcome.state == PollState.TOKEN_ERROR,
    )


def fetch_usage_view(
    *,
    mock: bool = False,
    interval: int = 60,
    tracker: UsageRateTracker | None = None,
) -> UsageViewResult:
    client = ClaudeUsageClient(interval_seconds=interval, mock=mock)
    try:
        outcome = asyncio.run(client.fetch_once())
    finally:
        asyncio.run(client.aclose())

    quota_rows, codex_5h_pct = codex_rows(mock)
    effective_tracker = tracker if tracker is not None else UsageRateTracker(mock=mock)
    state = state_from_outcome(
        outcome,
        quota_rows,
        rate_group=effective_tracker.group(),
        mock=mock,
    )
    return UsageViewResult(
        state=state,
        outcome=outcome,
        codex_5h_pct=codex_5h_pct,
        fetched_at=time.time(),
    )
