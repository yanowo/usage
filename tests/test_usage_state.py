from __future__ import annotations

import usage_state


def test_format_human_time_zero_and_negative() -> None:
    assert usage_state.format_human_time(0) == "0m"
    assert usage_state.format_human_time(-1) == "0m"


def test_format_human_time_sub_minute() -> None:
    assert usage_state.format_human_time(30) == "0m"


def test_format_human_time_minutes_hours_and_days() -> None:
    assert usage_state.format_human_time(90) == "1m"
    assert usage_state.format_human_time(3700) == "1h 1m"
    assert usage_state.format_human_time(90000) == "1d 1h"


def test_format_percent() -> None:
    assert usage_state.format_percent(50.0) == "50"
    assert usage_state.format_percent(50.5) == "50.5"
    assert usage_state.format_percent(0.0) == "0"


def test_bar_color_thresholds() -> None:
    brand = (0.1, 0.2, 0.3)

    assert usage_state.bar_color(80, brand) == usage_state.DANGER_COLOR
    assert usage_state.bar_color(60, brand) == usage_state.WARN_COLOR
    assert usage_state.bar_color(49, brand) == brand


def test_quota_row_returns_missing_when_percent_is_none() -> None:
    row = usage_state.quota_row("Session", None, 1_100.0, 1_000.0, usage_state.CODEX_COLOR)

    assert row.available is False
    assert row.percent is None
    assert row.percent_text == "--"


def test_quota_row_returns_missing_when_reset_is_none() -> None:
    row = usage_state.quota_row("Session", 50.0, None, 1_000.0, usage_state.CODEX_COLOR)

    assert row.available is False
    assert row.percent is None
    assert row.percent_text == "--"


def test_quota_row_formats_available_row() -> None:
    row = usage_state.quota_row("Session", 50.5, 1_090.0, 1_000.0, usage_state.CODEX_COLOR)

    assert row.available is True
    assert row.percent == 50.5
    assert row.percent_text == "50.5% 已用"
    assert row.reset_text.startswith("重置 ")
    assert row.color == usage_state.WARN_COLOR


def test_quota_row_clamps_percent_to_range() -> None:
    high = usage_state.quota_row("Session", 150.0, 1_090.0, 1_000.0, usage_state.CODEX_COLOR)
    low = usage_state.quota_row("Session", -10.0, 1_090.0, 1_000.0, usage_state.CODEX_COLOR)

    assert high.percent == 100.0
    assert high.percent_text == "100% 已用"
    assert low.percent == 0.0
    assert low.percent_text == "0% 已用"


def test_missing_row() -> None:
    row = usage_state.missing_row("Weekly", usage_state.CLAUDE_COLOR)

    assert row.available is False
    assert row.percent is None
    assert row.percent_text == "--"
    assert row.reset_text == "重置 --"


def test_today_title_mock() -> None:
    assert usage_state.today_title(mock=True) == "今日：$45.20 (50,193,442 tokens)"


def test_empty_state() -> None:
    state = usage_state.empty_state()
    rows = (
        state.claude_session,
        state.claude_weekly,
        state.codex_session,
        state.codex_weekly,
    )

    assert all(row.available is False for row in rows)
    assert state.show_install_button is False


def test_error_state_uses_message_and_mock_today_title() -> None:
    state = usage_state.error_state("boom", mock=True)

    assert "boom" in state.status_text
    assert state.today_text == "今日：$45.20 (50,193,442 tokens)"
