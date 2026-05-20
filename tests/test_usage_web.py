from __future__ import annotations

from usage_client import PollOutcome, PollState
from usage_state import (
    CLAUDE_COLOR,
    CODEX_COLOR,
    FIVE_HOUR_TITLE,
    WEEKLY_TITLE,
    PopoverState,
    QuotaRowState,
    UsageViewResult,
    missing_row,
    quota_row,
)
from usage_web import _query_flag, _query_layout, render_html, rgb_to_hex, usage_payload


def _state() -> PopoverState:
    now = 1_000.0
    return PopoverState(
        claude_session=quota_row(FIVE_HOUR_TITLE, 42.0, now + 90, now, CLAUDE_COLOR),
        claude_weekly=quota_row(WEEKLY_TITLE, 7.0, now + 3600, now, CLAUDE_COLOR),
        codex_session=missing_row(FIVE_HOUR_TITLE, CODEX_COLOR),
        codex_weekly=QuotaRowState(
            title=WEEKLY_TITLE,
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
    html = render_html(layout="compact", interval=30)

    assert '<body class="compact">' in html
    assert "const intervalMs = 30000;" in html
    assert "/api/usage" in html


def test_render_html_includes_full_panel_controls() -> None:
    html = render_html(layout="full", interval=60)

    assert 'data-product="claude"' in html
    assert 'data-product="codex"' in html
    assert 'data-layout="compact"' in html
    assert 'data-layout="horizontal"' in html
    assert 'id="themeToggle"' in html
    assert "usage.theme" in html
    assert "usage.layout" in html


def test_render_html_sets_horizontal_compact_mode() -> None:
    html = render_html(layout="horizontal", interval=30)

    assert '<body class="compact horizontal">' in html
    assert "body.compact.horizontal .grid" in html


def test_render_html_falls_back_to_full_layout() -> None:
    assert '<body class="full">' in render_html(layout="bad", interval=30)


def test_query_flag_accepts_horizontal_layout_aliases() -> None:
    assert _query_flag({"horizontal": ["1"]}, "horizontal") is True
    assert _query_flag({"layout": ["horizontal"]}, "horizontal") is True
    assert _query_flag({"horizontal": ["0"], "layout": ["vertical"]}, "horizontal") is False


def test_query_layout_accepts_root_page_layout_params() -> None:
    assert _query_layout({"layout": ["compact"]}) == "compact"
    assert _query_layout({"view": ["horizontal"]}) == "horizontal"
    assert _query_layout({"compact": ["true"]}) == "compact"
    assert _query_layout({"layout": ["bad"]}) == "full"
