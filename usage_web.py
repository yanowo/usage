from __future__ import annotations

import html
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

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
            self._send_html(compact=True)
            return
        if path == "/":
            self._send_html(compact=False)
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

    def _send_html(self, *, compact: bool) -> None:
        server = cast(UsageHTTPServer, self.server)
        body = render_html(compact=compact, interval=server.interval).encode("utf-8")
        self._send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", body)

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
    print(f"compact widget: http://{display_host}:{actual_port}/compact")
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


def render_html(*, compact: bool, interval: int) -> str:
    mode_class = "compact" if compact else "full"
    title = "usage compact" if compact else "usage"
    escaped_title = html.escape(title)
    interval_ms = max(30, interval) * 1000
    return HTML_TEMPLATE.replace("__MODE__", mode_class).replace(
        "__TITLE__",
        escaped_title,
    ).replace("__INTERVAL_MS__", str(interval_ms))


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
      --shadow: 0 18px 44px rgba(21, 28, 36, 0.12);
      --claude: #f49164;
      --codex: #58d6e6;
      --good: #2a8f62;
      --warn: #ffc439;
      --danger: #ff453a;
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
      background: #e7edf2;
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
      background: #101316;
      color: #f4f7f9;
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
      align-items: center;
      padding: 0 0 10px;
      border-color: rgba(255, 255, 255, 0.12);
    }

    body.compact h1 {
      font-size: 18px;
    }

    body.compact .clock {
      color: #aeb8c4;
      font-size: 11px;
    }

    body.compact .grid {
      grid-template-columns: 1fr;
      gap: 8px;
      padding-top: 10px;
    }

    body.compact .card {
      min-height: auto;
      padding: 12px;
      color: #f4f7f9;
      background: #191f24;
      border-color: rgba(255, 255, 255, 0.12);
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
      color: #aeb8c4;
    }

    body.compact .quota {
      padding: 9px 0;
      border-color: rgba(255, 255, 255, 0.12);
    }

    body.compact .track {
      height: 7px;
      background: #2a333b;
    }

    body.compact .footer {
      grid-template-columns: 1fr;
      margin-top: 8px;
      background: rgba(255, 255, 255, 0.12);
      border-color: rgba(255, 255, 255, 0.12);
      box-shadow: none;
    }

    body.compact .metric {
      min-height: 0;
      padding: 10px 12px;
      color: #f4f7f9;
      background: #191f24;
    }

    body.compact .metric span {
      display: none;
    }

    body.compact .metric strong {
      font-size: 12px;
      font-weight: 600;
    }

    @media (max-width: 700px) {
      .shell {
        width: min(420px, calc(100vw - 20px));
        margin: 10px auto;
      }

      .grid,
      .footer {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body class="__MODE__">
  <main class="shell">
    <header class="topbar">
      <h1>usage</h1>
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

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char]));
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
      cards.innerHTML = card(data.claude) + card(data.codex);
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

    refresh();
    setInterval(refresh, intervalMs);
  </script>
</body>
</html>
"""
