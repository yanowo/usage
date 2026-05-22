#!/bin/bash
set -euo pipefail

LABEL="com.yanowo.usagemonitor"
PLIST_NAME="${LABEL}.plist"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
LEGACY_LABELS=("com.lollapalooza.usage" "com.lollapalooza.usag")

echo "正在卸載 LaunchAgent..."
launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
fi
for legacy_label in "${LEGACY_LABELS[@]}"; do
    if launchctl print "gui/$(id -u)/${legacy_label}" >/dev/null 2>&1; then
        launchctl bootout "gui/$(id -u)/${legacy_label}" 2>/dev/null || true
    fi
done

echo "正在移除檔案..."
rm -f "${TARGET_PLIST}"
for legacy_label in "${LEGACY_LABELS[@]}"; do
    rm -f "${HOME}/Library/LaunchAgents/${legacy_label}.plist"
done
rm -f "${HOME}/Library/Logs/usage-monitor/usage-monitor.log"
rm -f "${HOME}/Library/Logs/usage-monitor/usage-monitor.err.log"
rmdir "${HOME}/Library/Logs/usage-monitor" 2>/dev/null || true
rm -f "${HOME}/Library/Logs/usage/usage.log"
rm -f "${HOME}/Library/Logs/usage/usage.err.log"
rmdir "${HOME}/Library/Logs/usage" 2>/dev/null || true

echo "✓ 已移除"
