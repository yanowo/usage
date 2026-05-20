from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any

from usage_rate import UsageRateTracker
from usage_state import (
    CLAUDE_COLOR,
    CODEX_COLOR,
    PopoverState,
    QuotaRowState,
    UsageViewResult,
    empty_state,
    fetch_usage_view,
)

PRODUCTS = ("all", "claude", "codex")
MIN_WIDTH = 330
MIN_HEIGHT = 420
DEFAULT_OPACITY = 1.0
MIN_OPACITY = 0.55


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
) -> tuple[int, int]:
    return (
        max(MIN_WIDTH, start_width + delta_x),
        max(MIN_HEIGHT, start_height + delta_y),
    )


def topmost_label(enabled: bool) -> str:
    return "Pinned" if enabled else "Pin"


def progress_fraction(row: QuotaRowState) -> float:
    if not row.available or row.percent is None:
        return 0.0
    return max(0.0, min(1.0, row.percent / 100.0))


def clean_label(text: str) -> str:
    return text.replace("狀態：", "").replace("速率：", "").replace("今日：", "")


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
        self.topmost_enabled = True
        self.opacity = DEFAULT_OPACITY
        self.drag_start: tuple[int, int] | None = None
        self.resize_start: tuple[int, int, int, int] | None = None

        self.root.title("usage")
        self.root.geometry("390x540+80+80")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.resizable(True, True)
        self.root.attributes("-topmost", self.topmost_enabled)
        self.root.attributes("-alpha", self.opacity)
        self.root.overrideredirect(True)

        self.title_var = tk.StringVar(value="usage")
        self.status_var = tk.StringVar(value="Loading")
        self.updated_var = tk.StringVar(value="--")
        self.opacity_var = tk.IntVar(value=round(self.opacity * 100))

        self.shell: tk.Frame | None = None
        self.cards: tk.Frame | None = None
        self.topmost_button: tk.Button | None = None
        self.template_button: tk.Button | None = None
        self._build_ui()

    def run(self) -> None:
        self._render()
        self.refresh()
        self.root.mainloop()

    def _build_ui(self) -> None:
        if self.shell is not None:
            self.shell.destroy()
        self.root.configure(bg=self.palette.bg)
        self.shell = tk.Frame(self.root, bg=self.palette.bg, padx=12, pady=12)
        self.shell.pack(fill="both", expand=True)

        self._build_header()
        self.cards = tk.Frame(self.shell, bg=self.palette.bg)
        self.cards.pack(fill="both", expand=True, pady=(10, 0))
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

        self._button(header, "x", self.root.destroy, width=2).pack(side="right")

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

    def _build_footer(self) -> None:
        if self.shell is None:
            return
        footer = tk.Frame(self.shell, bg=self.palette.panel, highlightthickness=1)
        footer.configure(highlightbackground=self.palette.line)
        footer.pack(fill="x", pady=(10, 0))

        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=self.palette.panel,
            fg=self.palette.text,
            anchor="w",
            justify="left",
            wraplength=340,
            padx=10,
            pady=7,
            font=(self.font_family, 9, "bold"),
        ).pack(fill="x")

        footer_bottom = tk.Frame(footer, bg=self.palette.panel)
        footer_bottom.pack(fill="x", pady=(0, 7))
        tk.Label(
            footer_bottom,
            textvariable=self.updated_var,
            bg=self.palette.panel,
            fg=self.palette.muted,
            anchor="w",
            padx=10,
            font=(self.font_family, 8),
        ).pack(side="left", fill="x", expand=True)

        grip = tk.Frame(
            footer_bottom,
            bg=self.palette.line,
            width=15,
            height=15,
            cursor="bottom_right_corner",
        )
        grip.pack(side="right", padx=(4, 8))
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._resize)
        grip.bind("<ButtonRelease-1>", self._end_resize)

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
            self.root.winfo_width(),
            self.root.winfo_height(),
        )

    def _resize(self, event: Any) -> None:
        if self.resize_start is None:
            return
        start_x, start_y, start_width, start_height = self.resize_start
        width, height = resize_dimensions(
            start_width,
            start_height,
            int(event.x_root) - start_x,
            int(event.y_root) - start_y,
        )
        self.root.geometry(f"{width}x{height}+{self.root.winfo_x()}+{self.root.winfo_y()}")

    def _end_resize(self, _event: Any) -> None:
        self.resize_start = None

    def _set_product(self, product: str) -> None:
        self.selected_product = normalize_product(product)
        self._render()

    def _product_command(self, product: str) -> Callable[[], None]:
        def command() -> None:
            self._set_product(product)

        return command

    def _toggle_topmost(self) -> None:
        self.topmost_enabled = not self.topmost_enabled
        self.root.attributes("-topmost", self.topmost_enabled)
        if self.topmost_button is not None:
            self.topmost_button.configure(text=topmost_label(self.topmost_enabled))
        self._style_window_buttons()

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

    def _set_opacity_from_scale(self, value: str) -> None:
        self.opacity = clamp_opacity(float(value) / 100.0)
        self.root.attributes("-alpha", self.opacity)

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
        updated = datetime.fromtimestamp(result.fetched_at).strftime("%H:%M:%S")
        self.updated_var.set(f"{clean_label(result.state.rate_text)} · {result.state.today_text}")
        self.status_var.set(f"{clean_label(result.state.status_text)} · updated {updated}")
        self._render()
        self.root.after(self.interval * 1000, self.refresh)

    def _render(self) -> None:
        if self.cards is None:
            return
        self._style_product_buttons()
        self._style_window_buttons()
        for child in self.cards.winfo_children():
            child.destroy()
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
        for button in (self.topmost_button, self.template_button):
            if button is None:
                continue
            topmost_active = button is self.topmost_button and self.topmost_enabled
            button.configure(
                bg=self.palette.active if topmost_active else self.palette.panel,
                fg=self.palette.active_text if topmost_active else self.palette.text,
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
            pady=11,
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
        ).pack(side="left")
        tk.Label(
            header,
            text=product.session.percent_text,
            bg=self.palette.panel,
            fg=product.accent,
            anchor="e",
            font=(self.font_family, 11, "bold"),
        ).pack(side="right")

        self._build_quota_row(frame, product.session, product.accent)
        self._build_quota_row(frame, product.weekly, product.accent)
        return frame

    def _build_quota_row(
        self,
        parent: tk.Frame,
        row: QuotaRowState,
        fallback_color: str,
    ) -> None:
        block = tk.Frame(parent, bg=self.palette.panel)
        block.pack(fill="x", pady=(12, 0))
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
        tk.Label(
            top,
            text=row.reset_text,
            bg=self.palette.panel,
            fg=self.palette.muted,
            anchor="e",
            font=(self.font_family, 8),
        ).pack(side="right")

        bar = tk.Canvas(
            block,
            width=310,
            height=8,
            bg=self.palette.panel,
            highlightthickness=0,
        )
        bar.pack(fill="x", pady=(7, 0))
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
        height = 8
        canvas.create_rectangle(0, 0, width, height, fill=self.palette.track, outline="")
        fill_width = max(0, int(width * progress_fraction(row)))
        if fill_width <= 0:
            return
        color = rgb_to_hex(row.color) if row.available else fallback_color
        canvas.create_rectangle(0, 0, fill_width, height, fill=color, outline="")
