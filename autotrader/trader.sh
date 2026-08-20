#!/usr/bin/env bash
# autotrader launcher (macOS / Linux). Run ./setup.sh once first.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ ! -x "$HERE/.venv/bin/trader" ]; then
    echo "autotrader is not set up yet on this machine. Run ./setup.sh first." >&2
    exit 1
fi
exec "$HERE/.venv/bin/trader" "$@"
