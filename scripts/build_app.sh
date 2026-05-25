#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$BASH_SOURCE")/.."
rm -rf build dist
uv sync --group build
uv run python3 setup_app.py py2app

if [[ ! -d dist/usage.app ]]; then
  for candidate in "dist/Usage Monitor.app" "dist/main.app"; do
    if [[ -d "$candidate" ]]; then
      mv "$candidate" dist/usage.app
      break
    fi
  done
fi

if [[ ! -d dist/usage.app ]]; then
  echo "Missing app bundle: dist/usage.app"
  ls -l dist || true
  exit 1
fi

echo "Built: dist/usage.app"
