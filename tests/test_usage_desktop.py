from __future__ import annotations

import usage_desktop
from usage_state import CLAUDE_COLOR, CODEX_COLOR, PopoverState, QuotaRowState, missing_row


def _state() -> PopoverState:
    claude = QuotaRowState(
        title="Session",
        percent=42.0,
        percent_text="42% 已用",
        reset_text="重置 1h 0m",
        color=CLAUDE_COLOR,
    )
    codex = QuotaRowState(
        title="Session",
        percent=9.0,
        percent_text="9% 已用",
        reset_text="重置 4h 0m",
        color=CODEX_COLOR,
    )
    return PopoverState(
        claude_session=claude,
        claude_weekly=missing_row("Weekly", CLAUDE_COLOR),
        codex_session=codex,
        codex_weekly=missing_row("Weekly", CODEX_COLOR),
        rate_text="速率：Idle",
        status_text="狀態：ok",
        today_text="今日：$0.00 (0 tokens)",
    )


def test_rgb_to_hex() -> None:
    assert usage_desktop.rgb_to_hex((1.0, 0.5, 0.0)) == "#ff8000"


def test_normalize_product() -> None:
    assert usage_desktop.normalize_product("claude") == "claude"
    assert usage_desktop.normalize_product("bad") == "all"


def test_template_helpers() -> None:
    assert usage_desktop.normalize_template("matrix") == "matrix"
    assert usage_desktop.normalize_template("missing") == usage_desktop.DEFAULT_TEMPLATE_ID
    assert usage_desktop.template_palette("sketch").bg == "#f6b89e"
    assert usage_desktop.next_template_id("sketch") == "classic"
    assert usage_desktop.next_template_id("missing") == "sketch"


def test_window_setting_helpers() -> None:
    assert usage_desktop.clamp_opacity(0.2) == usage_desktop.MIN_OPACITY
    assert usage_desktop.clamp_opacity(0.75) == 0.75
    assert usage_desktop.clamp_opacity(1.5) == 1.0
    assert usage_desktop.resize_dimensions(400, 500, 30, -900) == (
        430,
        usage_desktop.MIN_HEIGHT,
    )
    assert usage_desktop.resize_dimensions(
        260,
        130,
        -80,
        -40,
        min_width=usage_desktop.MINI_WIDTH,
        min_height=usage_desktop.MINI_HEIGHT,
    ) == (usage_desktop.MINI_WIDTH, usage_desktop.MINI_HEIGHT)
    assert usage_desktop.top_left_resize_geometry(80, 90, 400, 500, -30, 40) == (
        430,
        usage_desktop.MIN_HEIGHT,
        50,
        110,
    )
    assert usage_desktop.top_left_resize_geometry(80, 90, 400, 500, 300, 300) == (
        usage_desktop.MIN_WIDTH,
        usage_desktop.MIN_HEIGHT,
        150,
        110,
    )
    assert usage_desktop.mini_product("all") == "codex"
    assert usage_desktop.mini_product("claude") == "claude"
    assert usage_desktop.topmost_label(True) == "Pinned"
    assert usage_desktop.topmost_label(False) == "Pin"


def test_selected_product_views() -> None:
    state = _state()

    assert [view.key for view in usage_desktop.selected_product_views(state, "all")] == [
        "claude",
        "codex",
    ]
    assert [view.key for view in usage_desktop.selected_product_views(state, "claude")] == [
        "claude"
    ]
    assert [view.key for view in usage_desktop.selected_product_views(state, "codex")] == ["codex"]


def test_progress_fraction() -> None:
    assert usage_desktop.progress_fraction(_state().claude_session) == 0.42
    assert usage_desktop.progress_fraction(missing_row("Session", CLAUDE_COLOR)) == 0.0


def test_clean_label_removes_common_prefixes() -> None:
    assert usage_desktop.clean_label("狀態：ok") == "ok"
    assert usage_desktop.clean_label("速率：Idle") == "Idle"
    assert usage_desktop.clean_label("今日：$0.00") == "$0.00"
