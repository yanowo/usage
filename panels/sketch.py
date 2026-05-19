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

BG = (0.965, 0.720, 0.620)
CARD_FILL = (1.000, 0.985, 0.965)
CARD_BORDER = (0.085, 0.070, 0.070)
TEXT = (0.080, 0.065, 0.065)
MUTED = (0.380, 0.340, 0.330)
CLAUDE_ACC = (0.900, 0.300, 0.160)
CODEX_ACC = (0.040, 0.560, 0.520)

CARD_X = 20.0
CARD_WIDTH = 324.0
CARD_HEIGHT = 200.0
CARD_RADIUS = 10.0

CLAUDE_CARD_Y = 16.0
CODEX_CARD_Y = 228.0
FOOTER_CARD_Y = 440.0
FOOTER_CARD_HEIGHT = 96.0

BUTTON_ROW_Y = 548.0
BUTTON_ROW_HEIGHT = 34.0
BUTTON_WIDTH = (CARD_WIDTH - 16.0) / 3.0
BUTTON_RADIUS = 8.0

CARD_BORDER_WIDTH = 2.5
BUTTON_BORDER_WIDTH = 2.0
PROGRESS_HEIGHT = 4.0
DOT_RADIUS = 4.0
DOT_INSET = 7.0


def _rgb(color: tuple[float, float, float], alpha: float = 1.0) -> NSColor:
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(*color, alpha)


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


def _draw_hline(x: float, y: float, width: float, color: NSColor) -> None:
    color.setFill()
    NSRectFill(NSMakeRect(x, y, width, 1.0))


def _draw_pin_dots(card_x: float, card_y: float, card_w: float, card_h: float) -> None:
    dot_positions = [
        (card_x + DOT_INSET, card_y + DOT_INSET),
        (card_x + card_w - DOT_INSET, card_y + DOT_INSET),
        (card_x + DOT_INSET, card_y + card_h - DOT_INSET),
        (card_x + card_w - DOT_INSET, card_y + card_h - DOT_INSET),
    ]
    _rgb(CARD_BORDER).setFill()
    for x, y in dot_positions:
        dot_rect = NSMakeRect(x - DOT_RADIUS, y - DOT_RADIUS, DOT_RADIUS * 2.0, DOT_RADIUS * 2.0)
        NSBezierPath.bezierPathWithOvalInRect_(dot_rect).fill()


class SketchButton(NSButton):
    fill_color = objc.ivar()
    text_color = objc.ivar()
    border_color = objc.ivar()

    def initWithFrame_title_fill_text_border_target_action_(
        self,
        frame: Any,
        title: str,
        fill_color: NSColor,
        text_color: NSColor,
        border_color: NSColor,
        target: Any,
        action: str,
    ) -> SketchButton:
        self = objc.super(SketchButton, self).initWithFrame_(frame)
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
        self.border_color.setStroke()
        path.setLineWidth_(BUTTON_BORDER_WIDTH)
        path.stroke()
        _draw_text(
            str(self.title()),
            NSMakeRect(0, 7.0, bounds.size.width, 18.0),
            self.text_color,
            13.5,
            0.70,
            NSTextAlignmentCenter,
        )


class SketchContentView(NSView):
    delegate = objc.ivar()
    state = objc.ivar()
    refresh_button = objc.ivar()
    quit_button = objc.ivar()
    switch_button = objc.ivar()
    install_hook_button = objc.ivar()

    def initWithFrame_delegate_(self, frame: Any, delegate: Any) -> SketchContentView:
        self = objc.super(SketchContentView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.delegate = delegate
        self.state = None

        fill = _rgb((1.0, 1.0, 1.0))
        text = NSColor.blackColor()
        border = _rgb(CARD_BORDER, 0.85)

        self.refresh_button = (
            SketchButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "立即更新",
                fill,
                text,
                border,
                delegate,
                "refreshNow:",
            )
        )
        self.quit_button = (
            SketchButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "結束",
                fill,
                text,
                border,
                delegate,
                "quitApp:",
            )
        )
        self.switch_button = (
            SketchButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "切換面板",
                fill,
                text,
                border,
                delegate,
                "switchPanel:",
            )
        )
        self.install_hook_button = (
            SketchButton.alloc().initWithFrame_title_fill_text_border_target_action_(
                NSMakeRect(0, 0, BUTTON_WIDTH, BUTTON_ROW_HEIGHT),
                "安裝 Hook",
                fill,
                text,
                border,
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
        self.refresh_button.setFrame_(
            NSMakeRect(20.0, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )
        self.install_hook_button.setFrame_(
            NSMakeRect(20.0, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )
        self.quit_button.setFrame_(
            NSMakeRect(130.67, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )
        self.switch_button.setFrame_(
            NSMakeRect(241.34, BUTTON_ROW_Y, BUTTON_WIDTH, BUTTON_ROW_HEIGHT)
        )

    def drawRect_(self, dirty_rect: Any) -> None:
        _rgb(BG).setFill()
        NSRectFill(self.bounds())
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
        _rgb(CARD_FILL).setFill()
        fill_rounded_rect(card_rect, CARD_RADIUS)
        _rgb(CARD_BORDER).setStroke()
        stroke_rounded_rect(card_rect, CARD_RADIUS, CARD_BORDER_WIDTH)
        _draw_pin_dots(CARD_X, card_y, CARD_WIDTH, CARD_HEIGHT)

        _draw_text(
            title,
            NSMakeRect(40.0, card_y + 13.0, 180.0, 16.0),
            _rgb(TEXT),
            10.0,
            0.75,
        )
        _draw_hline(40.0, card_y + 28.0, 284.0, _rgb(CARD_BORDER, 0.18))

        self._draw_row(rows[0], accent, card_y, True)
        _draw_hline(40.0, card_y + 120.0, 284.0, _rgb(CARD_BORDER, 0.18))
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
        progress_y = card_y + (93.0 if is_session else 175.0)
        reset_y = card_y + (101.0 if is_session else 183.0)
        number_size = 26.0 if is_session else 24.0
        number_weight = 0.70 if is_session else 0.60
        number_color = accent if row.available else _rgb(TEXT)

        _draw_text(
            row.title.upper(),
            NSMakeRect(40.0, label_y, 120.0, 16.0),
            _rgb(MUTED),
            10.0,
            0.45,
        )
        _draw_text(
            row.percent_text,
            NSMakeRect(40.0, number_y, 200.0, 28.0),
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
            0.25,
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
        track_rect = NSMakeRect(x, y, width, PROGRESS_HEIGHT)
        _rgb(CARD_BORDER, 0.12).setFill()
        fill_rounded_rect(track_rect, PROGRESS_HEIGHT / 2.0)

        fill_width = _progress_fill_width(percent, width)
        if fill_width <= 0:
            return
        fill_rect = NSMakeRect(x, y, fill_width, PROGRESS_HEIGHT)
        accent.setFill()
        fill_rounded_rect(fill_rect, PROGRESS_HEIGHT / 2.0)

    def _draw_footer_card(self) -> None:
        footer_rect = NSMakeRect(CARD_X, FOOTER_CARD_Y, CARD_WIDTH, FOOTER_CARD_HEIGHT)
        _rgb(CARD_FILL).setFill()
        fill_rounded_rect(footer_rect, CARD_RADIUS)
        _rgb(CARD_BORDER).setStroke()
        stroke_rounded_rect(footer_rect, CARD_RADIUS, CARD_BORDER_WIDTH)
        _draw_pin_dots(CARD_X, FOOTER_CARD_Y, CARD_WIDTH, FOOTER_CARD_HEIGHT)

        state = self.state
        if state is None:
            return

        inner_x = CARD_X + 16.0
        inner_w = CARD_WIDTH - 32.0
        row_ys = [454.0, 478.0, 502.0]
        div_ys = [474.0, 498.0]
        texts = [state.rate_text, state.status_text, state.today_text]

        for text, row_y in zip(texts, row_ys, strict=True):
            if "：" in text:
                lbl, val = text.split("：", 1)
            else:
                lbl, val = "", text
            _draw_text(lbl, NSMakeRect(inner_x, row_y, inner_w, 18.0), _rgb(MUTED), 11.0, 0.35)
            _draw_text(
                val,
                NSMakeRect(inner_x, row_y, inner_w, 18.0),
                _rgb(TEXT),
                11.0,
                0.50,
                NSTextAlignmentRight,
            )

        for div_y in div_ys:
            _draw_hline(inner_x, div_y, inner_w, _rgb(CARD_BORDER, 0.18))

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


class SketchPanel:
    id = "sketch"
    display_name = "手繪"

    def build_view(self, delegate: Any) -> NSView:
        width, height = self.preferred_size()
        return SketchContentView.alloc().initWithFrame_delegate_(
            NSMakeRect(0, 0, width, height),
            delegate,
        )

    def apply_state(self, view: NSView, state: PopoverState) -> None:
        view.setState_(state)

    def preferred_size(self) -> tuple[float, float]:
        return (POPOVER_WIDTH, CONTENT_HEIGHT)
