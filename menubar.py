# mypy: disable-error-code="import-untyped,misc"
# PyObjC modules do not ship type stubs, and their base classes resolve to Any in mypy.
from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import objc
from AppKit import (
    NSAlert,
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMakePoint,
    NSMakeSize,
    NSMenu,
    NSMenuItem,
    NSMinYEdge,
    NSPopover,
    NSPopoverBehaviorTransient,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSViewController,
)
from Foundation import (
    NSBundle,
    NSObject,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSTimer,
)

import codex_loader
import panels
from panels.base import Panel as UsagePanel
from panels.base import load_active_panel_id, save_active_panel_id
from usage_client import ClaudeUsageClient, PollOutcome, PollState
from usage_rate import GROUP_NAMES, UsageRateTracker
from usage_state import (
    CLAUDE_COLOR,
    CODEX_COLOR,
    DANGER_COLOR,
    FIVE_HOUR_TITLE,
    WARN_COLOR,
    WEEKLY_TITLE,
    PopoverState,
    QuotaRowState,
    format_human_time,
)
from usage_state import (
    bar_color as _bar_color,
)
from usage_state import (
    empty_state as _empty_state,
)
from usage_state import (
    error_state as _error_state,
)
from usage_state import (
    format_percent as _format_percent,
)
from usage_state import (
    missing_row as _missing_row,
)
from usage_state import (
    quota_row as _quota_row,
)
from usage_state import (
    today_title as _today_title,
)

POPOVER_WIDTH = 364.0
CONTENT_HEIGHT = 574.0
PADDING = 14.0
TRACK_HEIGHT = 8.0
CARD_HEIGHT = 184.0
FOOTER_HEIGHT = 152.0
CARD_RADIUS = 18.0
CARD_HEADER_TOP = 22.0
CARD_ROW_TOP = 66.0
CARD_ROW_GAP = 64.0
CARD_SIDE_INSET = 18.0
SECTION_GAP = 14.0
FOOTER_GAP = 12.0
FOOTER_LINE_GAP = 18.0
BUTTON_TOP_GAP = 18.0
BUTTON_HEIGHT = 32.0
INSTALL_BUTTON_EXTRA_HEIGHT = BUTTON_HEIGHT + 10.0
logger = logging.getLogger(__name__)

__all__ = (
    "CLAUDE_COLOR",
    "CODEX_COLOR",
    "DANGER_COLOR",
    "WARN_COLOR",
    "PopoverState",
    "QuotaRowState",
    "format_human_time",
    "_bar_color",
    "_empty_state",
    "_error_state",
    "_format_percent",
    "_missing_row",
    "_quota_row",
    "_today_title",
    "run_app",
)


def _resolve_resource(name: str) -> str:
    bundle = NSBundle.mainBundle()
    if bundle is not None:
        stem, _, ext = name.rpartition(".")
        path = bundle.pathForResource_ofType_(stem, ext)
        if path:
            return str(path)
    return str(Path(__file__).parent / "assets" / name)


CLAUDE_ICON_PATH = _resolve_resource("claude.webp")
CODEX_ICON_PATH = _resolve_resource("codex.webp")

_APP_DELEGATE: AppDelegate | None = None


class PopoverViewController(NSViewController):
    content_view = objc.ivar()
    panel = objc.ivar()
    delegate = objc.ivar()

    def initWithPanel_delegate_(self, panel: UsagePanel, delegate: Any) -> PopoverViewController:
        self = objc.super(PopoverViewController, self).init()
        if self is None:
            return None
        self.panel = panel
        self.delegate = delegate
        self.content_view = panel.build_view(delegate)
        self.setView_(self.content_view)
        return self

    def rebuildWithPanel_(self, panel: UsagePanel) -> None:
        self.panel = panel
        self.content_view = panel.build_view(self.delegate)
        self.setView_(self.content_view)

    def setState_(self, state: PopoverState) -> None:
        self.view().setFrameSize_(_popover_size(state, self.panel))
        self.panel.apply_state(self.content_view, state)


class AppDelegate(NSObject):
    status_item = objc.ivar()
    popover = objc.ivar()
    popover_controller = objc.ivar()
    timer = objc.ivar()
    mock = objc.ivar()
    interval = objc.ivar()
    tracker = objc.ivar()
    latest_state = objc.ivar()
    active_panel = objc.ivar()
    codex_5h_pct = objc.ivar()
    _refresh_in_flight = objc.ivar()

    def initWithMock_interval_(self, mock: bool, interval: int) -> AppDelegate:
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.mock = mock
        self.interval = max(30, interval)
        self.tracker = UsageRateTracker(mock=mock)
        self.codex_5h_pct = None
        self.latest_state = _empty_state()
        self.active_panel = panels.get_panel(load_active_panel_id())
        self._refresh_in_flight = False
        return self

    def applicationDidFinishLaunching_(self, notification: Any) -> None:
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength,
        )
        button = self.status_item.button()
        button.setTitle_("🐾 ...")
        button.setTarget_(self)
        button.setAction_("togglePopover:")

        self.popover_controller = PopoverViewController.alloc().initWithPanel_delegate_(
            self.active_panel,
            self,
        )
        self.popover = NSPopover.alloc().init()
        self.popover.setBehavior_(NSPopoverBehaviorTransient)
        self.popover.setContentSize_(_popover_size(self.latest_state, self.active_panel))
        self.popover.setContentViewController_(self.popover_controller)

        self._refresh()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            self.interval,
            self,
            "timerFired:",
            None,
            True,
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def timerFired_(self, timer: Any) -> None:
        self._refresh()

    def refreshNow_(self, sender: Any) -> None:
        self._refresh()

    def installHook_(self, sender: Any) -> None:
        thread = threading.Thread(target=self._install_hook_in_background, daemon=True)
        thread.start()

    def quitApp_(self, sender: Any) -> None:
        if self.timer is not None:
            self.timer.invalidate()
        NSApp.terminate_(sender)

    def switchPanel_(self, sender: Any) -> None:
        menu = NSMenu.alloc().initWithTitle_("更換面板")
        for panel in panels.all_panels():
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                panel.display_name,
                "selectPanel:",
                "",
            )
            item.setTarget_(self)
            item.setRepresentedObject_(panel.id)
            item.setState_(1 if panel.id == self.active_panel.id else 0)
            menu.addItem_(item)
        menu.popUpMenuPositioningItem_atLocation_inView_(None, NSMakePoint(0, 0), sender)

    def selectPanel_(self, sender: Any) -> None:
        panel_id = str(sender.representedObject())
        self._set_active_panel_id(panel_id)

    def _set_active_panel_id(self, panel_id: str) -> None:
        panel = panels.get_panel(panel_id)
        save_active_panel_id(panel.id)
        self.active_panel = panel
        self.popover_controller.rebuildWithPanel_(panel)
        self.popover_controller.setState_(self.latest_state)
        self.popover.setContentSize_(_popover_size(self.latest_state, panel))

    def togglePopover_(self, sender: Any) -> None:
        if self.popover.isShown():
            self.popover.performClose_(sender)
            return
        self.popover_controller.setState_(self.latest_state)
        self.popover.setContentSize_(_popover_size(self.latest_state, self.active_panel))
        button = self.status_item.button()
        self.popover.showRelativeToRect_ofView_preferredEdge_(button.bounds(), button, NSMinYEdge)

    def _refresh(self) -> None:
        if self._refresh_in_flight:
            return
        self._refresh_in_flight = True
        thread = threading.Thread(target=self._refresh_in_background, daemon=True)
        thread.start()

    def _refresh_in_background(self) -> None:
        try:
            outcome = asyncio.run(self._fetch())
            codex_rows, codex_5h_pct = self._codex_rows()
            state = self._state_from_outcome(outcome, codex_rows)
        except Exception as exc:
            codex_5h_pct = None
            state = _error_state(type(exc).__name__, self.mock)

        result = {"state": state, "codex_5h_pct": codex_5h_pct}
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "_applyRefreshResult:",
            result,
            False,
        )

    def _applyRefreshResult_(self, result: dict[str, Any]) -> None:
        state = result["state"]
        codex_5h_pct = result["codex_5h_pct"]
        self.codex_5h_pct = codex_5h_pct
        self.latest_state = state
        self.popover_controller.setState_(state)
        self.popover.setContentSize_(_popover_size(state, self.active_panel))
        self.status_item.button().setTitle_(self._compose_title(state))
        self._refresh_in_flight = False

    def _install_hook_in_background(self) -> None:
        output = io.StringIO()
        exit_code = 1
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                import setup_hook

                exit_code = setup_hook.setup()
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
            if exc.code:
                print(exc.code, file=output)
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}", file=output)

        result = {
            "success": exit_code == 0,
            "message": output.getvalue().strip(),
        }
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "_finishHookInstall:",
            result,
            False,
        )

    def _finishHookInstall_(self, result: dict[str, Any]) -> None:
        alert = NSAlert.alloc().init()
        if result["success"]:
            alert.setMessageText_("已安裝完成，請重開 Claude Code 一次")
        else:
            alert.setMessageText_("安裝 hook 失敗")
            alert.setInformativeText_(result["message"] or "setup_hook.setup() 回傳失敗")
        alert.runModal()
        self._refresh()

    async def _fetch(self) -> PollOutcome:
        client = ClaudeUsageClient(mock=self.mock)
        try:
            return await client.fetch_once()
        finally:
            await client.aclose()

    def _state_from_outcome(
        self,
        outcome: PollOutcome,
        codex_rows: tuple[QuotaRowState, QuotaRowState],
    ) -> PopoverState:
        now = time.time()
        today_text = _today_title(self.mock)
        group_name = GROUP_NAMES[self.tracker.group()]
        status_text = f"狀態：{outcome.message or '載入中'}"

        if outcome.state == PollState.SUCCESS and outcome.snapshot is not None:
            snapshot = outcome.snapshot
            group_name = GROUP_NAMES[self.tracker.group()]
            claude_session = _quota_row(
                FIVE_HOUR_TITLE,
                float(snapshot.current_percent) if snapshot.current_percent is not None else None,
                snapshot.current_reset_at,
                now,
                CLAUDE_COLOR,
            )
            claude_weekly = _quota_row(
                WEEKLY_TITLE,
                float(snapshot.weekly_percent) if snapshot.weekly_percent is not None else None,
                snapshot.weekly_reset_at,
                now,
                CLAUDE_COLOR,
            )
            status_text = f"狀態：{outcome.message or '✓ 已同步'}"
        else:
            claude_session = _missing_row(FIVE_HOUR_TITLE, CLAUDE_COLOR)
            claude_weekly = _missing_row(WEEKLY_TITLE, CLAUDE_COLOR)
            status_text = f"狀態：{outcome.message or '無資料'}"

        return PopoverState(
            claude_session=claude_session,
            claude_weekly=claude_weekly,
            codex_session=codex_rows[0],
            codex_weekly=codex_rows[1],
            rate_text=f"速率：{group_name}",
            status_text=status_text,
            today_text=today_text,
            show_install_button=outcome.state == PollState.TOKEN_ERROR,
        )

    def _codex_rows(self) -> tuple[tuple[QuotaRowState, QuotaRowState], int | None]:
        if self.mock:
            now = time.time()
            rows = (
                _quota_row(
                    FIVE_HOUR_TITLE,
                    12.0,
                    now + (4 * 3600) + (15 * 60),
                    now,
                    CODEX_COLOR,
                ),
                _quota_row(WEEKLY_TITLE, 28.0, now + (4 * 86400), now, CODEX_COLOR),
            )
            return rows, 12

        try:
            rate_limits = codex_loader.load_rate_limits()
        except Exception:
            if os.environ.get("USAGE_DEBUG") == "1":
                logger.warning("codex rate limits load failed", exc_info=True)
            rate_limits = None

        if rate_limits is None:
            rows = _missing_row(FIVE_HOUR_TITLE, CODEX_COLOR), _missing_row(
                WEEKLY_TITLE,
                CODEX_COLOR,
            )
            return rows, None

        now = time.time()
        codex_5h_pct = (
            round(rate_limits.five_hour_pct) if rate_limits.five_hour_pct is not None else None
        )
        rows = (
            _quota_row(
                FIVE_HOUR_TITLE,
                rate_limits.five_hour_pct,
                rate_limits.five_hour_resets_at,
                now,
                CODEX_COLOR,
            ),
            _quota_row(
                WEEKLY_TITLE,
                rate_limits.seven_day_pct,
                rate_limits.seven_day_resets_at,
                now,
                CODEX_COLOR,
            ),
        )
        return rows, codex_5h_pct

    def _compose_title(self, state: PopoverState) -> str:
        claude_text = state.claude_session.percent_text.replace(" 已用", "")
        base = "🐾 --" if claude_text == "--" else f"🐾 {claude_text}"
        if self.codex_5h_pct is None:
            return base
        return f"{base} · 📜 {self.codex_5h_pct}%"


def run_app(mock: bool = False, interval: int = 60) -> None:
    global _APP_DELEGATE
    app = NSApplication.sharedApplication()
    _APP_DELEGATE = AppDelegate.alloc().initWithMock_interval_(mock, interval)
    app.setDelegate_(_APP_DELEGATE)
    app.run()


def _popover_size(state: PopoverState, panel: UsagePanel | None = None) -> Any:
    active_panel = panel if panel is not None else panels.get_panel("classic")
    width, base_height = active_panel.preferred_size()
    height = base_height + (INSTALL_BUTTON_EXTRA_HEIGHT if state.show_install_button else 0.0)
    return NSMakeSize(width, height)
