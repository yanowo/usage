# mypy: disable-error-code="import-untyped,misc"
from __future__ import annotations

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
from Foundation import NSMutableDictionary, NSString, NSTimer

from panels.base import (
    BUTTON_HEIGHT,
    POPOVER_WIDTH,
    fill_rounded_rect,
    label,
    ns_color,
    stroke_rounded_rect,
)

if TYPE_CHECKING:
    from menubar import PopoverState, QuotaRowState

BACKGROUND = (0.01, 0.06, 0.05)
PANEL_FILL = (0.02, 0.12, 0.10, 0.96)
PANEL_BORDER = (0.22, 0.62, 0.50, 0.45)
GRID_COLOR = (0.09, 0.35, 0.28, 0.50)
TEXT_MAIN = (0.85, 1.0, 0.94)
TEXT_MUTED = (0.48, 0.81, 0.72)
CLAUDE_WAVE = (0.20, 1.0, 0.72, 1.0)
CODEX_WAVE = (0.14, 0.83, 1.0, 1.0)
BUTTON_FILL = (0.03, 0.17, 0.14, 0.98)
BUTTON_BORDER = (0.28, 0.70, 0.58, 0.52)
PADDING = 16.0
INFO_HEIGHT = 92.0
SECTION_GAP = 12.0
BUTTON_GAP = 10.0
ACTION_TOP_GAP = 14.0
BOTTOM_PADDING = 16.0
MONITOR_INSET = 14.0
MONITOR_BOTTOM_INSET = 14.0
LEAD_HEADER_HEIGHT = 18.0
LEAD_BLOCK_GAP = 10.0
LEAD_SUMMARY_GAP = 4.0
LEAD_WAVE_GAP = 8.0
WAVE_HEIGHT = 48.0
SUMMARY_ROW_HEIGHT = 34.0
SUMMARY_BLOCK_HEIGHT = (SUMMARY_ROW_HEIGHT * 2) + LEAD_SUMMARY_GAP
LEAD_TEXT_HEIGHT = LEAD_HEADER_HEIGHT + 8.0 + SUMMARY_BLOCK_HEIGHT
LEAD_SECTION_HEIGHT = LEAD_TEXT_HEIGHT + LEAD_WAVE_GAP + WAVE_HEIGHT
MONITOR_HEIGHT = (
    MONITOR_INSET
    + LEAD_SECTION_HEIGHT
    + LEAD_BLOCK_GAP
    + LEAD_SECTION_HEIGHT
    + MONITOR_BOTTOM_INSET
)
PANEL_BASE_HEIGHT = (
    PADDING
    + MONITOR_HEIGHT
    + SECTION_GAP
    + INFO_HEIGHT
    + ACTION_TOP_GAP
    + BUTTON_HEIGHT
    + BOTTOM_PADDING
)


def _rgba(color: tuple[float, float, float, float]) -> NSColor:
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(*color)


def _font(size: float, weight: float) -> NSFont:
    try:
        return NSFont.monospacedSystemFontOfSize_weight_(size, weight)
    except Exception:
        fallback = NSFont.fontWithName_size_("Menlo", size)
        if fallback is not None:
            return fallback
        return NSFont.systemFontOfSize_weight_(size, weight)


def _mono_label(
    text: str,
    size: float,
    color: NSColor,
    alignment: int | None = None,
    weight: float = 0.28,
) -> Any:
    return label(text, _font(size, weight), color, alignment)


def _suffix(text: str) -> str:
    if "：" in text:
        return text.split("：", 1)[1].strip()
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text.strip()


def _pulse_profile(rate_text: str) -> tuple[float, float]:
    lowered = rate_text.lower()
    if "heavy" in lowered:
        return (1.0, 1.85)
    if "active" in lowered:
        return (0.74, 1.45)
    if "normal" in lowered:
        return (0.48, 1.10)
    return (0.18, 0.72)


def _ecg_shape(progress: float) -> float:
    if progress < 0.12:
        return 0.0
    if progress < 0.18:
        return (progress - 0.12) / 0.06 * 0.16
    if progress < 0.24:
        return 0.16 - ((progress - 0.18) / 0.06 * 0.18)
    if progress < 0.28:
        return -((progress - 0.24) / 0.04) * 0.22
    if progress < 0.32:
        return -0.22 + ((progress - 0.28) / 0.04) * 1.30
    if progress < 0.36:
        return 1.08 - ((progress - 0.32) / 0.04) * 1.56
    if progress < 0.42:
        return -0.48 + ((progress - 0.36) / 0.06) * 0.52
    if progress < 0.54:
        return ((progress - 0.42) / 0.12) * 0.18
    if progress < 0.68:
        return 0.18 - ((progress - 0.54) / 0.14) * 0.18
    return 0.0


def _wave_baselines(height: float) -> tuple[float, float]:
    claude_wave_top = MONITOR_INSET + LEAD_TEXT_HEIGHT + LEAD_WAVE_GAP
    codex_wave_top = (
        MONITOR_INSET + LEAD_SECTION_HEIGHT + LEAD_BLOCK_GAP + LEAD_TEXT_HEIGHT + LEAD_WAVE_GAP
    )
    return (
        claude_wave_top + (WAVE_HEIGHT / 2.0),
        codex_wave_top + (WAVE_HEIGHT / 2.0),
    )


class ECGActionButton(NSButton):
    fill_color = objc.ivar()
    border_color = objc.ivar()
    text_color = objc.ivar()

    def initWithFrame_title_target_action_(
        self,
        frame: Any,
        title: str,
        target: Any,
        action: str,
    ) -> ECGActionButton:
        self = objc.super(ECGActionButton, self).initWithFrame_(frame)
        if self is None:
            return None
        self.fill_color = _rgba(BUTTON_FILL)
        self.border_color = _rgba(BUTTON_BORDER)
        self.text_color = ns_color(TEXT_MAIN)
        self.setTitle_(title)
        self.setBordered_(False)
        self.setTarget_(target)
        self.setAction_(action)
        return self

    def drawRect_(self, dirty_rect: Any) -> None:
        bounds = self.bounds()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, 8.0, 8.0)
        self.fill_color.setFill()
        path.fill()
        self.border_color.setStroke()
        path.setLineWidth_(1.0)
        path.stroke()

        style = NSMutableParagraphStyle.alloc().init()
        style.setAlignment_(NSTextAlignmentCenter)
        attrs = NSMutableDictionary.dictionaryWithDictionary_(
            {
                NSForegroundColorAttributeName: self.text_color,
                NSParagraphStyleAttributeName: style,
                NSFontAttributeName: _font(13.5, 0.32),
            },
        )
        NSString.stringWithString_(str(self.title())).drawInRect_withAttributes_(
            NSMakeRect(0, 8.0, bounds.size.width, 16.0),
            attrs,
        )


class ECGQuotaSummaryView(NSView):
    title_label = objc.ivar()
    percent_label = objc.ivar()
    reset_label = objc.ivar()

    def initWithFrame_color_(self, frame: Any, color: NSColor) -> ECGQuotaSummaryView:
        self = objc.super(ECGQuotaSummaryView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.title_label = _mono_label("", 13.0, ns_color(TEXT_MAIN), weight=0.32)
        self.percent_label = _mono_label("", 13.0, color, NSTextAlignmentRight, 0.38)
        self.reset_label = _mono_label("", 11.5, ns_color(TEXT_MUTED), weight=0.22)
        for view in (self.title_label, self.percent_label, self.reset_label):
            self.addSubview_(view)
        return self

    def isFlipped(self) -> bool:
        return True

    def layout(self) -> None:
        width = self.bounds().size.width
        self.title_label.setFrame_(NSMakeRect(0, 0, width * 0.58, 17))
        self.percent_label.setFrame_(NSMakeRect(width * 0.58, 0, width * 0.42, 17))
        self.reset_label.setFrame_(NSMakeRect(0, 19, width, 14))

    def setRowState_(self, row: QuotaRowState) -> None:
        self.title_label.setStringValue_(row.title)
        self.percent_label.setStringValue_(row.percent_text)
        self.reset_label.setStringValue_(row.reset_text)
        self.setNeedsLayout_(True)


class ECGMonitorView(NSView):
    timer = objc.ivar()
    phase = objc.ivar()
    speed_factor = objc.ivar()
    claude_amplitude = objc.ivar()
    codex_amplitude = objc.ivar()

    def initWithFrame_(self, frame: Any) -> ECGMonitorView:
        self = objc.super(ECGMonitorView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.phase = 0.0
        self.speed_factor = 0.72
        self.claude_amplitude = 0.18
        self.codex_amplitude = 0.18
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.08,
            self,
            "tick:",
            None,
            True,
        )
        return self

    def isFlipped(self) -> bool:
        return True

    def viewWillMoveToWindow_(self, window: Any) -> None:
        if window is None and self.timer is not None:
            self.timer.invalidate()
            self.timer = None

    def tick_(self, sender: Any) -> None:
        self.phase = float(self.phase) + float(self.speed_factor) * 0.055
        self.setNeedsDisplay_(True)

    def updateWithClaudePercent_codexPercent_rateText_(
        self,
        claude_percent: float | None,
        codex_percent: float | None,
        rate_text: str,
    ) -> None:
        intensity, speed = _pulse_profile(rate_text)
        claude_pct = max(0.0, min(100.0, claude_percent or 0.0))
        codex_pct = max(0.0, min(100.0, codex_percent or 0.0))
        self.speed_factor = speed
        self.claude_amplitude = 0.08 + (claude_pct / 100.0 * 0.92 * intensity)
        self.codex_amplitude = 0.08 + (codex_pct / 100.0 * 0.92 * intensity)
        self.setNeedsDisplay_(True)

    def drawRect_(self, dirty_rect: Any) -> None:
        bounds = self.bounds()
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*PANEL_FILL).setFill()
        fill_rounded_rect(bounds, 14.0)
        _rgba(PANEL_BORDER).setStroke()
        stroke_rounded_rect(bounds, 14.0, 1.0)
        self._draw_grid(bounds)
        claude_baseline, codex_baseline = _wave_baselines(bounds.size.height)
        self._draw_channel(
            bounds,
            claude_baseline,
            CLAUDE_WAVE,
            self.claude_amplitude,
            0.0,
        )
        self._draw_channel(
            bounds,
            codex_baseline,
            CODEX_WAVE,
            self.codex_amplitude,
            0.38,
        )

    def _draw_grid(self, bounds: Any) -> None:
        grid = _rgba(GRID_COLOR)
        grid.setFill()
        width = bounds.size.width
        height = bounds.size.height
        for x in range(14, int(width), 18):
            NSRectFill(NSMakeRect(float(x), 8.0, 1.0, height - 16.0))
        for y in range(14, int(height), 18):
            NSRectFill(NSMakeRect(8.0, float(y), width - 16.0, 1.0))
        claude_baseline, codex_baseline = _wave_baselines(bounds.size.height)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.30, 0.92, 0.78, 0.20).setFill()
        NSRectFill(NSMakeRect(8.0, claude_baseline, width - 16.0, 1.0))
        NSRectFill(NSMakeRect(8.0, codex_baseline, width - 16.0, 1.0))
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.30, 0.92, 0.78, 0.10).setFill()
        NSRectFill(
            NSMakeRect(
                12.0,
                MONITOR_INSET + LEAD_SECTION_HEIGHT + (LEAD_BLOCK_GAP / 2.0),
                width - 24.0,
                1.0,
            ),
        )

    def _draw_channel(
        self,
        bounds: Any,
        baseline: float,
        color_rgba: tuple[float, float, float, float],
        amplitude_ratio: float,
        phase_offset: float,
    ) -> None:
        width = bounds.size.width - 20.0
        base_x = 10.0
        amplitude = 6.0 + (amplitude_ratio * 24.0)
        cycle_length = max(56.0, 116.0 - (self.speed_factor * 26.0))
        glow = NSBezierPath.bezierPath()
        line = NSBezierPath.bezierPath()
        started = False
        for step in range(int(width / 4.0) + 1):
            x = base_x + (step * 4.0)
            progress = ((x / cycle_length) + float(self.phase) + phase_offset) % 1.0
            y = baseline - (_ecg_shape(progress) * amplitude)
            if not started:
                glow.moveToPoint_((x, y))
                line.moveToPoint_((x, y))
                started = True
            else:
                glow.lineToPoint_((x, y))
                line.lineToPoint_((x, y))

        glow_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            color_rgba[0],
            color_rgba[1],
            color_rgba[2],
            0.18,
        )
        glow_color.setStroke()
        glow.setLineWidth_(5.0)
        glow.stroke()

        _rgba(color_rgba).setStroke()
        line.setLineWidth_(2.0)
        line.stroke()


class ECGContentView(NSView):
    delegate = objc.ivar()
    monitor_view = objc.ivar()
    claude_header = objc.ivar()
    codex_header = objc.ivar()
    claude_session = objc.ivar()
    claude_weekly = objc.ivar()
    codex_session = objc.ivar()
    codex_weekly = objc.ivar()
    rate_label = objc.ivar()
    status_label = objc.ivar()
    today_label = objc.ivar()
    switch_button = objc.ivar()
    refresh_button = objc.ivar()
    quit_button = objc.ivar()
    install_hook_button = objc.ivar()
    show_install_button = objc.ivar()

    def initWithFrame_delegate_(self, frame: Any, delegate: Any) -> ECGContentView:
        self = objc.super(ECGContentView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.delegate = delegate
        self.show_install_button = False

        self.monitor_view = ECGMonitorView.alloc().initWithFrame_(NSMakeRect(0, 0, 1, 1))
        self.claude_header = _mono_label("LEAD A  CLAUDE", 14.0, _rgba(CLAUDE_WAVE), weight=0.38)
        self.codex_header = _mono_label("LEAD B  CODEX", 14.0, _rgba(CODEX_WAVE), weight=0.38)
        self.claude_session = ECGQuotaSummaryView.alloc().initWithFrame_color_(
            NSMakeRect(0, 0, 1, 34),
            _rgba(CLAUDE_WAVE),
        )
        self.claude_weekly = ECGQuotaSummaryView.alloc().initWithFrame_color_(
            NSMakeRect(0, 0, 1, 34),
            _rgba(CLAUDE_WAVE),
        )
        self.codex_session = ECGQuotaSummaryView.alloc().initWithFrame_color_(
            NSMakeRect(0, 0, 1, 34),
            _rgba(CODEX_WAVE),
        )
        self.codex_weekly = ECGQuotaSummaryView.alloc().initWithFrame_color_(
            NSMakeRect(0, 0, 1, 34),
            _rgba(CODEX_WAVE),
        )

        self.rate_label = _mono_label("速率：--", 13.0, ns_color(TEXT_MAIN), weight=0.30)
        self.status_label = _mono_label("狀態：--", 13.0, ns_color(TEXT_MAIN), weight=0.30)
        self.today_label = _mono_label("今日：--", 13.0, ns_color(TEXT_MAIN), weight=0.30)

        self.switch_button = ECGActionButton.alloc().initWithFrame_title_target_action_(
            NSMakeRect(0, 0, 1, BUTTON_HEIGHT),
            "切換面板",
            delegate,
            "switchPanel:",
        )
        self.refresh_button = ECGActionButton.alloc().initWithFrame_title_target_action_(
            NSMakeRect(0, 0, 1, BUTTON_HEIGHT),
            "立即更新",
            delegate,
            "refreshNow:",
        )
        self.quit_button = ECGActionButton.alloc().initWithFrame_title_target_action_(
            NSMakeRect(0, 0, 1, BUTTON_HEIGHT),
            "結束",
            delegate,
            "quitApp:",
        )
        self.install_hook_button = ECGActionButton.alloc().initWithFrame_title_target_action_(
            NSMakeRect(0, 0, 1, BUTTON_HEIGHT),
            "安裝 Hook",
            delegate,
            "installHook:",
        )
        self.install_hook_button.setHidden_(True)

        for view in (
            self.monitor_view,
            self.claude_header,
            self.codex_header,
            self.claude_session,
            self.claude_weekly,
            self.codex_session,
            self.codex_weekly,
            self.rate_label,
            self.status_label,
            self.today_label,
            self.switch_button,
            self.refresh_button,
            self.quit_button,
            self.install_hook_button,
        ):
            self.addSubview_(view)
        return self

    def isFlipped(self) -> bool:
        return True

    def layout(self) -> None:
        width = self.bounds().size.width
        content_width = width - (PADDING * 2)
        monitor_y = PADDING
        info_y = monitor_y + MONITOR_HEIGHT + SECTION_GAP
        button_y = info_y + INFO_HEIGHT + ACTION_TOP_GAP
        button_width = (content_width - (BUTTON_GAP * 2)) / 3
        lead_x = PADDING + 18
        lead_width = content_width - 36
        claude_text_y = monitor_y + MONITOR_INSET
        claude_wave_y = claude_text_y + LEAD_TEXT_HEIGHT + LEAD_WAVE_GAP
        codex_text_y = claude_wave_y + WAVE_HEIGHT + LEAD_BLOCK_GAP

        self.monitor_view.setFrame_(NSMakeRect(PADDING, monitor_y, content_width, MONITOR_HEIGHT))
        self.claude_header.setFrame_(NSMakeRect(lead_x, claude_text_y, 180, LEAD_HEADER_HEIGHT))
        self.claude_session.setFrame_(
            NSMakeRect(lead_x, claude_text_y + 26, lead_width, SUMMARY_ROW_HEIGHT),
        )
        self.claude_weekly.setFrame_(
            NSMakeRect(
                lead_x,
                claude_text_y + 26 + SUMMARY_ROW_HEIGHT + LEAD_SUMMARY_GAP,
                lead_width,
                SUMMARY_ROW_HEIGHT,
            ),
        )
        self.codex_header.setFrame_(NSMakeRect(lead_x, codex_text_y, 180, LEAD_HEADER_HEIGHT))
        self.codex_session.setFrame_(
            NSMakeRect(lead_x, codex_text_y + 26, lead_width, SUMMARY_ROW_HEIGHT),
        )
        self.codex_weekly.setFrame_(
            NSMakeRect(
                lead_x,
                codex_text_y + 26 + SUMMARY_ROW_HEIGHT + LEAD_SUMMARY_GAP,
                lead_width,
                SUMMARY_ROW_HEIGHT,
            ),
        )

        self.rate_label.setFrame_(NSMakeRect(PADDING + 18, info_y + 16, content_width - 36, 16))
        self.status_label.setFrame_(NSMakeRect(PADDING + 18, info_y + 40, content_width - 36, 16))
        self.today_label.setFrame_(NSMakeRect(PADDING + 18, info_y + 64, content_width - 36, 16))

        if self.show_install_button:
            self.install_hook_button.setFrame_(
                NSMakeRect(PADDING, button_y, content_width, BUTTON_HEIGHT),
            )
            button_y += BUTTON_HEIGHT + 10.0
        else:
            self.install_hook_button.setFrame_(NSMakeRect(PADDING, button_y, 0, 0))

        self.refresh_button.setFrame_(NSMakeRect(PADDING, button_y, button_width, BUTTON_HEIGHT))
        self.quit_button.setFrame_(
            NSMakeRect(PADDING + button_width + BUTTON_GAP, button_y, button_width, BUTTON_HEIGHT),
        )
        self.switch_button.setFrame_(
            NSMakeRect(
                PADDING + ((button_width + BUTTON_GAP) * 2),
                button_y,
                button_width,
                BUTTON_HEIGHT,
            ),
        )

    def drawRect_(self, dirty_rect: Any) -> None:
        bounds = self.bounds()
        ns_color(BACKGROUND).setFill()
        NSRectFill(bounds)

        info_y = PADDING + MONITOR_HEIGHT + SECTION_GAP
        info_rect = NSMakeRect(PADDING, info_y, bounds.size.width - (PADDING * 2), INFO_HEIGHT)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*PANEL_FILL).setFill()
        fill_rounded_rect(info_rect, 12.0)
        _rgba(PANEL_BORDER).setStroke()
        stroke_rounded_rect(info_rect, 12.0, 1.0)

    def setState_(self, state: PopoverState) -> None:
        self.claude_session.setRowState_(state.claude_session)
        self.claude_weekly.setRowState_(state.claude_weekly)
        self.codex_session.setRowState_(state.codex_session)
        self.codex_weekly.setRowState_(state.codex_weekly)
        self.rate_label.setStringValue_(state.rate_text)
        self.status_label.setStringValue_(state.status_text)
        self.today_label.setStringValue_(state.today_text)
        self.monitor_view.updateWithClaudePercent_codexPercent_rateText_(
            state.claude_session.percent,
            state.codex_session.percent,
            _suffix(state.rate_text),
        )
        self.show_install_button = state.show_install_button
        self.install_hook_button.setHidden_(not state.show_install_button)
        self.setNeedsLayout_(True)
        self.setNeedsDisplay_(True)


class ECGPanel:
    id = "ecg"
    display_name = "ECG"

    def build_view(self, delegate: Any) -> NSView:
        width, height = self.preferred_size()
        return ECGContentView.alloc().initWithFrame_delegate_(
            NSMakeRect(0, 0, width, height),
            delegate,
        )

    def apply_state(self, view: NSView, state: PopoverState) -> None:
        view.setState_(state)

    def preferred_size(self) -> tuple[float, float]:
        return (POPOVER_WIDTH, PANEL_BASE_HEIGHT)
