from __future__ import annotations

import html
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlparse

from usage_rate import UsageRateTracker
from usage_state import QuotaRowState, UsageViewResult, fetch_usage_view

DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8765
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


class UsageHTTPServer(ThreadingHTTPServer):
    mock: bool
    interval: int
    tracker: UsageRateTracker

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        mock: bool,
        interval: int,
    ) -> None:
        super().__init__(server_address, UsageRequestHandler)
        self.mock = mock
        self.interval = max(30, interval)
        self.tracker = UsageRateTracker(mock=mock)


class UsageRequestHandler(BaseHTTPRequestHandler):
    server_version = "usage-web/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/usage":
            self._send_usage_json()
            return
        if path == "/healthz":
            self._send_bytes(HTTPStatus.OK, "text/plain; charset=utf-8", b"ok\n")
            return
        if path == "/assets/claude.webp" or path == "/assets/codex.webp":
            self._send_asset(path.removeprefix("/assets/"))
            return
        if path == "/compact":
            layout = "horizontal" if _query_flag(query, "horizontal") else "compact"
            self._redirect_to_root(query, layout=layout)
            return
        if path == "/compact-horizontal":
            self._redirect_to_root(query, layout="horizontal")
            return
        if path == "/":
            self._send_html(layout=_query_layout(query))
            return

        self._send_bytes(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_usage_json(self) -> None:
        server = cast(UsageHTTPServer, self.server)
        try:
            result = fetch_usage_view(
                mock=server.mock,
                interval=server.interval,
                tracker=server.tracker,
            )
            payload = usage_payload(result, mock=server.mock)
            status = HTTPStatus.OK
        except Exception as exc:
            payload = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_at": time.time(),
            }
            status = HTTPStatus.INTERNAL_SERVER_ERROR

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _send_html(self, *, layout: str) -> None:
        server = cast(UsageHTTPServer, self.server)
        body = render_html(layout=layout, interval=server.interval).encode("utf-8")
        self._send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", body)

    def _redirect_to_root(self, query: dict[str, list[str]], *, layout: str) -> None:
        pairs: list[tuple[str, str]] = [("layout", layout)]
        for key, values in query.items():
            if key in ("layout", "horizontal"):
                continue
            pairs.extend((key, value) for value in values)
        location = f"/?{urlencode(pairs)}"
        body = f"redirecting to {location}\n".encode()
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_asset(self, name: str) -> None:
        path = (ASSETS_DIR / name).resolve()
        if path.parent != ASSETS_DIR or not path.is_file():
            self._send_bytes(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            body = path.read_bytes()
        except OSError:
            self._send_bytes(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "text/plain; charset=utf-8",
                b"asset read failed\n",
            )
            return
        self._send_bytes(HTTPStatus.OK, content_type, body, cache_control="public, max-age=86400")

    def _send_bytes(
        self,
        status: HTTPStatus,
        content_type: str,
        body: bytes,
        *,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)


def run_server(
    *,
    host: str = DEFAULT_WEB_HOST,
    port: int = DEFAULT_WEB_PORT,
    mock: bool = False,
    interval: int = 60,
) -> None:
    server = UsageHTTPServer((host, port), mock=mock, interval=interval)
    actual_host, actual_port = server.server_address[:2]
    display_host = "127.0.0.1" if actual_host in ("", "0.0.0.0") else str(actual_host)
    print(f"usage web: http://{display_host}:{actual_port}/")
    print(f"compact layout: http://{display_host}:{actual_port}/?layout=compact")
    print(f"wide layout: http://{display_host}:{actual_port}/?layout=horizontal")
    print(f"JSON API: http://{display_host}:{actual_port}/api/usage")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def usage_payload(result: UsageViewResult, *, mock: bool) -> dict[str, Any]:
    state = result.state
    return {
        "ok": True,
        "mock": mock,
        "poll_state": result.outcome.state.value,
        "message": result.outcome.message or "",
        "fetched_at": result.fetched_at,
        "codex_5h_pct": result.codex_5h_pct,
        "rate_text": state.rate_text,
        "status_text": state.status_text,
        "today_text": state.today_text,
        "show_install_button": state.show_install_button,
        "claude": {
            "name": "Claude Code",
            "icon": "/assets/claude.webp",
            "session": row_payload(state.claude_session),
            "weekly": row_payload(state.claude_weekly),
        },
        "codex": {
            "name": "Codex",
            "icon": "/assets/codex.webp",
            "session": row_payload(state.codex_session),
            "weekly": row_payload(state.codex_weekly),
        },
    }


def row_payload(row: QuotaRowState) -> dict[str, Any]:
    return {
        "title": row.title,
        "percent": row.percent,
        "percent_text": row.percent_text,
        "reset_text": row.reset_text,
        "color": rgb_to_hex(row.color),
        "available": row.available,
    }


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    channels = [max(0, min(255, round(channel * 255))) for channel in rgb]
    return "#{:02x}{:02x}{:02x}".format(*channels)


def render_html(*, interval: int, layout: str = "full") -> str:
    normalized_layout = _normalize_layout(layout)
    body_class = (
        "compact horizontal" if normalized_layout == "horizontal" else normalized_layout
    )
    title = f"usage {normalized_layout}" if normalized_layout != "full" else "usage"
    escaped_title = html.escape(title)
    interval_ms = max(30, interval) * 1000
    return HTML_TEMPLATE.replace("__BODY_CLASS__", body_class).replace(
        "__TITLE__",
        escaped_title,
    ).replace("__INTERVAL_MS__", str(interval_ms)).replace(
        "__LAYOUT__",
        normalized_layout,
    )


def _normalize_layout(value: str | None) -> str:
    if value in ("full", "compact", "horizontal"):
        return value
    return "full"


def _query_layout(query: dict[str, list[str]]) -> str:
    values = query.get("layout") or query.get("view") or []
    if values:
        return _normalize_layout(values[-1].lower())
    if _query_flag(query, "horizontal"):
        return "horizontal"
    if _query_flag(query, "compact"):
        return "compact"
    return "full"


def _query_flag(query: dict[str, list[str]], name: str) -> bool:
    values = query.get(name, [])
    if any(value.lower() in ("1", "true", "yes", "on") for value in values):
        return True
    layout_values = query.get("layout", [])
    return any(value.lower() == name for value in layout_values)


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #16191d;
      --muted: #69727d;
      --paper: #f3f6f8;
      --panel: #ffffff;
      --line: #d7dee5;
      --button: #eef3f6;
      --button-active: #16191d;
      --button-active-ink: #ffffff;
      --shadow: 0 18px 44px rgba(21, 28, 36, 0.12);
      --claude: #f49164;
      --codex: #58d6e6;
      --good: #2a8f62;
      --warn: #ffc439;
      --danger: #ff453a;
    }

    body.theme-dark {
      color-scheme: dark;
      --ink: #e8edf0;
      --muted: #93a0a8;
      --paper: #0f1316;
      --panel: #171d21;
      --line: #2b343a;
      --button: #1f272c;
      --button-active: #9de6d0;
      --button-active-ink: #0c1113;
      --shadow: 0 22px 56px rgba(0, 0, 0, 0.42);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(22, 25, 29, 0.05) 1px, transparent 1px),
        linear-gradient(180deg, rgba(22, 25, 29, 0.05) 1px, transparent 1px),
        var(--paper);
      background-size: 24px 24px;
      font-family: Avenir Next, Segoe UI, Helvetica Neue, sans-serif;
      letter-spacing: 0;
    }

    body.theme-dark {
      background:
        linear-gradient(90deg, rgba(157, 230, 208, 0.035) 1px, transparent 1px),
        linear-gradient(180deg, rgba(157, 230, 208, 0.035) 1px, transparent 1px),
        radial-gradient(circle at 16% 12%, rgba(157, 230, 208, 0.11), transparent 34%),
        var(--paper);
    }

    .shell {
      width: min(960px, calc(100vw - 32px));
      margin: 24px auto;
    }

    .topbar {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      padding: 0 2px 14px;
      border-bottom: 1px solid var(--line);
    }

    .controls {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .segmented {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      width: 236px;
      padding: 3px;
      background: var(--button);
      border: 1px solid var(--line);
      border-radius: 8px;
    }

    .layout-tabs {
      width: 252px;
    }

    button {
      min-height: 32px;
      color: var(--ink);
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
      background: transparent;
      border: 0;
      border-radius: 6px;
      cursor: pointer;
    }

    button:focus-visible {
      outline: 2px solid var(--codex);
      outline-offset: 2px;
    }

    .segment.active {
      color: var(--button-active-ink);
      background: var(--button-active);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
    }

    .theme-toggle {
      min-width: 72px;
      padding: 0 12px;
      background: var(--panel);
      border: 1px solid var(--line);
    }

    body.theme-dark .theme-toggle {
      color: #c7f4e7;
      background: #12181b;
    }

    h1 {
      margin: 0;
      font-size: 26px;
      line-height: 1;
      font-weight: 750;
      letter-spacing: 0;
    }

    .clock {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      padding-top: 14px;
    }

    .grid.single {
      grid-template-columns: minmax(0, 1fr);
    }

    .grid.single .card {
      min-height: 226px;
    }

    .card, .footer {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .card {
      min-height: 250px;
      padding: 18px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 18px;
    }

    .brand img {
      width: 42px;
      height: 42px;
      border-radius: 8px;
      object-fit: cover;
      background: #111418;
    }

    .brand strong {
      display: block;
      font-size: 18px;
      line-height: 1.1;
    }

    .brand span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }

    .quota {
      padding: 14px 0;
      border-top: 1px solid var(--line);
    }

    .quota:first-of-type {
      border-top: 0;
      padding-top: 0;
    }

    .quota-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }

    .quota-title {
      font-size: 13px;
      font-weight: 650;
    }

    .quota-pct {
      color: var(--muted);
      font-size: 13px;
      font-variant-numeric: tabular-nums;
      text-align: right;
    }

    .track {
      width: 100%;
      height: 9px;
      overflow: hidden;
      background: var(--button);
      border-radius: 999px;
    }

    .fill {
      width: 0%;
      height: 100%;
      min-width: 0;
      border-radius: 999px;
      background: var(--good);
      transition: width 220ms ease, background-color 220ms ease;
    }

    .reset {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }

    .footer {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1px;
      margin-top: 14px;
      overflow: hidden;
      background: var(--line);
    }

    .metric {
      min-height: 74px;
      padding: 14px;
      background: var(--panel);
    }

    .metric span {
      display: block;
      margin-bottom: 7px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .metric strong {
      display: block;
      overflow-wrap: anywhere;
      font-size: 14px;
      line-height: 1.35;
      font-weight: 650;
    }

    .error {
      display: none;
      margin-top: 14px;
      padding: 12px 14px;
      color: #7e1d17;
      background: #ffe8e5;
      border: 1px solid #ffc9c2;
      border-radius: 8px;
      font-size: 13px;
    }

    body.compact {
      min-height: 100vh;
    }

    body.compact .shell {
      width: min(360px, 100vw);
      min-height: 100vh;
      margin: 0 auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }

    body.compact .topbar {
      align-items: flex-start;
      flex-wrap: wrap;
      padding: 0 0 10px;
      border-color: var(--line);
    }

    body.compact .controls {
      width: 100%;
      justify-content: flex-start;
      gap: 6px;
      order: 3;
    }

    body.compact h1 {
      font-size: 18px;
    }

    body.compact .clock {
      color: var(--muted);
      font-size: 11px;
    }

    body.compact .segmented {
      width: 164px;
      padding: 2px;
    }

    body.compact .layout-tabs {
      width: 188px;
    }

    body.compact button {
      min-height: 27px;
      font-size: 10.5px;
    }

    body.compact .theme-toggle {
      min-width: 58px;
      padding: 0 9px;
    }

    body.compact .grid {
      grid-template-columns: 1fr;
      gap: 8px;
      padding-top: 10px;
    }

    body.compact .card {
      min-height: auto;
      padding: 12px;
      background: var(--panel);
      border-color: var(--line);
      box-shadow: none;
    }

    body.compact .brand {
      margin-bottom: 10px;
    }

    body.compact .brand img {
      width: 28px;
      height: 28px;
      border-radius: 6px;
    }

    body.compact .brand strong {
      font-size: 14px;
    }

    body.compact .brand span,
    body.compact .quota-pct,
    body.compact .reset {
      color: var(--muted);
    }

    body.compact .quota {
      padding: 9px 0;
      border-color: rgba(255, 255, 255, 0.12);
    }

    body.compact .track {
      height: 7px;
      background: var(--button);
    }

    body.compact .footer {
      grid-template-columns: 1fr;
      margin-top: 8px;
      background: var(--line);
      border-color: var(--line);
      box-shadow: none;
    }

    body.compact .metric {
      min-height: 0;
      padding: 10px 12px;
      background: var(--panel);
    }

    body.compact .metric span {
      display: none;
    }

    body.compact .metric strong {
      font-size: 12px;
      font-weight: 600;
    }

    body.compact.horizontal .shell {
      width: min(780px, 100vw);
      padding: 10px;
    }

    body.compact.horizontal .grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      padding-top: 8px;
    }

    body.compact.horizontal .card {
      padding: 10px;
    }

    body.compact.horizontal .brand {
      margin-bottom: 6px;
    }

    body.compact.horizontal .quota {
      padding: 6px 0;
    }

    body.compact.horizontal .quota-head {
      margin-bottom: 6px;
    }

    body.compact.horizontal .reset {
      margin-top: 5px;
    }

    body.compact.horizontal .footer {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 8px;
    }

    body.compact.horizontal .metric {
      padding: 8px 10px;
    }

    @media (max-width: 700px) {
      .shell {
        width: min(420px, calc(100vw - 20px));
        margin: 10px auto;
      }

      body:not(.compact.horizontal) .grid,
      body:not(.compact.horizontal) .footer {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body class="__BODY_CLASS__">
  <main class="shell">
    <header class="topbar">
      <h1>usage</h1>
      <div class="controls" id="controls">
        <div class="segmented" id="productTabs" aria-label="Product view">
          <button class="segment" type="button" data-product="all">All</button>
          <button class="segment" type="button" data-product="claude">Claude</button>
          <button class="segment" type="button" data-product="codex">Codex</button>
        </div>
        <div class="segmented layout-tabs" id="layoutTabs" aria-label="Layout view">
          <button class="segment" type="button" data-layout="full">Full</button>
          <button class="segment" type="button" data-layout="compact">Compact</button>
          <button class="segment" type="button" data-layout="horizontal">Wide</button>
        </div>
        <button class="theme-toggle" id="themeToggle" type="button">Dark</button>
      </div>
      <div class="clock" id="clock">--</div>
    </header>
    <section class="grid" id="cards"></section>
    <section class="footer" id="footer"></section>
    <div class="error" id="error"></div>
  </main>

  <script>
    const intervalMs = __INTERVAL_MS__;
    const cards = document.getElementById("cards");
    const footer = document.getElementById("footer");
    const error = document.getElementById("error");
    const clock = document.getElementById("clock");
    const productTabs = document.getElementById("productTabs");
    const layoutTabs = document.getElementById("layoutTabs");
    const themeToggle = document.getElementById("themeToggle");
    const params = new URLSearchParams(window.location.search);
    const productChoices = new Set(["all", "claude", "codex"]);
    const layoutChoices = new Set(["full", "compact", "horizontal"]);
    const themeChoices = new Set(["light", "dark"]);
    const initialLayout = "__LAYOUT__";
    let selectedLayout = normalizeChoice(
      params.get("layout") || params.get("view") || localStorage.getItem("usage.layout"),
      layoutChoices,
      initialLayout,
    );
    let selectedProduct = normalizeChoice(
      params.get("product") || localStorage.getItem("usage.product"),
      productChoices,
      "all",
    );
    let selectedTheme = resolveTheme();

    applyLayout(selectedLayout, false);
    applyTheme(selectedTheme);
    updateProductTabs();
    updateLayoutTabs();

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char]));
    }

    function normalizeChoice(value, choices, fallback) {
      return choices.has(value) ? value : fallback;
    }

    function resolveTheme() {
      const requested = normalizeChoice(params.get("theme"), themeChoices, "");
      if (requested) return requested;
      const saved = normalizeChoice(localStorage.getItem("usage.theme"), themeChoices, "");
      if (saved) return saved;
      if (selectedLayout !== "full") return "dark";
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    function applyLayout(layout, persist = true) {
      selectedLayout = normalizeChoice(layout, layoutChoices, "full");
      document.body.classList.toggle("full", selectedLayout === "full");
      document.body.classList.toggle("compact", selectedLayout !== "full");
      document.body.classList.toggle("horizontal", selectedLayout === "horizontal");
      if (persist) localStorage.setItem("usage.layout", selectedLayout);
      updateLayoutTabs();
    }

    function applyTheme(theme) {
      selectedTheme = theme;
      document.body.classList.toggle("theme-dark", theme === "dark");
      document.body.classList.toggle("theme-light", theme === "light");
      document.documentElement.style.colorScheme = theme;
      if (themeToggle) {
        themeToggle.textContent = theme === "dark" ? "Light" : "Dark";
        const nextTheme = theme === "dark" ? "light" : "dark";
        themeToggle.setAttribute("aria-label", `Switch to ${nextTheme} mode`);
      }
    }

    function updateProductTabs() {
      if (!productTabs) return;
      productTabs.querySelectorAll("[data-product]").forEach((button) => {
        const isActive = button.dataset.product === selectedProduct;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
    }

    function updateLayoutTabs() {
      if (!layoutTabs) return;
      layoutTabs.querySelectorAll("[data-layout]").forEach((button) => {
        const isActive = button.dataset.layout === selectedLayout;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
    }

    function quota(row) {
      const percent = typeof row.percent === "number" ? Math.max(0, Math.min(100, row.percent)) : 0;
      const width = row.available ? percent : 0;
      const color = row.available ? row.color : "#95a1ad";
      return `
        <div class="quota">
          <div class="quota-head">
            <span class="quota-title">${escapeHtml(row.title)}</span>
            <span class="quota-pct">${escapeHtml(row.percent_text)}</span>
          </div>
          <div class="track">
            <div class="fill" style="width:${width}%; background:${color}"></div>
          </div>
          <div class="reset">${escapeHtml(row.reset_text)}</div>
        </div>
      `;
    }

    function card(product) {
      return `
        <article class="card">
          <div class="brand">
            <img src="${escapeHtml(product.icon)}" alt="">
            <div>
              <strong>${escapeHtml(product.name)}</strong>
              <span>
                ${escapeHtml(product.session.percent_text)}
                ·
                ${escapeHtml(product.weekly.percent_text)}
              </span>
            </div>
          </div>
          ${quota(product.session)}
          ${quota(product.weekly)}
        </article>
      `;
    }

    function metric(label, value) {
      return `
        <div class="metric">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `;
    }

    function render(data) {
      const products = selectedProduct === "claude"
        ? [data.claude]
        : selectedProduct === "codex"
          ? [data.codex]
          : [data.claude, data.codex];
      cards.classList.toggle("single", products.length === 1);
      cards.innerHTML = products.map(card).join("");
      footer.innerHTML =
        metric("Rate", data.rate_text) +
        metric("Status", data.status_text) +
        metric("Today", data.today_text);
      clock.textContent = new Date(data.fetched_at * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      error.style.display = "none";
    }

    async function refresh() {
      try {
        const response = await fetch("/api/usage", { cache: "no-store" });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || response.statusText);
        render(data);
      } catch (err) {
        error.textContent = err.message || String(err);
        error.style.display = "block";
      }
    }

    if (productTabs) {
      productTabs.addEventListener("click", (event) => {
        const button = event.target.closest("[data-product]");
        if (!button) return;
        selectedProduct = normalizeChoice(button.dataset.product, productChoices, "all");
        localStorage.setItem("usage.product", selectedProduct);
        updateProductTabs();
        refresh();
      });
    }

    if (layoutTabs) {
      layoutTabs.addEventListener("click", (event) => {
        const button = event.target.closest("[data-layout]");
        if (!button) return;
        applyLayout(button.dataset.layout);
      });
    }

    if (themeToggle) {
      themeToggle.addEventListener("click", () => {
        const nextTheme = selectedTheme === "dark" ? "light" : "dark";
        localStorage.setItem("usage.theme", nextTheme);
        applyTheme(nextTheme);
      });
    }

    refresh();
    setInterval(refresh, intervalMs);
  </script>
</body>
</html>
"""
