#!/usr/bin/env bash
# Build a standalone `trader` binary that runs without Python installed.
# Run ./setup.sh first, then: ./scripts/build-exe.sh
# The result lands in dist/trader.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
    echo "Run ./setup.sh first -- this build needs the project's virtual environment." >&2
    exit 1
fi

echo "Installing PyInstaller ..."
.venv/bin/python -m pip install --quiet "pyinstaller>=6"

echo "Building dist/trader (this takes a minute) ..."
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
    --name trader \
    --collect-all alpaca \
    --collect-submodules autotrader \
    --add-data "src/autotrader/web/static:autotrader/web/static" \
    scripts/trader_entry.py

echo
echo "Built dist/trader"
echo "It reads its config and credentials from ~/.autotrader/, so it works from"
echo "any directory. Try:  ./dist/trader status"
