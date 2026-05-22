# usage

繁體中文 · [English](README.en.md)

[![CI](https://github.com/yanowo/usage/actions/workflows/check.yml/badge.svg)](https://github.com/yanowo/usage/actions/workflows/check.yml)
[![Latest Release](https://img.shields.io/github/v/release/yanowo/usage)](https://github.com/yanowo/usage/releases/latest)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Web-lightgrey.svg)](README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

`usage` 是一個本機用量監控工具，用來顯示 **Claude Code** 與 **Codex** 的 5 小時、Weekly、今日 token 與成本估算。

目前支援三種主要使用方式：

- **macOS**：選單列 menu bar app，點開後顯示完整 popover 面板。
- **Windows**：桌面小工具，支援置頂、透明度、Mini 模式、縮到狀態條、外接螢幕拖曳。
- **Web**：本機 HTTP 頁面與 JSON API，可給瀏覽器、桌面擺件、Rainmeter 類工具或內嵌面板使用。

本專案基於上游 [aqua5230/usage](https://github.com/aqua5230/usage) 延伸；若散布 fork 或衍生版本，請保留上游專案連結與授權資訊。

<p align="center">
  <img src="docs/popover.png" alt="usage macOS popover" width="320">
</p>

## 核心特性

- 本機讀取用量，不呼叫 Anthropic / OpenAI API。
- Claude Code 用量來自官方 `statusLine` JSON 裡的 `rate_limits`。
- Codex 用量來自 `~/.codex/sessions/**/*.jsonl` 的 `rate_limits` 與 token 記錄。
- macOS 內建 6 種面板：預設、台灣用量監控、駭客任務、ECG、Minimal、手繪。
- Windows 桌面版支援 `All / Claude / Codex`、透明度、置頂、Mini、小狀態條、多螢幕拖曳。
- Web 版支援 `Full / Compact / Wide`、`All / Claude / Codex`、亮暗色與 `/api/usage`。
- 可用 mock 模式預覽 UI，不需要先安裝 Claude hook。

## 資料來源

### Claude Code

Claude Code 的資料來源是官方 `statusLine` hook。`usage` 會把 `usage_statusline.py` 安裝到 `~/.claude/usage-statusline.py`，並更新 `~/.claude/settings.json`：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/usage-statusline.py",
    "refreshInterval": 1
  }
}
```

Claude Code 刷新 status line 時會把當前 session JSON 餵給 hook，hook 只做一件事：把 JSON 寫到 `~/.claude/usage-status.json`。`usage` 再讀這份檔案中的：

- `rate_limits.five_hour.used_percentage`
- `rate_limits.seven_day.used_percentage`
- `rate_limits.*.resets_at`
- `context_window`
- `cost`

Claude 狀態檔讀取順序不是死吃第一個檔案；如果多份檔案同時存在，會選「最新且有 quota 資料」的快照：

1. `~/.claude/usage-status.json`
2. `~/.claude/usag-status.json`，舊版 legacy fallback
3. `~/.claude/tt-status.json`，token-tracker 相容 fallback

`/usage` 是 Claude Code 的互動式指令，不是穩定 JSON API；本專案不解析 `/usage` 畫面文字。

### Codex

Codex CLI 沒有 Claude Code 那種 statusLine hook，所以 `usage` 會掃描：

```text
~/.codex/sessions/**/*.jsonl
```

Codex 記錄中若出現 `rate_limits`，會依視窗長度對應：

- `window_minutes=300`：5 小時 quota
- `window_minutes=10080`：Weekly quota

今日 token 與成本估算會從同一批 session log 加總。沒安裝 Codex、沒有 session 目錄、或 log 還沒有 `rate_limits` 時，Codex 區塊會顯示空資料，不影響 Claude 顯示。

### 成本估算

用量百分比不需要網路。只有在估算 Codex 成本、且本機沒有價格表快取時，`usage` 會嘗試下載公開的 LiteLLM pricing JSON，並快取到：

```text
~/.claude/pricing_cache.json
```

下載失敗時會用內建 fallback 價格，不影響 quota 百分比。

## 系統需求

- macOS 或 Windows
- Python 3.13 以上
- 已安裝並登入 Claude Code
- Codex CLI 可選

Windows 版桌面小工具需要 Python 內含 Tkinter。若你的 Python 沒有 Tkinter，可以改用 Web 模式。

## 快速開始

### 1. 取得專案

```bash
git clone https://github.com/yanowo/usage.git
cd usage
```

如果你要使用上游原版，請改用 [aqua5230/usage](https://github.com/aqua5230/usage)。

### 2. 建立環境

macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### 3. 安裝 Claude Code hook

原始碼模式第一次使用必跑：

```bash
python3 main.py --setup
```

Windows PowerShell：

```powershell
python main.py --setup
```

完成後請完整重啟 Claude Code，讓它重新讀取 `~/.claude/settings.json`。重啟後 Claude Code 下一次刷新 statusLine 時，`~/.claude/usage-status.json` 才會更新。

卸載 hook：

```bash
python3 main.py --unsetup
```

Windows PowerShell：

```powershell
python main.py --unsetup
```

## 使用方式

### macOS Menu Bar

macOS 預設會啟動 menu bar app：

```bash
source .venv/bin/activate
python3 main.py
```

啟動後右上角會出現 `usage` 狀態項。點開後會顯示 Claude / Codex 兩組 quota、目前速率、同步狀態、今日 token 與成本。

內建面板：

- **預設**：兩張 quota 卡片與底部狀態卡。
- **台灣用量監控**：紅白主題與台灣標題列。
- **駭客任務**：黑底綠字與 Matrix 數位雨動畫。
- **ECG**：醫療監視器風格，Claude / Codex 各一條動態波形。
- **Minimal**：深色簡約風格。
- **手繪**：Excalidraw 類手繪風格。

<p align="center">
  <img src="docs/popover.png" alt="預設面板" width="180">
  <img src="docs/popover-taiwan.png" alt="台灣用量監控面板" width="180">
  <img src="docs/popover-matrix.png" alt="駭客任務面板" width="180">
  <img src="docs/popover-ecg.png" alt="ECG 面板" width="180">
  <img src="docs/popover-minimal.png" alt="Minimal 面板" width="180">
  <img src="docs/popover-sketch.png" alt="手繪面板" width="180">
</p>

若你下載的是 `.app` 版本，第一次開啟可能被 Gatekeeper 擋下。解法是 Finder 找到 `usage.app`，按住 Ctrl 右鍵，選「打開」，再確認一次。

### Windows Desktop

Windows 預設會啟動桌面小工具：

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

也可以明確指定：

```powershell
python main.py --desktop
```

桌面小工具功能：

- `All / Claude / Codex` 切換顯示範圍。
- `Refresh` 立即刷新。
- `Pinned / Pin` 切換是否置頂。
- `Alpha` 調整透明度。
- `Mini` 縮成單產品小卡。
- `_` 縮到狀態條小工具；狀態條可拖曳，支援外接螢幕。
- `Style` 切換 Classic / Taiwan / Matrix / ECG / Minimal / Sketch。

如果不想保留 PowerShell 視窗，可以建立捷徑並使用 `pythonw.exe`：

```powershell
E:\usage\.venv\Scripts\pythonw.exe E:\usage\main.py --desktop
```

請把路徑換成你的實際專案位置。

### Web

Web 模式會啟動本機 HTTP server：

```bash
python3 main.py --web
```

Windows PowerShell：

```powershell
python main.py --web
```

預設網址：

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/?layout=compact`
- `http://127.0.0.1:8765/?layout=horizontal`
- `http://127.0.0.1:8765/api/usage`

可用參數：

```bash
python3 main.py --web --host 127.0.0.1 --port 8765
```

若要讓同一區網其他裝置連進來，可改成：

```bash
python3 main.py --web --host 0.0.0.0 --port 8765
```

請自行確認防火牆與網路安全設定。預設綁定 `127.0.0.1`，只允許本機連線。

Web UI 支援 URL 參數：

- `?product=all`
- `?product=claude`
- `?product=codex`
- `?layout=full`
- `?layout=compact`
- `?layout=horizontal`
- `?theme=dark`
- `?theme=light`

桌面擺件通常建議使用：

```text
http://127.0.0.1:8765/?layout=compact
```

或寬版：

```text
http://127.0.0.1:8765/?layout=horizontal
```

### TUI

終端機文字介面：

```bash
python3 main.py --tui
```

Windows PowerShell：

```powershell
python main.py --tui
```

<p align="center">
  <img src="docs/tui.png" alt="usage TUI" width="480">
</p>

按 `Ctrl+C` 離開。

## Mock 預覽

還沒安裝 hook、或只想看 UI，可加 `--mock`：

```bash
python3 main.py --mock
python3 main.py --web --mock
python3 main.py --desktop --mock
python3 main.py --tui --mock
```

Windows PowerShell：

```powershell
python main.py --desktop --mock
python main.py --web --mock
```

## CLI 參數

| 參數 | 說明 |
|------|------|
| `--setup` | 安裝 Claude Code statusLine hook |
| `--unsetup` | 移除 hook，並還原原本的 statusLine 設定 |
| `--desktop` | 啟動桌面小工具 |
| `--web` | 啟動 Web UI 與 JSON API |
| `--host HOST` | Web 綁定位址，預設 `127.0.0.1` |
| `--port PORT` | Web port，預設 `8765` |
| `--tui` | 啟動終端機 TUI |
| `--interval N` | 重新讀取資料間隔，最小 30 秒，預設 60 秒 |
| `--mock` | 使用假資料預覽 |
| `--force-group {0,1,2,3}` | TUI 測試用，強制速率分組 |

平台預設：

- Windows：`python main.py` 等同 desktop。
- macOS：`python3 main.py` 等同 menu bar。
- 其他平台：`python3 main.py` 會 fallback 到 Web。

## 開機自動啟動

### macOS LaunchAgent

```bash
./scripts/install-launchagent.sh
```

查看 log：

```text
~/Library/Logs/usage/usage.log
~/Library/Logs/usage/usage.err.log
```

移除：

```bash
./scripts/uninstall-launchagent.sh
```

### Windows

可以把下列指令做成捷徑，放進 Windows Startup 資料夾：

```powershell
E:\usage\.venv\Scripts\pythonw.exe E:\usage\main.py --desktop
```

Web 模式則可建立：

```powershell
E:\usage\.venv\Scripts\pythonw.exe E:\usage\main.py --web
```

## 打包

### macOS `.app`

```bash
./scripts/build_app.sh
```

輸出：

```text
dist/usage.app
```

### Windows `.exe`

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_exe.ps1
```

輸出：

```text
dist\usage.exe
```

## 開發與驗證

安裝開發工具：

```bash
pip install pytest ruff mypy
```

執行檢查：

```bash
pytest
ruff check .
mypy .
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe .
```

## 常見問題

| 問題 | 可能原因 | 解法 |
|------|----------|------|
| Claude 顯示 `--` | hook 未安裝，或 Claude Code 尚未刷新 statusLine | 跑 `python main.py --setup`，重啟 Claude Code，等它刷新一次 |
| Claude 顯示 0%，但 `/usage` 看起來不是 0% | 本地 `usage-status.json` 還是舊快照，或目前使用的是 IDE entrypoint 且沒有刷新 statusLine | 重啟原生 Claude Code，確認 `~/.claude/settings.json` 有 `refreshInterval: 1` |
| 狀態顯示 stale / 未更新 | Claude Code 很久沒有寫入新的 statusLine JSON | 打開 Claude Code，讓它觸發一次回應或 statusLine 刷新 |
| Codex 區塊沒有資料 | 沒有 `~/.codex/sessions`，或 log 尚未出現 `rate_limits` | 用 Codex 跑一次對話後再刷新 |
| Windows 沒有出現桌面小工具 | Tkinter 不可用，或 GUI 環境異常 | 改用 `python main.py --web`，或安裝含 Tkinter 的 Python |
| Web URL 打不開 | server 沒啟動、port 被占用、host 不一致 | 重新執行 `python main.py --web`，看終端機印出的實際 URL |
| 今日成本是 `$0.00` | 沒有成本記錄、pricing cache 失效，或模型名稱無法對應 | 刪除 `~/.claude/pricing_cache.json` 讓它重抓，或用 `USAGE_DEBUG=1` 查看細節 |
| macOS `.app` 打不開 | Gatekeeper 擋未簽章 app | Finder 中 Ctrl + 右鍵 `usage.app`，選「打開」 |

## 除錯

啟用 debug log：

```bash
USAGE_DEBUG=1 python3 main.py
```

Windows PowerShell：

```powershell
$env:USAGE_DEBUG="1"
python main.py --web
```

常用檢查：

```bash
cat ~/.claude/settings.json
cat ~/.claude/usage-status.json
```

Windows PowerShell：

```powershell
Get-Content -Raw $env:USERPROFILE\.claude\settings.json
Get-Content -Raw $env:USERPROFILE\.claude\usage-status.json
```

## 隱私與網路

- 不讀 macOS Keychain。
- 不呼叫 Anthropic API。
- 不呼叫 OpenAI API。
- Claude quota 來自 Claude Code statusLine JSON。
- Codex quota 來自本機 Codex session log。
- 唯一預期網路行為是下載公開 LiteLLM pricing JSON 供成本估算，並會快取。
- Web 模式預設只綁定 `127.0.0.1`。

## 致謝、授權與上游

本 fork 基於原始 `usage` 專案，並延伸 Windows desktop、Web server、跨平台 CLI、Windows 打包與多螢幕小工具等功能。

| 項目 | 連結 |
|------|------|
| 原作者 / 上游專案 | [lollapalooza · aqua5230/usage](https://github.com/aqua5230/usage) |
| 本 fork | [yanowo/usage](https://github.com/yanowo/usage) |
| 本 fork 授權 | [MIT License](LICENSE) |

> 若你 fork、修改或重新發布，請保留這段 attribution 與上游專案連結。
