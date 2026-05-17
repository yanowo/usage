# usag

[繁體中文](README.md) · English

`usag` is a macOS tool for Claude Code users that displays your 5-hour and 7-day usage in the right-hand menu bar or a terminal TUI, with optional auto-start on login.

<p align="center">
  <img src="docs/popover.png" alt="usag popover" width="320">
</p>

## How it gets the data

usag **never calls the Anthropic API and never reads the Keychain**, so it avoids the observer effect of "pinging once a minute counts as usage."

Instead it installs a Claude Code statusLine hook. Every time the Claude Code main process refreshes its status line, it pipes a JSON payload (with fields like `rate_limits.five_hour.used_percentage`) into the hook. The hook writes that payload to `~/.claude/usag-status.json`, and the usag UI reads the file. The numbers match exactly what Claude Code itself sees.

Read priority:

1. `~/.claude/usag-status.json` — written by the hook usag installs.
2. `~/.claude/tt-status.json` — fallback. If you also use [token-tracker](https://github.com/stormzhang/token-tracker), usag will share its status file.

## Requirements

- macOS
- Python 3.13
- Claude Code installed and signed in
- Recommended: use a GitHub noreply email as your commit identity so your private email doesn't leak: `git config user.email "ID+username@users.noreply.github.com"`

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

## First install

Run setup once to write the statusLine hook into your Claude Code settings, then **restart Claude Code once** so it re-reads `~/.claude/settings.json` and refreshes its status line (which is when the data first lands on disk):

```bash
source .venv/bin/activate
python3 main.py --setup
# restart Claude Code once
```

Setup will:

- Copy `usag_statusline.py` to `~/.claude/usag-statusline.py`.
- Point `statusLine` in `~/.claude/settings.json` at that hook.
- If you already had a custom `statusLine`, it is backed up to `settings.usag.previousStatusLine`.

To uninstall:

```bash
python3 main.py --unsetup
```

`--unsetup` restores your original statusLine and removes the hook and `~/.claude/usag-status.json`.

## Run modes

### Menu bar mode (default)

Stays in the macOS menu bar and shows the current 5-hour usage percentage.

```bash
source .venv/bin/activate
python3 main.py
```

- **Display format:** `🐾 37%`; if Codex usage is also detected, a suffix like `· 📜 10%` is appended:

  <img src="docs/menubar.png" alt="menu bar display" width="240">

- **Dropdown:** detailed 5-hour and weekly usage, reset times, current rate, and sync status.
- **Permissions:** on first launch, macOS may ask whether to allow background execution.

### Terminal TUI mode

Keeps the original Rich Live interface, including the pixel-art Clawd animation.

```bash
source .venv/bin/activate
python3 main.py --tui
```

## Auto-start on login

A LaunchAgent makes usag start automatically when you log in:

1. **Install:**
   ```bash
   ./install-launchagent.sh
   ```
2. **Manual start (for testing):**
   ```bash
   launchctl start com.lollapalooza.usag
   ```
3. **Logs:**
   - stdout: `~/Library/Logs/usag/usag.log`
   - stderr: `~/Library/Logs/usag/usag.err.log`
4. **Uninstall:**
   ```bash
   ./uninstall-launchagent.sh
   ```

## Preview mode

If you haven't installed the hook yet, or you just want to see what the UI looks like, run with fake data:

```bash
# Menu bar preview
python3 main.py --mock

# TUI preview
python3 main.py --tui --mock
```

## Options

- `--setup` / `--unsetup` — install or remove the Claude Code statusLine hook.
- `--tui` — force terminal TUI mode.
- `--interval N` — how often (seconds) the UI re-reads the status file. Minimum 30, default 60.
- `--mock` — use fake data; don't read any status file.
- `--force-group {0,1,2,3}` — force a specific rate group (TUI only).

## Debug

To see internal warnings (e.g. swallowed `OSError`s), set:

```bash
USAG_DEBUG=1 python3 main.py
```

## Behavior notes

- usag only reads `~/.claude/usag-status.json` or `~/.claude/tt-status.json`. It does not make network calls and does not read the Keychain.
- When Claude Code isn't running, the status file isn't updated — but actual usage isn't changing either (until reset time), so the displayed value is still accurate. After reset time passes, it auto-resets to zero.
- If the status file hasn't been updated for more than 6 hours, the status line notes "status file is N minutes stale, numbers may be out of date."

## Self-check commands

```bash
source .venv/bin/activate
ruff check .
mypy .
pytest -v
python3 main.py --tui --mock
```
