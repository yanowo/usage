#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python3"
LABEL="com.yanowo.usagemonitor"
PLIST_NAME="${LABEL}.plist"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
LEGACY_LABELS=("com.lollapalooza.usage" "com.lollapalooza.usag")

if [ ! -f "$VENV_PYTHON" ]; then
    echo "錯誤：找不到虛擬環境中的 Python ($VENV_PYTHON)"
    exit 1
fi

for legacy_label in "${LEGACY_LABELS[@]}"; do
    if launchctl print "gui/$(id -u)/${legacy_label}" >/dev/null 2>&1; then
        launchctl bootout "gui/$(id -u)/${legacy_label}" 2>/dev/null || true
    fi
    rm -f "${HOME}/Library/LaunchAgents/${legacy_label}.plist"
done

mkdir -p "${HOME}/Library/Logs/usage-monitor"

echo "正在生成設定檔..."
sed -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__VENV_PYTHON__|${VENV_PYTHON}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "${SCRIPT_DIR}/${PLIST_NAME}" > "${TARGET_PLIST}"

echo "正在載入 LaunchAgent..."
launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
launchctl load "${TARGET_PLIST}"

echo "ℹ 已清掉舊 com.lollapalooza.* LaunchAgent（如果有）"
echo "✓ 已安裝，下次登入會自動啟動。手動測試：launchctl start ${LABEL}"
