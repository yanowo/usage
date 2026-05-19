# mypy: disable-error-code="import-untyped,misc"
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import objc
from AppKit import (
    NSBezierPath,
    NSButton,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
    NSRectFill,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSView,
)
from Foundation import NSMutableDictionary, NSString

from panels.base import POPOVER_WIDTH, fill_rounded_rect, stroke_rounded_rect

if TYPE_CHECKING:
    from menubar import PopoverState, QuotaRowState

CONTENT_HEIGHT = 590.0

BG = (0.040, 0.040, 0.048)
CARD_BG = (0.090, 0.090, 0.105)
TEXT = (0.960, 0.960, 0.970)
MUTED = (0.380, 0.380, 0.420)
CLAUDE_ACC = (0.957, 0.573, 0.431)
CODEX_ACC = (0.345, 0.839, 0.902)

CARD_X = 20.0
CARD_WIDTH = 324.0
CARD_HEIGHT = 200.0
CARD_RADIUS = 12.0

CLAUDE_CARD_Y = 16.0
CODEX_CARD_Y = 228.0
FOOTER_CARD_Y = 440.0
FOOTER_CARD_HEIGHT = 96.0

BUTTON_ROW_Y = 548.0
BUTTON_ROW_HEIGHT = 34.0
BUTTON_GAP = 8.0
BUTTON_WIDTH = (CARD_WIDTH - (BUTTON_GAP * 2)) / 3.0
BUTTON_RADIUS = 8.0

CARD_BORDER_ALPHA = 0.06
TRACK_ALPHA = 0.08
PRIMARY_ALPHA = 0.90


def _rgb(color: tuple[float, float, float], alpha: float = 1.0) -> NSColor:
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(*color, alpha)


def _white(alpha: float) -> NSColor:
    return NSColor.whiteColor().colorWithAlphaComponent_(alpha)


def _font(size: float, weight: float) -> NSFont:
    return NSFont.systemFontOfSize_weight_(size, weight)


def _paragraph_style(alignment: int | None = None) -> Any:
    style = NSMutableParagraphStyle.alloc().init()
    if alignment is not None:
        style.setAlignment_(alignment)
    return style


def _draw_text(
    text: str,
    rect: Any,
    color: NSColor,
    size: float,
    weight: float,
    alignment: int | None = None,
) -> None:
    attrs = NSMutableDictionary.dictionaryWithDictionary_(
        {
            NSForegroundColorAttributeName: color,
            NSFontAttributeName: _font(size, weight),
            NSParagraphStyleAttributeName: _paragraph_style(alignment),
        }
    )
    NSString.stringWithString_(text).drawInRect_withAttributes_(rect, attrs)


def _draw_hline(x: float, y: float, width: float) -> None:
    _white(CARD_BORDER_ALPHA).setFill()
    NSRectFill(NSMakeRect(x, y, width, 1.0))


def _progress_fill_width(percent: float | None, width: float) -> float:
    if percent is None:
        return 0.0
    pct = max(0.0, min(100.0, float(percent)))
    return width * pct / 100.0


def _placeholder_row(title: str) -> Any:
    return SimpleNamespace(
        title=title,
        percent=None,
        percent_text="--",
        reset_text="重置 --",
        available=False,
    )


class MinimalButton(NSButton):
    fill_color = objc.ivar()
    text_color = objc.ivar()
    border_color = objc.ivar()

    def initWithFrame_title_fill_text_border_target_action_(
        self,
        frame: Any,
        title: str,
        fill_color: NSColor,
        text_color: NSColor,
        border_color: NSColor | None,
        target: Any,
        action: str,
    ) -> MinimalButton:
        self = objc.super(MinimalButton, self).initWithFrame_(frame)
        if self is None:
            return None
        self.fill_color = fill_color
        self.text_color = text_color
        self.border_color = border_color
        self.setTitle_(title)
        self.setBordered_(False)
        self.setTarget_(target)
        self.setAction_(action)
        return self

    def drawRect_(self, dirty_rect: Any) -> None:
        bounds = self.bounds()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds,
            BUTTON_RADIUS,
            BUTTON_RADIUS,
        )
        self.fill_color.setFill()
        path.fill()
        if self.border_color is not None:
            self.border_color.setStroke()
            path.setLineWidth_(1.0)
            path.stroke()
        _draw_text(
            str(self.title()),
            NSMakeRect(0, 8.0, bounds.size.width, 16.0),
            self.text_color,
            12.5,
            0.32,
            NSTextAlignmentCenter,
        )


class MinimalContentView(NSView):
    delegate = objc.ivar()
    state = objc.ivar()
    refresh_button = objc.ivar()
    quit_button = objc.ivar()
    switch_button = objc.ivar()
    install_hook_button = objc.ivar()

    def initWithFrame_delegate_(self, frame: Any, delegate: Any) -> MinimalContentView:
        self = objc.super(MinimalContentView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.delegate = delegate
        self.state = None

        border = _white(CARD_BORDER_ALPHA)
        secondary_fill = _rgb(CARD_BG)
        secondary_text = _rgb(TEXT)
        primary_fill = _rgb(CLAUDE_ACC, PRIMARY_ALPHA)
        primary_text = _rgb(BG)

        self.refresh_button = (
            MinimalButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "立即更新",
                primary_fill,
                primary_text,
                None,
                delegate,
                "refreshNow:",
            )
        )
        self.quit_button = (
            MinimalButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "結束",
                secondary_fill,
                secondary_text,
                border,
                delegate,
                "quitApp:",
            )
        )
        self.switch_button = (
            MinimalButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "切換面板",
                secondary_fill,
                secondary_text,
                border,
                delegate,
                "switchPanel:",
            )
        )
        self.install_hook_button = (
            MinimalButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "安裝 Hook",
                primary_fill,
                primary_text,
                None,
                delegate,
                "installHook:",
            )
        )
        self.install_hook_button.setHidden_(True)

        for view in (
            self.refresh_button,
            self.quit_button,
            self.switch_button,
            self.install_hook_button,
        ):
            self.addSubview_(view)
        return self

    def isFlipped(self) -> bool:
        return True

    def layout(self) -> None:
        left_x = CARD_X
        middle_x = CARD_X + BUTTON_WIDTH + BUTTON_GAP
        right_x = CARD_X + ((BUTTON_WIDTH + BUTTON_GAP) * 2)
        self.refresh_button.setFrame_(
            NSMakeRect(left_x, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )
        self.install_hook_button.setFrame_(
            NSMakeRect(left_x, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )
        self.quit_button.setFrame_(
            NSMakeRect(middle_x, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )
        self.switch_button.setFrame_(
            NSMakeRect(right_x, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )

    def drawRect_(self, dirty_rect: Any) -> None:
        bounds = self.bounds()
        _rgb(BG).setFill()
        NSRectFill(bounds)

        self._draw_quota_card("CLAUDE CODE", CLAUDE_CARD_Y, _rgb(CLAUDE_ACC), self._claude_rows())
        self._draw_quota_card("CODEX", CODEX_CARD_Y, _rgb(CODEX_ACC), self._codex_rows())
        self._draw_footer_card()

    def _draw_quota_card(
        self,
        title: str,
        card_y: float,
        accent: NSColor,
        rows: tuple[QuotaRowState, QuotaRowState],
    ) -> None:
        card_rect = NSMakeRect(CARD_X, card_y, CARD_WIDTH, CARD_HEIGHT)
        _rgb(CARD_BG).setFill()
        fill_rounded_rect(card_rect, CARD_RADIUS)
        _white(CARD_BORDER_ALPHA).setStroke()
        stroke_rounded_rect(card_rect, CARD_RADIUS, 1.0)

        _draw_text(
            title, NSMakeRect(36.0, card_y + 13.0, 200.0, 18.0), _rgb(TEXT, 0.65), 13.0, 0.28
        )
        _draw_hline(40.0, card_y + 28.0, 284.0)

        self._draw_row(rows[0], accent, card_y, True)
        _draw_hline(40.0, card_y + 120.0, 284.0)
        self._draw_row(rows[1], accent, card_y, False)

    def _draw_row(
        self,
        row: QuotaRowState,
        accent: NSColor,
        card_y: float,
        is_session: bool,
    ) -> None:
        label_y = card_y + (36.0 if is_session else 122.0)
        number_y = card_y + (53.0 if is_session else 139.0)
        number_height = 26.0
        progress_y = number_y + number_height + (14.0 if is_session else 10.0)
        reset_y = progress_y + (8.0 if is_session else 6.0)
        number_size = 26.0 if is_session else 24.0
        number_weight = 0.6 if is_session else 0.5
        number_color = accent if row.available else _rgb(TEXT)

        _draw_text(
            row.title.upper(),
            NSMakeRect(40.0, label_y, 120.0, 13.0),
            _rgb(MUTED),
            9.5,
            -0.2,
        )
        _draw_text(
            row.percent_text,
            NSMakeRect(40.0, number_y, 200.0, number_height),
            number_color,
            number_size,
            number_weight,
        )
        self._draw_progress_bar(40.0, progress_y, 284.0, row.percent, accent)
        _draw_text(
            row.reset_text,
            NSMakeRect(150.0, reset_y, 174.0, 14.0),
            _rgb(MUTED),
            10.0,
            -0.2,
            NSTextAlignmentRight,
        )

    def _draw_progress_bar(
        self,
        x: float,
        y: float,
        width: float,
        percent: float | None,
        accent: NSColor,
    ) -> None:
        track_rect = NSMakeRect(x, y, width, 2.0)
        _white(TRACK_ALPHA).setFill()
        fill_rounded_rect(track_rect, 1.0)

        fill_width = _progress_fill_width(percent, width)
        if fill_width <= 0:
            return
        fill_rect = NSMakeRect(x, y, fill_width, 2.0)
        accent.setFill()
        fill_rounded_rect(fill_rect, 1.0)

    def _draw_footer_card(self) -> None:
        footer_rect = NSMakeRect(CARD_X, FOOTER_CARD_Y, CARD_WIDTH, FOOTER_CARD_HEIGHT)
        _rgb(CARD_BG).setFill()
        fill_rounded_rect(footer_rect, CARD_RADIUS)
        _white(CARD_BORDER_ALPHA).setStroke()
        stroke_rounded_rect(footer_rect, CARD_RADIUS, 1.0)

        state = self.state
        if state is None:
            return

        inner_x = CARD_X + 16.0
        inner_w = CARD_WIDTH - 32.0
        row_ys = [FOOTER_CARD_Y + 14.0, FOOTER_CARD_Y + 38.0, FOOTER_CARD_Y + 62.0]
        div_ys = [FOOTER_CARD_Y + 34.0, FOOTER_CARD_Y + 58.0]
        texts = [state.rate_text, state.status_text, state.today_text]

        for text, row_y in zip(texts, row_ys, strict=True):
            if "：" in text:
                lbl, val = text.split("：", 1)
            else:
                lbl, val = "", text
            _draw_text(lbl, NSMakeRect(inner_x, row_y, inner_w, 18.0), _rgb(MUTED), 11.0, -0.2)
            _draw_text(
                val,
                NSMakeRect(inner_x, row_y, inner_w, 18.0),
                _rgb(TEXT),
                11.0,
                0.0,
                NSTextAlignmentRight,
            )

        for div_y in div_ys:
            _draw_hline(inner_x, div_y, inner_w)

    def _claude_rows(self) -> tuple[QuotaRowState, QuotaRowState]:
        state = self.state
        if state is None:
            return (_placeholder_row("Session"), _placeholder_row("Weekly"))
        return (state.claude_session, state.claude_weekly)

    def _codex_rows(self) -> tuple[QuotaRowState, QuotaRowState]:
        state = self.state
        if state is None:
            return (_placeholder_row("Session"), _placeholder_row("Weekly"))
        return (state.codex_session, state.codex_weekly)

    def setState_(self, state: PopoverState) -> None:
        self.state = state
        show_install = bool(state.show_install_button)
        self.install_hook_button.setHidden_(not show_install)
        self.refresh_button.setHidden_(show_install)
        self.setNeedsLayout_(True)
        self.setNeedsDisplay_(True)


class MinimalPanel:
    id = "minimal"
    display_name = "Minimal"

    def build_view(self, delegate: Any) -> NSView:
        width, height = self.preferred_size()
        return MinimalContentView.alloc().initWithFrame_delegate_(
            NSMakeRect(0, 0, width, height),
            delegate,
        )

    def apply_state(self, view: NSView, state: PopoverState) -> None:
        view.setState_(state)

    def preferred_size(self) -> tuple[float, float]:
        return (POPOVER_WIDTH, CONTENT_HEIGHT)
