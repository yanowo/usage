# usage

[繁體中文](README.md) · English

[![CI](https://github.com/aqua5230/usage/actions/workflows/check.yml/badge.svg)](https://github.com/aqua5230/usage/actions/workflows/check.yml)
[![Latest Release](https://img.shields.io/github/v/release/aqua5230/usage)](https://github.com/aqua5230/usage/releases/latest)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey.svg)](README.en.md)
[![License](https://img.shields.io/github/license/aqua5230/usage)](LICENSE)

`usage` shows your **Claude Code and Codex** usage locally. On macOS it can live in the menu bar; on Windows it can run as a small desktop window, or as a local web UI so a browser or desktop widget can open a URL and show current 5-hour usage, 7-day usage, and today's token usage and cost estimate.

It **never calls the Anthropic / OpenAI API** and **never reads the Keychain**, so it avoids the observer effect of "pinging once a minute counts as usage."

<p align="center">
  <img src="docs/popover.png" alt="usage popover" width="320">
</p>

## How it gets the data

Usage numbers come from local files written by Claude Code and Codex — no Anthropic / OpenAI API calls. The one exception: to estimate Codex costs, usage needs a token pricing table. If no local cache exists (`~/.claude/pricing_cache.json`), it downloads the public [LiteLLM pricing JSON](https://github.com/BerriAI/litellm) once and caches it for 7 days. If the download fails, a built-in fallback price is used — usage percentage display is unaffected. On first launch without a cache, the fetch is synchronous and may take ~10 seconds on slow networks.

### Claude Code usage

usage installs a small **statusLine hook** — a script that Claude Code automatically pipes data into every time it refreshes its status line. The flow:

1. Claude Code refreshes the status line and packages usage info (5-hour percentage, 7-day percentage, etc.) as JSON.
2. It pipes that JSON to the hook via stdin.
3. The hook writes the JSON to `~/.claude/usage-status.json`.
4. The usage UI reads that file.

Since both sides look at the same source data, **the numbers match exactly what Claude Code itself shows**.

```mermaid
flowchart LR
    A[Claude Code main process] -->|pipes JSON to stdin<br/>on every statusLine refresh| B[usage-statusline.py<br/>hook script]
    B -->|writes| C[(~/.claude/<br/>usage-status.json)]
    D[usage menu bar / Web / TUI] -->|reads| C
    D -->|renders| E[macOS menu bar / browser / widget URL]
    F((Anthropic API)) -.x.- D
    style F stroke:#c0392b,stroke-dasharray:5 5
```

Claude status files usage can read:

1. `~/.claude/usage-status.json` — written by the hook usage installs.
2. `~/.claude/usag-status.json` — automatic v0.1.x legacy fallback; new users should not encounter this.
3. `~/.claude/tt-status.json` — fallback. If you also use [token-tracker](https://github.com/stormzhang/token-tracker), usage will share its status file.

If multiple status files exist, usage chooses the newest snapshot that contains quota data. It only falls back to source priority when timestamps match, so an older `usage-status.json` will not hide newer usable data from another local source.

### Codex usage

Codex CLI doesn't expose a statusLine hook, so usage takes a different route: it scans the conversation logs Codex CLI leaves on disk (`~/.codex/sessions/*.jsonl`). Codex writes `rate_limits` data directly into each log entry — usage maps `window_minutes=300` to the CLI 5h quota and `window_minutes=10080` to the weekly quota. Today's token count and cost are summed from the token usage recorded in the same files.

If Codex isn't installed or the directory doesn't exist, that part of the UI hides itself and Claude Code stats continue to work normally.

## Requirements

- macOS or Windows
- Python 3.13
- Claude Code installed and signed in (Codex is optional)

## Quick start

| I want to… | How |
|-----------|-----|
| Use it on macOS with no setup | [Download the app](#download-the-app) |
| Use it on Windows with no setup | [Download the Windows exe](#download-the-windows-exe) |
| Use it on Windows as a small desktop window | [Desktop mode](#desktop-mode-windows-default) |
| Use a desktop widget URL | [Web mode](#web-mode-url--desktop-widget) |
| Run from source | [Set up the environment](#set-up-the-environment) |
| Preview the UI without installing | [Preview mode](#preview-mode-no-install-required) |

## Download the app

Go to the [GitHub Releases page](https://github.com/aqua5230/usage/releases/latest) and download the latest `usage.app.zip`. Unzip it and move `usage.app` wherever you like (e.g. `/Applications`).

⚠️ Because this app is not signed with an Apple Developer certificate, **macOS Gatekeeper will block the first launch**.
To open it: find `usage.app` in Finder → right-click → Open → confirm Open. After that, double-clicking works normally.

### First launch: install the hook

The first time you open usage, if Claude Code has never been wired up yet, the popover will detect the missing status file and **show an extra "立即安裝 hook" (Install hook now) button at the bottom**. Click it once — it installs the hook for you. Then **fully quit Claude Code (Cmd+Q) and re-open it**, click "Refresh now" in usage, and the numbers will appear.

If the button doesn't show, usage is already reading data (e.g. you previously installed [token-tracker](https://github.com/stormzhang/token-tracker) and its status file works as a fallback) — nothing else to do.

> **Fallback: install via curl**
> If the in-app button doesn't work or you prefer the command line, paste this in Terminal:
>
> ```bash
> bash <(curl -fsSL https://raw.githubusercontent.com/aqua5230/usage/main/scripts/install-hook.sh)
> ```

## Download the Windows exe

Go to the [GitHub Releases page](https://github.com/aqua5230/usage/releases/latest) and download `usage.exe`. Double-clicking it starts the Windows desktop widget. If SmartScreen warns about an unknown publisher, verify the file came from this project's Release page before choosing to keep or run it.

## Download

```bash
git clone https://github.com/aqua5230/usage.git
cd usage
```

If you don't use git, go to the [GitHub project page](https://github.com/aqua5230/usage), click the green **Code → Download ZIP**, then `cd` into the unzipped folder.

## Set up the environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

This creates an isolated Python environment (`.venv`) for the project, activates it, and installs usage plus its dependencies into it.

## First install (wire up the Claude Code hook — source mode only)

> Using the .app? Just click the "立即安裝 hook" button in the popover on first launch instead — you don't need this section. The steps below are for developers running usage from source.

This single command does two things: copies the hook script into `~/.claude/`, and updates your Claude Code settings to point at it.

```bash
source .venv/bin/activate
python3 main.py --setup
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py --setup
```

**Restart Claude Code once after running this** so it re-reads `~/.claude/settings.json` and refreshes its status line. That refresh is when usage data first lands on disk.

What `--setup` does in detail:

- Copies `usage_statusline.py` to `~/.claude/usage-statusline.py`.
- Points `statusLine` in `~/.claude/settings.json` at that hook and sets `refreshInterval: 1`, so Claude Code keeps refreshing the status file while idle.
- If you already had a custom `statusLine`, it is backed up to `settings.usage.previousStatusLine` so nothing is overwritten.

To uninstall:

```bash
python3 main.py --unsetup
```

`--unsetup` restores your original statusLine and removes the hook and `~/.claude/usage-status.json`.

## Run modes

### Desktop mode (Windows default)

Windows does not have the macOS menu bar API, so usage starts a small always-on-top draggable window by default. The window can switch between `All / Claude / Codex` and refreshes usage on a timer.

The desktop widget supports:

- dragging the upper-left grip to resize the window, so the control is less likely to be covered by other desktop widgets
- the `Alpha` slider for opacity
- `Pinned / Pin` to toggle always-on-top
- `Mini` mode, which shrinks the widget to one `Codex` or `Claude` `5h / Weekly` readout plus the last update time
- `Style` switching between `Classic / Taiwan / Matrix / ECG / Minimal / Sketch`, aligned with the macOS widget templates

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

You can also request desktop mode explicitly:

```powershell
python main.py --desktop
```

To launch without keeping a PowerShell window open, create a Windows shortcut that uses `pythonw.exe`, for example:

```powershell
E:\usage\.venv\Scripts\pythonw.exe E:\usage\main.py --desktop
```

### Web mode (URL / desktop widget)

If you want to embed usage in a desktop widget that renders a web URL, start web mode manually.

```powershell
.\.venv\Scripts\Activate.ps1
python main.py --web
```

The server prints these entry points:

- `http://127.0.0.1:8765/` — the main page, with product, theme, and layout switching
- `http://127.0.0.1:8765/?layout=compact` — compact layout on the same main page
- `http://127.0.0.1:8765/?layout=horizontal` — wide horizontal layout on the same main page
- `http://127.0.0.1:8765/api/usage` — JSON API

For a desktop widget, use `http://127.0.0.1:8765/?layout=compact` or `http://127.0.0.1:8765/?layout=horizontal`. To change the port:

```powershell
python main.py --web --port 9000
```

The main page has `All / Claude / Codex`, `Full / Compact / Wide`, and `Dark / Light` controls in the top-right corner. Choices are saved in browser localStorage. You can also pin them in the URL:

- `http://127.0.0.1:8765/?product=claude`
- `http://127.0.0.1:8765/?product=codex`
- `http://127.0.0.1:8765/?layout=compact`
- `http://127.0.0.1:8765/?layout=horizontal`

Dark mode is available from the `Dark / Light` toggle, and from URL parameters:

- `http://127.0.0.1:8765/?theme=dark`
- `http://127.0.0.1:8765/?layout=horizontal&theme=light`

### Menu bar mode (macOS default)

Stays in the macOS menu bar with a short percentage readout. Click it to open the full popover.

```bash
source .venv/bin/activate
python3 main.py
```

- **Menu bar format:** `🐾 37%`. If Codex usage is also detected, a Codex suffix is appended: `🐾 37% · 📜 10%`.

  <img src="docs/menubar.png" alt="menu bar display" width="240">

- **Click the icon to expand the popover.** It has three sections:
  1. Two cards for Claude Code and Codex, each with `5h` and `Weekly` progress bars and a reset countdown.
  2. A footer card showing current rate, sync status, and today's token usage and cost estimate (Claude uses the actual `costUSD` from its log when available; Codex cost is estimated from token count × pricing table).
  3. Two buttons: "Refresh now" and "Quit".
- **Switch panel** (v0.3.0+): a `⇄ Switch` button sits in the Claude Code card's top-right corner (the Taiwan panel embeds it in the top header bar instead) and opens a menu of available panel styles. Six are built in:
  - **Default**: the original two-card + footer layout.
  - **Taiwan usage monitor**: a red-on-white themed variant with a top header bar containing the TAIWAN flag icon.
  - **Matrix / 駭客任務** (v0.3.1+): animated digital-rain panel with cascading katakana characters, Matrix-green palette, and terminal bracket–style buttons.
  - **ECG**: medical-monitor style with two live ECG waveform channels — LEAD A for Claude Code and LEAD B for Codex. Waveform amplitude scales with quota usage; higher burn rate produces more intense peaks.
  - **Minimal** (v0.3.3+): dark minimal panel inspired by Linear / Raycast. Near-black background, rounded cards, accent-coloured progress bars (Claude warm-orange / Codex cyan). Footer card presents rate, status, and today's cost as a two-column label + value layout.
  - **手繪 / Sketch** (v0.3.4+): hand-drawn Excalidraw-style panel. Coral-pink background, off-white cards with thick black borders, corner pin decorations. Claude in deep orange-red, Codex in deep teal.

  <p align="center">
    <img src="docs/popover.png" alt="default panel" width="180">
    <img src="docs/popover-taiwan.png" alt="Taiwan usage monitor panel" width="180">
    <img src="docs/popover-matrix.png" alt="Matrix panel" width="180">
    <img src="docs/popover-ecg.png" alt="ECG panel" width="180">
    <img src="docs/popover-minimal.png" alt="Minimal panel" width="180">
    <img src="docs/popover-sketch.png" alt="Sketch panel" width="180">
  </p>

  Your choice is persisted via `NSUserDefaults`, so the last selected panel survives restarts.
- **Permissions:** on first launch, macOS may ask whether to allow background execution. Click Allow.

### Terminal TUI mode

If you'd rather stay in a terminal, run the Rich Live TUI — everything draws inside your terminal window via repeated text repaints. You get a pixel-art Claude logo, a spinner, a rotating set of Claude Code's playful loading phrases, and the same two progress bars as the menu bar popover:

<p align="center">
  <img src="docs/tui.png" alt="usage TUI mode" width="480">
</p>

```bash
source .venv/bin/activate
python3 main.py --tui
```

Press `Ctrl+C` to exit.

## Auto-start on login

A LaunchAgent (the macOS service that handles "what should start when this user logs in") makes usage start automatically.

1. **Install:**
   ```bash
   ./scripts/install-launchagent.sh
   ```
   This drops a plist into `~/Library/LaunchAgents/` and loads usage immediately.

2. **Manual start (for testing):**
   ```bash
   launchctl start com.lollapalooza.usage
   ```

3. **Logs:**
   - stdout: `~/Library/Logs/usage/usage.log`
   - stderr: `~/Library/Logs/usage/usage.err.log`

4. **Uninstall:**
   ```bash
   ./scripts/uninstall-launchagent.sh
   ```

## Preview mode (no install required)

If you haven't installed the hook yet, or you just want to see what the UI looks like, run with fake data:

```bash
# Menu bar preview
python3 main.py --mock

# Web preview (Windows / browser / widget)
python3 main.py --web --mock

# Desktop preview (Windows mini window)
python main.py --desktop --mock

# TUI preview
python3 main.py --tui --mock
```

## Options

- `--setup` / `--unsetup` — install or remove the Claude Code statusLine hook.
- `--desktop` — start the cross-platform desktop mini window (default on Windows).
- `--web` — start the cross-platform web UI.
- `--host HOST` — web server bind address, default `127.0.0.1`.
- `--port PORT` — web server port, default `8765`.
- `--tui` — force terminal TUI mode (no menu bar).
- `--interval N` — how often (seconds) the UI re-reads the status file. Minimum 30, default 60.
- `--mock` — use fake data; don't read any status file.
- `--force-group {0,1,2,3}` — force a specific rate group (TUI only).

## Debug

To see internal warnings (e.g. swallowed `OSError`s), set:

```bash
USAGE_DEBUG=1 python3 main.py
```

Windows PowerShell:

```powershell
$env:USAGE_DEBUG="1"; python main.py --web
```

## Behaviour notes

- usage only reads `~/.claude/usage-status.json`, the v0.1.x legacy `~/.claude/usag-status.json`, `~/.claude/tt-status.json`, and Codex's session files. It does not call the Anthropic / OpenAI API and does not read the Keychain. The only network activity is a one-time download of the LiteLLM pricing table for Codex cost estimates (cached for 7 days; offline fallback available).
- When Claude Code isn't running, the status file isn't updated — but actual usage isn't changing either (until reset time), so the displayed value is still accurate. After reset time passes, it auto-resets to zero.
- If the status file hasn't been updated for more than 6 hours, the status line notes "status file is N minutes stale, numbers may be out of date."

## Troubleshooting

The "Fix" column distinguishes three kinds of users — find yours first:

- **.app users** — downloaded `usage.app.zip` from GitHub Releases, unzipped, dragged `usage.app` to `/Applications`, double-click to launch like any Mac app. No Terminal, no Python.
- **Desktop / Windows users** — run `python main.py` or `python main.py --desktop` from source to open a small desktop window.
- **Web / widget users** — run `python main.py --web` from source, then open the URL in a browser or desktop widget.
- **LaunchAgent users** — cloned the source and ran `./scripts/install-launchagent.sh` so macOS auto-starts usage on login.
- **Source users** — cloned the source and run `python3 main.py` manually in Terminal each time.

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Menu bar shows `--` | Hook not installed, or Claude Code hasn't refreshed yet | **.app users**: click the "立即安裝 hook" button in the popover. **Source users**: run `python3 main.py --setup`. Either way, restart Claude Code once afterwards |
| `python main.py` on Windows does not open a native window | Tkinter is unavailable, or the current environment cannot open a GUI | Use `python main.py --web`, or install Python with Tkinter support |
| Desktop widget cannot open the URL | The usage web server is not running, or the port changed/is occupied | Run `python main.py --web` again and copy the printed URL. If you changed the port, update the widget URL too |
| Accidentally hit "Quit", paw icon disappeared from the menu bar | "Quit" fully terminates the usage process; you have to relaunch it | **.app users**: press `Cmd+Space` for Spotlight, type `usage`, hit Enter; or double-click `usage.app` from `/Applications`. **LaunchAgent users**: run `launchctl start com.lollapalooza.usage` in Terminal. **Source users**: run `python3 main.py` in Terminal again |
| Status says "N minutes stale" | Claude Code isn't running | Open Claude Code and let it run; it updates the file on its next status refresh |
| Codex section is empty | `~/.codex/sessions/` doesn't exist or has no `rate_limits` events yet | Run a Codex conversation to generate log entries |
| Today's cost shows $0.00 | Model name doesn't match the pricing table, or pricing download/cache failed | Delete `~/.claude/pricing_cache.json` to force a re-fetch; or run with `USAGE_DEBUG=1` for details |
| App won't open (blocked by macOS) | Gatekeeper blocks unsigned apps | Finder → find `usage.app` → right-click → Open → confirm Open |

## Build a .app bundle (optional)

If you want to launch usage by double-clicking instead of opening a terminal, build a native macOS app bundle:

```bash
./scripts/build_app.sh
```

The output is `dist/usage.app`. Double-click it or run `open dist/usage.app`.

Each GitHub Release build (push a `v*` tag) automatically builds the app in CI and attaches `usage.app.zip` to the Release page.

## Build a Windows exe

On Windows, package a single-file exe with PyInstaller:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_exe.ps1
```

The output is `dist\usage.exe`. The `Windows exe` GitHub Actions workflow also builds it on `v*` tags or manual dispatch, uploads `usage.exe` as an artifact, and attaches it to the Release for tag builds.
