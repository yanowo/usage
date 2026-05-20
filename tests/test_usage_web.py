from __future__ import annotations

from usage_client import PollOutcome, PollState
from usage_state import (
    CLAUDE_COLOR,
    CODEX_COLOR,
    PopoverState,
    QuotaRowState,
    UsageViewResult,
    missing_row,
    quota_row,
)
from usage_web import render_html, rgb_to_hex, usage_payload


def _state() -> PopoverState:
    now = 1_000.0
    return PopoverState(
        claude_session=quota_row("Session", 42.0, now + 90, now, CLAUDE_COLOR),
        claude_weekly=quota_row("Weekly", 7.0, now + 3600, now, CLAUDE_COLOR),
        codex_session=missing_row("Session", CODEX_COLOR),
        codex_weekly=QuotaRowState(
            title="Weekly",
            percent=81.0,
            percent_text="81% 已用",
            reset_text="重置 1d 0h",
            color=(1.0, 0.0, 0.0),
        ),
        rate_text="速率：Idle",
        status_text="狀態：✓ 已同步",
        today_text="今日：$1.23 (456 tokens)",
    )


def test_rgb_to_hex_clamps_and_formats() -> None:
    assert rgb_to_hex((1.0, 0.5, 0.0)) == "#ff8000"
    assert rgb_to_hex((2.0, -1.0, 0.0)) == "#ff0000"


def test_usage_payload_contains_widget_data() -> None:
    result = UsageViewResult(
        state=_state(),
        outcome=PollOutcome(state=PollState.SUCCESS, message="ok"),
        codex_5h_pct=None,
        fetched_at=1234.5,
    )

    payload = usage_payload(result, mock=True)

    assert payload["ok"] is True
    assert payload["mock"] is True
    assert payload["poll_state"] == "success"
    assert payload["claude"]["session"]["percent"] == 42.0
    assert payload["claude"]["session"]["color"] == "#f49164"
    assert payload["codex"]["session"]["available"] is False
    assert payload["today_text"] == "今日：$1.23 (456 tokens)"


def test_render_html_sets_mode_and_interval() -> None:
    html = render_html(compact=True, interval=30)

    assert '<body class="compact">' in html
    assert "const intervalMs = 30000;" in html
    assert "/api/usage" in html
