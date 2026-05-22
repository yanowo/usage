from __future__ import annotations

import importlib
import threading
import time
import tkinter as tk
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any

import codex_loader
from usage_rate import UsageRateTracker
from usage_state import (
    CLAUDE_COLOR,
    CODEX_COLOR,
    PopoverState,
    QuotaRowState,
    UsageViewResult,
    codex_rows,
    empty_state,
    fetch_usage_view,
)

PRODUCTS = ("all", "claude", "codex")
MIN_WIDTH = 330
MIN_HEIGHT = 480
DEFAULT_WIDTH = 390
DEFAULT_HEIGHT = 570
MINI_WIDTH = 310
MINI_HEIGHT = 170
DEFAULT_OPACITY = 1.0
MIN_OPACITY = 0.55
CODEX_POLL_SECONDS = 5
STRIP_MIN_WIDTH = 300
STRIP_MIN_HEIGHT = 82
STRIP_MARGIN = 8
STRIP_BAR_WIDTH = 44
STRIP_BAR_HEIGHT = 5
RESIZE_THROTTLE_SECONDS = 1 / 60


@dataclass(frozen=True, slots=True)
class WorkArea:
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True, slots=True)
class DesktopPalette:
    bg: str
    panel: str
    panel_alt: str
    line: str
    text: str
    muted: str
    track: str
    active: str
    active_text: str
    danger: str


@dataclass(frozen=True, slots=True)
class DesktopTemplate:
    id: str
    display_name: str
    font_family: str
    palette: DesktopPalette


@dataclass(frozen=True, slots=True)
class ProductView:
    key: str
    name: str
    accent: str
    session: QuotaRowState
    weekly: QuotaRowState


DESKTOP_TEMPLATES: tuple[DesktopTemplate, ...] = (
    DesktopTemplate(
        id="classic",
        display_name="Classic",
        font_family="Segoe UI",
        palette=DesktopPalette(
            bg="#111417",
            panel="#f6f1e8",
            panel_alt="#e8dfd1",
            line="#d3c5b5",
            text="#161514",
            muted="#69625a",
            track="#ddd2c4",
            active="#1f6f8b",
            active_text="#ffffff",
            danger="#d24a35",
        ),
    ),
    DesktopTemplate(
        id="taiwan",
        display_name="Taiwan",
        font_family="Segoe UI",
        palette=DesktopPalette(
            bg="#8c0d14",
            panel="#5c050a",
            panel_alt="#740810",
            line="#f2d5d5",
            text="#ffffff",
            muted="#f1c5c5",
            track="#8f2830",
            active="#ffffff",
            active_text="#8c0d14",
            danger="#ffd166",
        ),
    ),
    DesktopTemplate(
        id="matrix",
        display_name="Matrix",
        font_family="Consolas",
        palette=DesktopPalette(
            bg="#000000",
            panel="#001407",
            panel_alt="#00240d",
            line="#00d959",
            text="#2ef273",
            muted="#0d992e",
            track="#00591f",
            active="#2ef273",
            active_text="#001407",
            danger="#ff4040",
        ),
    ),
    DesktopTemplate(
        id="ecg",
        display_name="ECG",
        font_family="Consolas",
        palette=DesktopPalette(
            bg="#030f0d",
            panel="#051f1a",
            panel_alt="#092b24",
            line="#479e80",
            text="#d9ffef",
            muted="#7bd0b8",
            track="#17483c",
            active="#33ffb8",
            active_text="#03120f",
            danger="#ff5f6d",
        ),
    ),
    DesktopTemplate(
        id="minimal",
        display_name="Minimal",
        font_family="Segoe UI",
        palette=DesktopPalette(
            bg="#0a0a0c",
            panel="#17171b",
            panel_alt="#202026",
            line="#2c2c33",
            text="#f5f5f7",
            muted="#8f8f9a",
            track="#2d2d33",
            active="#f49164",
            active_text="#111111",
            danger="#ff5f57",
        ),
    ),
    DesktopTemplate(
        id="sketch",
        display_name="Sketch",
        font_family="Segoe UI",
        palette=DesktopPalette(
            bg="#f6b89e",
            panel="#fffbf6",
            panel_alt="#f8e6dc",
            line="#161212",
            text="#140f0f",
            muted="#615654",
            track="#ead2c9",
            active="#e64d29",
            active_text="#ffffff",
            danger="#b02020",
        ),
    ),
)

TEMPLATE_IDS = tuple(template.id for template in DESKTOP_TEMPLATES)
DEFAULT_TEMPLATE_ID = "minimal"
TEMPLATES_BY_ID = {template.id: template for template in DESKTOP_TEMPLATES}


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    channels = [max(0, min(255, round(channel * 255))) for channel in rgb]
    return "#{:02x}{:02x}{:02x}".format(*channels)


def product_views(state: PopoverState) -> dict[str, ProductView]:
    return {
        "claude": ProductView(
            key="claude",
            name="Claude Code",
            accent=rgb_to_hex(CLAUDE_COLOR),
            session=state.claude_session,
            weekly=state.claude_weekly,
        ),
        "codex": ProductView(
            key="codex",
            name="Codex",
            accent=rgb_to_hex(CODEX_COLOR),
            session=state.codex_session,
            weekly=state.codex_weekly,
        ),
    }


def selected_product_views(state: PopoverState, selected: str) -> list[ProductView]:
    views = product_views(state)
    if selected == "claude":
        return [views["claude"]]
    if selected == "codex":
        return [views["codex"]]
    return [views["claude"], views["codex"]]


def normalize_product(value: str) -> str:
    return value if value in PRODUCTS else "all"


def normalize_template(value: str) -> str:
    return value if value in TEMPLATES_BY_ID else DEFAULT_TEMPLATE_ID


def template_palette(value: str) -> DesktopPalette:
    return TEMPLATES_BY_ID[normalize_template(value)].palette


def next_template_id(current: str) -> str:
    normalized = normalize_template(current)
    index = TEMPLATE_IDS.index(normalized)
    return TEMPLATE_IDS[(index + 1) % len(TEMPLATE_IDS)]


def clamp_opacity(value: float) -> float:
    return max(MIN_OPACITY, min(1.0, value))


def resize_dimensions(
    start_width: int,
    start_height: int,
    delta_x: int,
    delta_y: int,
    *,
    min_width: int = MIN_WIDTH,
    min_height: int = MIN_HEIGHT,
) -> tuple[int, int]:
    return (
        max(min_width, start_width + delta_x),
        max(min_height, start_height + delta_y),
    )


def top_left_resize_geometry(
    start_x: int,
    start_y: int,
    start_width: int,
    start_height: int,
    delta_x: int,
    delta_y: int,
    *,
    min_width: int = MIN_WIDTH,
    min_height: int = MIN_HEIGHT,
) -> tuple[int, int, int, int]:
    width = max(min_width, start_width - delta_x)
    height = max(min_height, start_height - delta_y)
    applied_delta_x = start_width - width
    applied_delta_y = start_height - height
    return width, height, start_x + applied_delta_x, start_y + applied_delta_y


def mini_product(selected: str) -> str:
    normalized = normalize_product(selected)
    return normalized if normalized in ("claude", "codex") else "codex"


def topmost_label(enabled: bool) -> str:
    return "Pinned" if enabled else "Pin"


def progress_fraction(row: QuotaRowState) -> float:
    if not row.available or row.percent is None:
        return 0.0
    return max(0.0, min(1.0, row.percent / 100.0))


def clean_label(text: str) -> str:
    return text.replace("狀態：", "").replace("速率：", "").replace("今日：", "")


def brief_percent(row: QuotaRowState) -> str:
    if not row.available or row.percent is None:
        return "--"
    value = row.percent
    return f"{int(value)}%" if value.is_integer() else f"{value:.1f}%"


def brief_reset(row: QuotaRowState) -> str:
    value = row.reset_text.replace("重置", "").strip()
    return value or "--"


def tray_tooltip(state: PopoverState) -> str:
    return (
        "usage | "
        f"Claude 5H {brief_percent(state.claude_session)} "
        f"W {brief_percent(state.claude_weekly)} | "
        f"Codex 5H {brief_percent(state.codex_session)} "
        f"W {brief_percent(state.codex_weekly)}"
    )


def strip_dimensions(
    screen_width: int,
    requested_width: int,
    requested_height: int,
    *,
    margin: int = STRIP_MARGIN,
) -> tuple[int, int]:
    max_width = max(STRIP_MIN_WIDTH, screen_width - margin * 2)
    return (
        min(max(STRIP_MIN_WIDTH, requested_width), max_width),
        max(STRIP_MIN_HEIGHT, requested_height),
    )


def strip_position(
    screen_width: int,
    screen_height: int,
    width: int,
    height: int,
    work_area: WorkArea | None,
    *,
    margin: int = STRIP_MARGIN,
) -> tuple[int, int]:
    left = work_area.left if work_area is not None else 0
    top = work_area.top if work_area is not None else 0
    right = work_area.right if work_area is not None else screen_width
    bottom = work_area.bottom if work_area is not None else screen_height
    return (
        max(left + margin, right - width - margin),
        max(top + margin, bottom - height - margin),
    )


def clamp_strip_position(
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
    width: int,
    height: int,
    work_area: WorkArea | None,
) -> tuple[int, int]:
    left = work_area.left if work_area is not None else 0
    top = work_area.top if work_area is not None else 0
    right = work_area.right if work_area is not None else screen_width
    bottom = work_area.bottom if work_area is not None else screen_height
    return (
        min(max(left, x), max(left, right - width)),
        min(max(top, y), max(top, bottom - height)),
    )


def merge_work_areas(areas: list[WorkArea] | tuple[WorkArea, ...]) -> WorkArea | None:
    if not areas:
        return None
    return WorkArea(
        left=min(area.left for area in areas),
        top=min(area.top for area in areas),
        right=max(area.right for area in areas),
        bottom=max(area.bottom for area in areas),
    )


def load_tray_modules() -> tuple[Any, Any, Any] | None:
    try:
        pystray_module = importlib.import_module("pystray")
        image_module = importlib.import_module("PIL.Image")
        image_draw_module = importlib.import_module("PIL.ImageDraw")
    except ImportError:
        return None
    return pystray_module, image_module, image_draw_module


def windows_work_area() -> WorkArea | None:
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    rect = wintypes.RECT()
    spi_get_work_area = 0x0030
    if not windll.user32.SystemParametersInfoW(
        spi_get_work_area,
        0,
        ctypes.byref(rect),
        0,
    ):
        return None
    return WorkArea(rect.left, rect.top, rect.right, rect.bottom)


def windows_virtual_work_area() -> WorkArea | None:
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return windows_work_area()
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return windows_work_area()

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    areas: list[WorkArea] = []

    def collect_monitor(
        monitor: Any,
        _hdc: Any,
        _rect: Any,
        _data: Any,
    ) -> bool:
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            areas.append(
                WorkArea(
                    info.rcWork.left,
                    info.rcWork.top,
                    info.rcWork.right,
                    info.rcWork.bottom,
                )
            )
        return True

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )
    callback = callback_type(collect_monitor)
    if not windll.user32.EnumDisplayMonitors(0, None, callback, 0):
        return windows_work_area()
    return merge_work_areas(areas) or windows_work_area()


def run_app(*, mock: bool = False, interval: int = 60) -> None:
    root = tk.Tk()
    DesktopUsageApp(root, mock=mock, interval=interval).run()


class DesktopUsageApp:
    def __init__(self, root: tk.Tk, *, mock: bool, interval: int) -> None:
        self.root = root
        self.mock = mock
        self.interval = max(30, interval)
        self.tracker = UsageRateTracker(mock=mock)
        self.template_id = DEFAULT_TEMPLATE_ID
        self.palette = template_palette(self.template_id)
        self.font_family = TEMPLATES_BY_ID[self.template_id].font_family
        self.selected_product = "all"
        self.latest_state = empty_state()
        self.refreshing = False
        self.codex_refreshing = False
        self.topmost_enabled = True
        self.mini_mode = False
        self.tray_hidden = False
        self.tray_modules: tuple[Any, Any, Any] | None = None
        self.tray_icon: Any | None = None
        self.strip_window: tk.Toplevel | None = None
        self.strip_frame: tk.Frame | None = None
        self.strip_header: tk.Frame | None = None
        self.strip_rows_frame: tk.Frame | None = None
        self.strip_title_label: tk.Label | None = None
        self.strip_opacity_caption: tk.Label | None = None
        self.strip_opacity_label: tk.Label | None = None
        self.strip_opacity_scale: tk.Scale | None = None
        self.strip_topmost_button: tk.Button | None = None
        self.strip_buttons: list[tk.Button] = []
        self.strip_custom_position: tuple[int, int] | None = None
        self.strip_drag_start: tuple[int, int, int, int] | None = None
        self.syncing_opacity_var = False
        self.opacity = DEFAULT_OPACITY
        self.full_geometry: str | None = None
        self.last_codex_mtime = codex_loader.latest_usage_source_mtime()
        self.last_codex_poll = 0.0
        self.drag_start: tuple[int, int] | None = None
        self.resize_start: tuple[int, int, int, int, int, int] | None = None
        self.pending_resize_geometry: str | None = None
        self.resize_after_id: str | None = None
        self.last_resize_apply = 0.0

        self.root.title("usage")
        self.root.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+80+80")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.resizable(True, True)
        self.root.attributes("-topmost", self.topmost_enabled)
        self.root.attributes("-alpha", self.opacity)
        self.root.overrideredirect(True)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self.title_var = tk.StringVar(value="usage")
        self.status_var = tk.StringVar(value="Loading")
        self.updated_var = tk.StringVar(value="--")
        self.updated_time_var = tk.StringVar(value="updated --")
        self.opacity_var = tk.IntVar(value=round(self.opacity * 100))

        self.shell: tk.Frame | None = None
        self.cards: tk.Frame | None = None
        self.all_button: tk.Button | None = None
        self.claude_button: tk.Button | None = None
        self.codex_button: tk.Button | None = None
        self.topmost_button: tk.Button | None = None
        self.mini_button: tk.Button | None = None
        self.template_button: tk.Button | None = None
        self._build_ui()

    def run(self) -> None:
        self._render()
        self.refresh()
        self._watch_codex_sessions()
        self.root.mainloop()

    def _build_ui(self) -> None:
        if self.shell is not None:
            self.shell.destroy()
        self.all_button = None
        self.claude_button = None
        self.codex_button = None
        self.topmost_button = None
        self.mini_button = None
        self.template_button = None
        self.root.configure(bg=self.palette.bg)
        padding = 8 if self.mini_mode else 12
        self.shell = tk.Frame(self.root, bg=self.palette.bg, padx=padding, pady=padding)
        self.shell.pack(fill="both", expand=True)

        if self.mini_mode:
            self._build_mini_header()
        else:
            self._build_header()
        self.cards = tk.Frame(self.shell, bg=self.palette.bg)
        self.cards.pack(fill="both", expand=True, pady=(8 if self.mini_mode else 10, 0))
        if not self.mini_mode:
            self._build_footer()
        self._render()

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        width: int | None = None,
    ) -> tk.Button:
        options: dict[str, Any] = {}
        if width is not None:
            options["width"] = width
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.palette.panel,
            fg=self.palette.text,
            activebackground=self.palette.panel_alt,
            activeforeground=self.palette.text,
            borderwidth=0,
            padx=10,
            pady=5,
            font=(self.font_family, 9, "bold"),
            **options,
        )
        return button

    def _build_header(self) -> None:
        if self.shell is None:
            return
        header = tk.Frame(self.shell, bg=self.palette.bg)
        header.pack(fill="x")
        header.bind("<ButtonPress-1>", self._start_drag)
        header.bind("<B1-Motion>", self._drag)

        grip = self._resize_grip(header)
        grip.pack(side="left", padx=(0, 8), pady=(4, 0))

        title = tk.Label(
            header,
            textvariable=self.title_var,
            bg=self.palette.bg,
            fg=self.palette.text,
            font=(self.font_family, 15, "bold"),
        )
        title.pack(side="left")
        title.bind("<ButtonPress-1>", self._start_drag)
        title.bind("<B1-Motion>", self._drag)

        self._button(header, "x", self._close, width=2).pack(side="right")
        self._button(header, "_", self._minimize_to_tray, width=2).pack(
            side="right",
            padx=(0, 4),
        )

        product_controls = tk.Frame(self.shell, bg=self.palette.bg)
        product_controls.pack(fill="x", pady=(10, 0))
        for key, label in (("all", "All"), ("claude", "Claude"), ("codex", "Codex")):
            button = self._button(product_controls, label, self._product_command(key))
            button.pack(side="left", padx=(0, 6))
            setattr(self, f"{key}_button", button)

        self._button(product_controls, "Refresh", self.refresh).pack(side="right")

        window_controls = tk.Frame(self.shell, bg=self.palette.bg)
        window_controls.pack(fill="x", pady=(8, 0))

        self.topmost_button = self._button(
            window_controls,
            topmost_label(self.topmost_enabled),
            self._toggle_topmost,
            width=7,
        )
        self.topmost_button.pack(side="left", padx=(0, 6))

        self.mini_button = self._button(
            window_controls,
            "Mini",
            self._toggle_mini,
            width=6,
        )
        self.mini_button.pack(side="left", padx=(0, 6))

        self.template_button = self._button(
            window_controls,
            self._template_button_text(),
            self._cycle_template,
            width=13,
        )
        self.template_button.pack(side="left", padx=(0, 8))

        tk.Label(
            window_controls,
            text="Alpha",
            bg=self.palette.bg,
            fg=self.palette.muted,
            font=(self.font_family, 8, "bold"),
        ).pack(side="left")
        opacity_scale = tk.Scale(
            window_controls,
            from_=55,
            to=100,
            orient="horizontal",
            variable=self.opacity_var,
            command=self._set_opacity_from_scale,
            showvalue=False,
            length=88,
            sliderlength=14,
            width=10,
            bd=0,
            highlightthickness=0,
            bg=self.palette.bg,
            fg=self.palette.text,
            troughcolor=self.palette.track,
            activebackground=self.palette.active,
        )
        opacity_scale.pack(side="left", fill="x", expand=True, padx=(5, 0))

    def _build_mini_header(self) -> None:
        if self.shell is None:
            return
        header = tk.Frame(self.shell, bg=self.palette.bg)
        header.pack(fill="x")
        header.bind("<ButtonPress-1>", self._start_drag)
        header.bind("<B1-Motion>", self._drag)

        grip = self._resize_grip(header)
        grip.pack(side="left", padx=(0, 6), pady=(3, 0))

        self._button(header, self._mini_product_label(), self._cycle_mini_product, width=8).pack(
            side="left",
            padx=(0, 6),
        )
        self._button(header, "x", self._close, width=2).pack(side="right")
        self._button(header, "_", self._minimize_to_tray, width=2).pack(
            side="right",
            padx=(0, 4),
        )
        self._button(header, "Full", self._toggle_mini, width=5).pack(side="right", padx=(6, 0))

    def _resize_grip(self, parent: tk.Misc) -> tk.Frame:
        grip = tk.Frame(
            parent,
            bg=self.palette.line,
            width=15,
            height=15,
            cursor="top_left_corner",
        )
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._resize)
        grip.bind("<ButtonRelease-1>", self._end_resize)
        return grip

    def _build_footer(self) -> None:
        if self.shell is None:
            return
        footer = tk.Frame(self.shell, bg=self.palette.panel, highlightthickness=1)
        footer.configure(highlightbackground=self.palette.line)
        footer.pack(fill="x", pady=(8, 0))

        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=self.palette.panel,
            fg=self.palette.text,
            anchor="w",
            justify="left",
            wraplength=340,
            padx=10,
            pady=5,
            font=(self.font_family, 9, "bold"),
        ).pack(fill="x")

        footer_bottom = tk.Frame(footer, bg=self.palette.panel)
        footer_bottom.pack(fill="x", pady=(0, 5))
        tk.Label(
            footer_bottom,
            textvariable=self.updated_var,
            bg=self.palette.panel,
            fg=self.palette.muted,
            anchor="w",
            padx=10,
            font=(self.font_family, 8),
        ).pack(side="left", fill="x", expand=True)

    def _start_drag(self, event: Any) -> None:
        self.drag_start = (int(event.x_root), int(event.y_root))

    def _drag(self, event: Any) -> None:
        if self.drag_start is None:
            return
        start_x, start_y = self.drag_start
        delta_x = int(event.x_root) - start_x
        delta_y = int(event.y_root) - start_y
        self.drag_start = (int(event.x_root), int(event.y_root))
        x = self.root.winfo_x() + delta_x
        y = self.root.winfo_y() + delta_y
        self.root.geometry(f"+{x}+{y}")

    def _start_resize(self, event: Any) -> None:
        self.resize_start = (
            int(event.x_root),
            int(event.y_root),
            self.root.winfo_x(),
            self.root.winfo_y(),
            self.root.winfo_width(),
            self.root.winfo_height(),
        )

    def _resize(self, event: Any) -> None:
        if self.resize_start is None:
            return
        min_width, min_height = self._minimum_size()
        start_x, start_y, start_window_x, start_window_y, start_width, start_height = (
            self.resize_start
        )
        width, height, x, y = top_left_resize_geometry(
            start_window_x,
            start_window_y,
            start_width,
            start_height,
            int(event.x_root) - start_x,
            int(event.y_root) - start_y,
            min_width=min_width,
            min_height=min_height,
        )
        self._queue_resize_geometry(f"{width}x{height}+{x}+{y}")

    def _end_resize(self, _event: Any) -> None:
        if self.resize_after_id is not None:
            with suppress(tk.TclError):
                self.root.after_cancel(self.resize_after_id)
            self.resize_after_id = None
        self._flush_queued_resize()
        self.resize_start = None

    def _queue_resize_geometry(self, geometry: str) -> None:
        if self.resize_after_id is not None:
            self.pending_resize_geometry = geometry
            return
        now = time.monotonic()
        if now - self.last_resize_apply >= RESIZE_THROTTLE_SECONDS:
            self._apply_resize_geometry(geometry)
            return
        self.pending_resize_geometry = geometry
        if self.resize_after_id is None:
            delay = max(
                1,
                round((RESIZE_THROTTLE_SECONDS - (now - self.last_resize_apply)) * 1000),
            )
            self.resize_after_id = self.root.after(delay, self._flush_queued_resize)

    def _flush_queued_resize(self) -> None:
        self.resize_after_id = None
        geometry = self.pending_resize_geometry
        self.pending_resize_geometry = None
        if geometry is not None:
            self._apply_resize_geometry(geometry)

    def _apply_resize_geometry(self, geometry: str) -> None:
        self.root.geometry(geometry)
        self.last_resize_apply = time.monotonic()

    def _minimum_size(self) -> tuple[int, int]:
        return (
            MINI_WIDTH if self.mini_mode else MIN_WIDTH,
            MINI_HEIGHT if self.mini_mode else MIN_HEIGHT,
        )

    def _set_product(self, product: str) -> None:
        self.selected_product = normalize_product(product)
        if self.mini_mode:
            self.selected_product = mini_product(self.selected_product)
        self._render()

    def _product_command(self, product: str) -> Callable[[], None]:
        def command() -> None:
            self._set_product(product)

        return command

    def _mini_product_label(self) -> str:
        return "Claude" if mini_product(self.selected_product) == "claude" else "Codex"

    def _cycle_mini_product(self) -> None:
        current = mini_product(self.selected_product)
        self.selected_product = "claude" if current == "codex" else "codex"
        self._build_ui()

    def _toggle_mini(self) -> None:
        self.mini_mode = not self.mini_mode
        if self.mini_mode:
            self.full_geometry = self.root.geometry()
            self.selected_product = mini_product(self.selected_product)
            self.root.minsize(MINI_WIDTH, MINI_HEIGHT)
            self.root.geometry(
                f"{MINI_WIDTH}x{MINI_HEIGHT}+{self.root.winfo_x()}+{self.root.winfo_y()}"
            )
        else:
            self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
            if self.full_geometry is not None:
                self.root.geometry(self.full_geometry)
        self._build_ui()

    def _toggle_topmost(self) -> None:
        self.topmost_enabled = not self.topmost_enabled
        self.root.attributes("-topmost", self.topmost_enabled)
        if self.strip_window is not None and self.strip_window.winfo_exists():
            self.strip_window.attributes("-topmost", self.topmost_enabled)
        if self.topmost_button is not None:
            self.topmost_button.configure(text=topmost_label(self.topmost_enabled))
        self._style_window_buttons()
        self._style_strip_buttons()

    def _minimize_to_tray(self) -> None:
        self._ensure_tray_icon()
        self.tray_hidden = True
        self._show_status_strip()
        self._update_tray_details()
        self.root.withdraw()

    def _ensure_tray_icon(self) -> bool:
        if self.tray_icon is not None:
            return True
        self.tray_modules = self.tray_modules or load_tray_modules()
        if self.tray_modules is None:
            return False
        pystray_module, image_module, image_draw_module = self.tray_modules
        image = self._create_tray_image(image_module, image_draw_module)
        menu = pystray_module.Menu(
            pystray_module.MenuItem("Restore", self._restore_from_tray_action, default=True),
            pystray_module.MenuItem("Quit", self._quit_from_tray_action),
        )
        self.tray_icon = pystray_module.Icon("usage", image, tray_tooltip(self.latest_state), menu)
        self._run_tray_icon(self.tray_icon)
        return True

    def _create_tray_image(self, image_module: Any, image_draw_module: Any) -> Any:
        image = image_module.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = image_draw_module.Draw(image)
        draw.rounded_rectangle(
            (4, 4, 60, 60),
            radius=12,
            fill="#17171b",
            outline="#f49164",
            width=3,
        )
        draw.rectangle((13, 21, 51, 27), fill="#2d2d33")
        draw.rectangle(
            (13, 21, 13 + round(38 * progress_fraction(self.latest_state.claude_session)), 27),
            fill="#f49164",
        )
        draw.rectangle((13, 38, 51, 44), fill="#2d2d33")
        draw.rectangle(
            (13, 38, 13 + round(38 * progress_fraction(self.latest_state.codex_session)), 44),
            fill="#58d6e6",
        )
        return image

    def _run_tray_icon(self, icon: Any) -> None:
        run_detached = getattr(icon, "run_detached", None)
        if callable(run_detached):
            run_detached()
            return
        thread = threading.Thread(target=icon.run, daemon=True)
        thread.start()

    def _restore_from_tray_action(self, _icon: Any = None, _item: Any = None) -> None:
        self.root.after(0, self._restore_from_tray)

    def _quit_from_tray_action(self, _icon: Any = None, _item: Any = None) -> None:
        self.root.after(0, self._close)

    def _restore_from_tray(self) -> None:
        self.tray_hidden = False
        self._hide_status_strip()
        self.root.deiconify()
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", self.opacity)
        self.root.attributes("-topmost", self.topmost_enabled)
        if self.topmost_enabled:
            self.root.lift()

    def _update_tray_details(self) -> None:
        self._update_status_strip()
        if self.tray_icon is None:
            return
        self.tray_icon.title = tray_tooltip(self.latest_state)
        if self.tray_modules is not None:
            _pystray_module, image_module, image_draw_module = self.tray_modules
            self.tray_icon.icon = self._create_tray_image(image_module, image_draw_module)

    def _show_status_strip(self) -> None:
        if self.strip_window is None or not self.strip_window.winfo_exists():
            self.strip_buttons = []
            self.strip_topmost_button = None
            window = tk.Toplevel(self.root)
            window.overrideredirect(True)
            window.attributes("-topmost", self.topmost_enabled)
            window.attributes("-alpha", self.opacity)
            with suppress(tk.TclError):
                window.attributes("-toolwindow", True)
            window.configure(bg=self.palette.bg)
            window.bind("<Button-3>", lambda _event: self._close())

            frame = tk.Frame(
                window,
                bg=self.palette.panel,
                padx=10,
                pady=7,
                highlightthickness=1,
                highlightbackground=self.palette.line,
            )
            frame.pack(fill="both", expand=True)
            frame.bind("<ButtonPress-1>", self._start_strip_drag)
            frame.bind("<B1-Motion>", self._drag_strip)
            frame.bind("<Double-Button-1>", lambda _event: self._restore_from_tray())
            frame.bind("<Button-3>", lambda _event: self._close())

            header = tk.Frame(frame, bg=self.palette.panel)
            header.pack(anchor="w", pady=(0, 4))
            header.bind("<ButtonPress-1>", self._start_strip_drag)
            header.bind("<B1-Motion>", self._drag_strip)
            header.bind("<Double-Button-1>", lambda _event: self._restore_from_tray())
            header.bind("<Button-3>", lambda _event: self._close())
            self.strip_header = header

            self.strip_title_label = tk.Label(
                header,
                text="usage",
                bg=self.palette.panel,
                fg=self.palette.text,
                anchor="w",
                font=(self.font_family, 8, "bold"),
            )
            self.strip_title_label.pack(side="left")
            self._bind_strip_drag(self.strip_title_label)

            self.strip_opacity_caption = tk.Label(
                header,
                text="Alpha",
                bg=self.palette.panel,
                fg=self.palette.muted,
                font=(self.font_family, 7, "bold"),
            )
            self.strip_opacity_caption.pack(side="left", padx=(8, 2))
            self.strip_opacity_scale = tk.Scale(
                header,
                from_=55,
                to=100,
                orient="horizontal",
                variable=self.opacity_var,
                command=self._set_opacity_from_scale,
                showvalue=False,
                length=78,
                sliderlength=12,
                width=8,
                bd=0,
                highlightthickness=0,
                bg=self.palette.panel,
                fg=self.palette.text,
                troughcolor=self.palette.track,
                activebackground=self.palette.active,
            )
            self.strip_opacity_scale.pack(side="left")
            self.strip_opacity_label = tk.Label(
                header,
                text="100%",
                bg=self.palette.panel,
                fg=self.palette.muted,
                anchor="e",
                font=(self.font_family, 7, "bold"),
            )
            self.strip_opacity_label.pack(side="left", padx=(3, 6))

            self._strip_button(header, "Style", self._cycle_template, width=5).pack(
                side="left",
                padx=(0, 4),
            )
            self.strip_topmost_button = self._strip_button(
                header,
                topmost_label(self.topmost_enabled),
                self._toggle_topmost,
                width=7,
            )
            self.strip_topmost_button.pack(side="left", padx=(0, 4))
            self._strip_button(header, "Open", self._restore_from_tray, width=5).pack(
                side="left",
                padx=(0, 4),
            )
            self._strip_button(header, "x", self._close, width=2).pack(side="left")

            self.strip_rows_frame = tk.Frame(
                frame,
                bg=self.palette.panel,
            )
            self.strip_rows_frame.pack(anchor="w")
            self.strip_rows_frame.bind("<ButtonPress-1>", self._start_strip_drag)
            self.strip_rows_frame.bind("<B1-Motion>", self._drag_strip)
            self.strip_rows_frame.bind(
                "<Double-Button-1>",
                lambda _event: self._restore_from_tray(),
            )
            self.strip_rows_frame.bind("<Button-3>", lambda _event: self._close())
            self.strip_window = window
            self.strip_frame = frame
        self._update_status_strip()
        if self.strip_window is not None:
            self.strip_window.deiconify()
            self.strip_window.lift()

    def _strip_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        width: int,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=self.palette.panel_alt,
            fg=self.palette.text,
            activebackground=self.palette.active,
            activeforeground=self.palette.active_text,
            borderwidth=0,
            padx=4,
            pady=1,
            font=(self.font_family, 7, "bold"),
        )
        self.strip_buttons.append(button)
        return button

    def _style_strip_buttons(self) -> None:
        if self.strip_topmost_button is not None:
            self.strip_topmost_button.configure(text=topmost_label(self.topmost_enabled))
        for button in self.strip_buttons:
            active = button is self.strip_topmost_button and self.topmost_enabled
            button.configure(
                bg=self.palette.active if active else self.palette.panel_alt,
                fg=self.palette.active_text if active else self.palette.text,
                activebackground=self.palette.active,
                activeforeground=self.palette.active_text,
                font=(self.font_family, 7, "bold"),
            )

    def _bind_strip_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._start_strip_drag)
        widget.bind("<B1-Motion>", self._drag_strip)
        widget.bind("<Double-Button-1>", lambda _event: self._restore_from_tray())

    def _start_strip_drag(self, event: Any) -> None:
        if self.strip_window is None:
            return
        self.strip_drag_start = (
            int(event.x_root),
            int(event.y_root),
            self.strip_window.winfo_x(),
            self.strip_window.winfo_y(),
        )

    def _drag_strip(self, event: Any) -> None:
        if self.strip_window is None or self.strip_drag_start is None:
            return
        start_x, start_y, start_window_x, start_window_y = self.strip_drag_start
        width = self.strip_window.winfo_width()
        height = self.strip_window.winfo_height()
        work_area = self._strip_drag_work_area()
        x, y = clamp_strip_position(
            start_window_x + int(event.x_root) - start_x,
            start_window_y + int(event.y_root) - start_y,
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
            width,
            height,
            work_area,
        )
        self.strip_custom_position = (x, y)
        self.strip_window.geometry(f"+{x}+{y}")

    def _strip_drag_work_area(self) -> WorkArea | None:
        return windows_virtual_work_area() or windows_work_area()

    def _update_status_strip(self) -> None:
        if self.strip_window is None or self.strip_rows_frame is None:
            return
        if not self.strip_window.winfo_exists():
            self.strip_window = None
            self.strip_frame = None
            self.strip_header = None
            self.strip_rows_frame = None
            self.strip_title_label = None
            self.strip_opacity_caption = None
            self.strip_opacity_label = None
            self.strip_opacity_scale = None
            self.strip_topmost_button = None
            self.strip_buttons = []
            return
        self.strip_window.configure(bg=self.palette.bg)
        self.strip_window.attributes("-alpha", self.opacity)
        self.strip_window.attributes("-topmost", self.topmost_enabled)
        if self.strip_frame is not None:
            self.strip_frame.configure(
                bg=self.palette.panel,
                highlightbackground=self.palette.line,
            )
        if self.strip_header is not None:
            self.strip_header.configure(bg=self.palette.panel)
        if self.strip_title_label is not None:
            self.strip_title_label.configure(
                bg=self.palette.panel,
                fg=self.palette.text,
                font=(self.font_family, 8, "bold"),
            )
        if self.strip_opacity_caption is not None:
            self.strip_opacity_caption.configure(
                bg=self.palette.panel,
                fg=self.palette.muted,
                font=(self.font_family, 7, "bold"),
            )
        if self.strip_opacity_label is not None:
            self.strip_opacity_label.configure(
                text=f"{round(self.opacity * 100)}%",
                bg=self.palette.panel,
                fg=self.palette.muted,
                font=(self.font_family, 7, "bold"),
            )
        if self.strip_opacity_scale is not None:
            self.strip_opacity_scale.configure(
                bg=self.palette.panel,
                fg=self.palette.text,
                troughcolor=self.palette.track,
                activebackground=self.palette.active,
            )
        self._style_strip_buttons()
        self._rebuild_strip_rows()
        self.strip_window.update_idletasks()
        width, height = strip_dimensions(
            self.root.winfo_screenwidth(),
            self.strip_window.winfo_reqwidth(),
            self.strip_window.winfo_reqheight(),
        )
        x, y = strip_position(
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
            width,
            height,
            windows_work_area(),
        )
        if self.strip_custom_position is not None:
            x, y = clamp_strip_position(
                self.strip_custom_position[0],
                self.strip_custom_position[1],
                self.root.winfo_screenwidth(),
                self.root.winfo_screenheight(),
                width,
                height,
                self._strip_drag_work_area(),
            )
            self.strip_custom_position = (x, y)
        self.strip_window.geometry(f"{width}x{height}+{x}+{y}")

    def _rebuild_strip_rows(self) -> None:
        if self.strip_rows_frame is None:
            return
        self.strip_rows_frame.configure(bg=self.palette.panel)
        for child in self.strip_rows_frame.winfo_children():
            child.destroy()
        rows = (
            (
                "Claude",
                self.latest_state.claude_session,
                self.latest_state.claude_weekly,
                rgb_to_hex(CLAUDE_COLOR),
            ),
            (
                "Codex",
                self.latest_state.codex_session,
                self.latest_state.codex_weekly,
                rgb_to_hex(CODEX_COLOR),
            ),
        )
        for index, (name, session, weekly, accent) in enumerate(rows):
            row = tk.Frame(self.strip_rows_frame, bg=self.palette.panel)
            row.pack(anchor="w", pady=(0, 3 if index == 0 else 0))
            self._bind_strip_drag(row)
            tk.Label(
                row,
                text=name,
                width=6,
                bg=self.palette.panel,
                fg=self.palette.text,
                anchor="w",
                font=(self.font_family, 8, "bold"),
            ).pack(side="left")
            self._build_strip_quota_segment(row, "5H", session, accent)
            self._build_strip_quota_segment(row, "W", weekly, accent)

    def _build_strip_quota_segment(
        self,
        parent: tk.Frame,
        title: str,
        row: QuotaRowState,
        fallback_color: str,
    ) -> None:
        segment = tk.Frame(parent, bg=self.palette.panel)
        segment.pack(side="left", padx=(0, 8))
        self._bind_strip_drag(segment)
        percent_color = rgb_to_hex(row.color) if row.available else self.palette.muted
        label = tk.Label(
            segment,
            text=f"{title} {brief_percent(row)}",
            bg=self.palette.panel,
            fg=percent_color,
            anchor="w",
            font=(self.font_family, 8, "bold"),
        )
        label.pack(side="left")
        self._bind_strip_drag(label)
        bar = tk.Canvas(
            segment,
            width=STRIP_BAR_WIDTH,
            height=STRIP_BAR_HEIGHT,
            bg=self.palette.panel,
            highlightthickness=0,
        )
        bar.pack(side="left", padx=(4, 4))
        self._bind_strip_drag(bar)
        self._bind_bar_resize(bar, row, fallback_color)
        self._draw_bar(bar, STRIP_BAR_WIDTH, row, fallback_color)
        reset = tk.Label(
            segment,
            text=brief_reset(row),
            bg=self.palette.panel,
            fg=self.palette.muted,
            anchor="w",
            font=(self.font_family, 7),
        )
        reset.pack(side="left")
        self._bind_strip_drag(reset)

    def _hide_status_strip(self) -> None:
        if self.strip_window is not None and self.strip_window.winfo_exists():
            self.strip_window.withdraw()

    def _close(self) -> None:
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        if self.strip_window is not None and self.strip_window.winfo_exists():
            self.strip_window.destroy()
            self.strip_window = None
            self.strip_frame = None
            self.strip_header = None
            self.strip_rows_frame = None
            self.strip_title_label = None
            self.strip_opacity_caption = None
            self.strip_opacity_label = None
            self.strip_opacity_scale = None
            self.strip_topmost_button = None
            self.strip_buttons = []
        self.root.destroy()

    def _template_button_text(self) -> str:
        template = TEMPLATES_BY_ID[normalize_template(self.template_id)]
        return f"Style {template.display_name}"

    def _cycle_template(self) -> None:
        self._set_template(next_template_id(self.template_id))

    def _set_template(self, template_id: str) -> None:
        self.template_id = normalize_template(template_id)
        template = TEMPLATES_BY_ID[self.template_id]
        self.palette = template.palette
        self.font_family = template.font_family
        self._build_ui()
        self._update_status_strip()

    def _set_opacity_from_scale(self, value: str) -> None:
        if self.syncing_opacity_var:
            return
        self._set_opacity(float(value) / 100.0, sync_var=False)

    def _set_opacity(self, value: float, *, sync_var: bool = True) -> None:
        self.opacity = clamp_opacity(value)
        if sync_var:
            self.syncing_opacity_var = True
            try:
                self.opacity_var.set(round(self.opacity * 100))
            finally:
                self.syncing_opacity_var = False
        self.root.attributes("-alpha", self.opacity)
        if self.strip_window is not None and self.strip_window.winfo_exists():
            self.strip_window.attributes("-alpha", self.opacity)
        if self.strip_opacity_label is not None:
            self.strip_opacity_label.configure(text=f"{round(self.opacity * 100)}%")

    def refresh(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        self.status_var.set("Loading")
        thread = threading.Thread(target=self._fetch_in_background, daemon=True)
        thread.start()

    def _fetch_in_background(self) -> None:
        try:
            result = fetch_usage_view(mock=self.mock, interval=self.interval, tracker=self.tracker)
            self.root.after(0, partial(self._apply_result, result, None))
        except Exception as exc:
            self.root.after(0, partial(self._apply_result, None, exc))

    def _apply_result(self, result: UsageViewResult | None, error: Exception | None) -> None:
        self.refreshing = False
        if error is not None:
            self.status_var.set(f"Error: {type(error).__name__}: {error}")
            self.updated_var.set("Refresh failed")
            return
        if result is None:
            return
        self.latest_state = result.state
        self._sync_codex_rows()
        updated = datetime.fromtimestamp(result.fetched_at).strftime("%H:%M:%S")
        self.updated_time_var.set(f"updated {updated}")
        self.updated_var.set(f"{clean_label(result.state.rate_text)} · {result.state.today_text}")
        self.status_var.set(f"{clean_label(result.state.status_text)} · updated {updated}")
        self._update_tray_details()
        self._render()
        self.root.after(self.interval * 1000, self.refresh)

    def _render(self) -> None:
        if self.cards is None:
            return
        if not self.mini_mode:
            self._style_product_buttons()
        self._style_window_buttons()
        for child in self.cards.winfo_children():
            child.destroy()
        if self.mini_mode:
            view = product_views(self.latest_state)[mini_product(self.selected_product)]
            self._build_mini_card(view).pack(fill="both", expand=True)
            return
        views = selected_product_views(self.latest_state, self.selected_product)
        for index, view in enumerate(views):
            self._build_card(view).pack(fill="x", pady=(0, 10 if index < len(views) - 1 else 0))

    def _style_product_buttons(self) -> None:
        for key in PRODUCTS:
            button = getattr(self, f"{key}_button", None)
            if button is None:
                continue
            active = key == self.selected_product
            button.configure(
                bg=self.palette.active if active else self.palette.panel,
                fg=self.palette.active_text if active else self.palette.text,
                activebackground=self.palette.active,
                activeforeground=self.palette.active_text,
            )

    def _style_window_buttons(self) -> None:
        for button in (self.topmost_button, self.mini_button, self.template_button):
            if button is None:
                continue
            topmost_active = button is self.topmost_button and self.topmost_enabled
            mini_active = button is self.mini_button and self.mini_mode
            active = topmost_active or mini_active
            button.configure(
                bg=self.palette.active if active else self.palette.panel,
                fg=self.palette.active_text if active else self.palette.text,
                activebackground=self.palette.panel_alt,
                activeforeground=self.palette.text,
            )
        if self.template_button is not None:
            self.template_button.configure(text=self._template_button_text())

    def _build_card(self, product: ProductView) -> tk.Frame:
        if self.cards is None:
            raise RuntimeError("cards frame has not been built")
        frame = tk.Frame(
            self.cards,
            bg=self.palette.panel,
            padx=12,
            pady=9,
            highlightthickness=1,
            highlightbackground=self.palette.line,
        )
        header = tk.Frame(frame, bg=self.palette.panel)
        header.pack(fill="x")
        tk.Label(
            header,
            text=product.name,
            bg=self.palette.panel,
            fg=self.palette.text,
            anchor="w",
            font=(self.font_family, 12, "bold"),
        ).pack(fill="x")

        self._build_quota_row(frame, product.session, product.accent)
        self._build_quota_row(frame, product.weekly, product.accent)
        return frame

    def _watch_codex_sessions(self) -> None:
        current_mtime = codex_loader.latest_usage_source_mtime()
        now = time.monotonic()
        source_changed = current_mtime is not None and current_mtime != self.last_codex_mtime
        poll_due = now - self.last_codex_poll >= CODEX_POLL_SECONDS
        if source_changed and current_mtime is not None:
            self.last_codex_mtime = current_mtime
        if (source_changed or poll_due) and not self.refreshing and not self.codex_refreshing:
            self._refresh_codex_rows()
        self.root.after(5_000, self._watch_codex_sessions)

    def _refresh_codex_rows(self) -> None:
        self.codex_refreshing = True
        thread = threading.Thread(target=self._fetch_codex_rows_in_background, daemon=True)
        thread.start()

    def _fetch_codex_rows_in_background(self) -> None:
        try:
            rows, _codex_5h_pct = codex_rows(self.mock)
        except Exception as exc:
            self.root.after(0, partial(self._apply_codex_rows, None, exc))
        else:
            self.root.after(0, partial(self._apply_codex_rows, rows, None))

    def _apply_codex_rows(
        self,
        rows: tuple[QuotaRowState, QuotaRowState] | None,
        error: Exception | None,
    ) -> None:
        self.codex_refreshing = False
        if error is not None:
            self.status_var.set(f"Codex refresh error: {type(error).__name__}: {error}")
            return
        if rows is None:
            return
        self.latest_state.codex_session = rows[0]
        self.latest_state.codex_weekly = rows[1]
        self.last_codex_poll = time.monotonic()
        updated = datetime.now().strftime("%H:%M:%S")
        self.updated_time_var.set(f"updated {updated}")
        self.status_var.set(f"{clean_label(self.latest_state.status_text)} · updated {updated}")
        self._update_tray_details()
        self._render()

    def _sync_codex_rows(self) -> None:
        rows, _codex_5h_pct = codex_rows(self.mock)
        self.latest_state.codex_session = rows[0]
        self.latest_state.codex_weekly = rows[1]
        self.last_codex_poll = time.monotonic()
        self._update_tray_details()

    def _build_mini_card(self, product: ProductView) -> tk.Frame:
        if self.cards is None:
            raise RuntimeError("cards frame has not been built")
        frame = tk.Frame(
            self.cards,
            bg=self.palette.panel,
            padx=10,
            pady=7,
            highlightthickness=1,
            highlightbackground=self.palette.line,
        )
        top = tk.Frame(frame, bg=self.palette.panel)
        top.pack(fill="x")
        tk.Label(
            top,
            text=product.name,
            bg=self.palette.panel,
            fg=self.palette.text,
            anchor="w",
            font=(self.font_family, 10, "bold"),
        ).pack(fill="x")

        self._build_mini_quota_row(frame, product.session, product.accent)
        self._build_mini_quota_row(frame, product.weekly, product.accent)
        tk.Label(
            frame,
            textvariable=self.updated_time_var,
            bg=self.palette.panel,
            fg=self.palette.muted,
            anchor="w",
            font=(self.font_family, 8),
        ).pack(fill="x")
        return frame

    def _build_mini_quota_row(
        self,
        parent: tk.Frame,
        row: QuotaRowState,
        fallback_color: str,
    ) -> None:
        row_frame = tk.Frame(parent, bg=self.palette.panel)
        row_frame.pack(fill="x", pady=(5, 0))
        tk.Label(
            row_frame,
            text=row.title,
            bg=self.palette.panel,
            fg=self.palette.text,
            anchor="w",
            font=(self.font_family, 8, "bold"),
        ).pack(side="left")
        meta = tk.Frame(row_frame, bg=self.palette.panel)
        meta.pack(side="right")
        tk.Label(
            meta,
            text=row.reset_text,
            bg=self.palette.panel,
            fg=self.palette.muted,
            anchor="e",
            font=(self.font_family, 7),
        ).pack(side="right")
        tk.Label(
            meta,
            text=row.percent_text,
            bg=self.palette.panel,
            fg=fallback_color,
            anchor="e",
            font=(self.font_family, 8, "bold"),
        ).pack(side="right", padx=(0, 8))

        bar = tk.Canvas(
            parent,
            width=280,
            height=4,
            bg=self.palette.panel,
            highlightthickness=0,
        )
        bar.pack(fill="x", pady=(2, 0))
        self._bind_bar_resize(bar, row, fallback_color)

    def _build_quota_row(
        self,
        parent: tk.Frame,
        row: QuotaRowState,
        fallback_color: str,
    ) -> None:
        block = tk.Frame(parent, bg=self.palette.panel)
        block.pack(fill="x", pady=(9, 0))
        top = tk.Frame(block, bg=self.palette.panel)
        top.pack(fill="x")
        tk.Label(
            top,
            text=row.title,
            bg=self.palette.panel,
            fg=self.palette.text,
            anchor="w",
            font=(self.font_family, 9, "bold"),
        ).pack(side="left")
        meta = tk.Frame(top, bg=self.palette.panel)
        meta.pack(side="right")
        tk.Label(
            meta,
            text=row.reset_text,
            bg=self.palette.panel,
            fg=self.palette.muted,
            anchor="e",
            font=(self.font_family, 8),
        ).pack(side="right")
        tk.Label(
            meta,
            text=row.percent_text,
            bg=self.palette.panel,
            fg=fallback_color,
            anchor="e",
            font=(self.font_family, 9, "bold"),
        ).pack(side="right", padx=(0, 10))

        bar = tk.Canvas(
            block,
            width=310,
            height=7,
            bg=self.palette.panel,
            highlightthickness=0,
        )
        bar.pack(fill="x", pady=(5, 0))
        self._bind_bar_resize(bar, row, fallback_color)

    def _bind_bar_resize(
        self,
        canvas: tk.Canvas,
        row: QuotaRowState,
        fallback_color: str,
    ) -> None:
        def redraw(event: Any) -> None:
            self._draw_bar(canvas, int(event.width), row, fallback_color)

        canvas.bind("<Configure>", redraw)

    def _draw_bar(
        self,
        canvas: tk.Canvas,
        width: int,
        row: QuotaRowState,
        fallback_color: str,
    ) -> None:
        canvas.delete("all")
        height = max(1, int(canvas.winfo_height()))
        canvas.create_rectangle(0, 0, width, height, fill=self.palette.track, outline="")
        fill_width = max(0, int(width * progress_fraction(row)))
        if fill_width <= 0:
            return
        color = rgb_to_hex(row.color) if row.available else fallback_color
        canvas.create_rectangle(0, 0, fill_width, height, fill=color, outline="")
