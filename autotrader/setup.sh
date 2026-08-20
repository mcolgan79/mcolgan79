#!/usr/bin/env bash
# autotrader first-time setup (macOS / Linux).
# Creates a virtual environment, installs the package, and stores your Alpaca
# paper credentials in ~/.autotrader/
set -euo pipefail
cd "$(dirname "$0")"

echo "=========================================="
echo "  autotrader setup"
echo "=========================================="

PYCMD=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        PYCMD="$candidate"
        break
    fi
done
if [ -z "$PYCMD" ]; then
    echo "ERROR: Python 3.11 or newer is required (this project uses tomllib)." >&2
    echo "Install it from https://www.python.org/downloads/ or via your package manager." >&2
    exit 1
fi
echo "[1/4] Using $("$PYCMD" --version)"

if [ -x ".venv/bin/python" ]; then
    echo "[2/4] Reusing existing .venv"
else
    echo "[2/4] Creating .venv ..."
    "$PYCMD" -m venv .venv
fi

echo "[3/4] Installing autotrader and its dependencies ..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -e . --quiet

CFGDIR="$HOME/.autotrader"
mkdir -p "$CFGDIR"

if [ -f "$CFGDIR/config.toml" ]; then
    echo "[4/4] Config already exists at $CFGDIR/config.toml"
else
    echo "[4/4] Writing default config to $CFGDIR/config.toml"
    cp config.example.toml "$CFGDIR/config.toml"
fi

if [ -f "$CFGDIR/.env" ]; then
    echo
    echo "Credentials already present at $CFGDIR/.env"
    echo "Delete that file and re-run this script to change them."
else
    echo
    echo "Enter your Alpaca PAPER API credentials."
    echo "Get them at https://app.alpaca.markets/paper/dashboard/overview -> API Keys"
    echo "The key ID starts with PK. The secret is only shown once when you create it."
    echo
    read -r -p "  API Key ID   : " KEYID
    read -r -s -p "  Secret Key   : " SECRET
    echo
    if [ -z "$KEYID" ] || [ -z "$SECRET" ]; then
        echo "ERROR: both the key ID and the secret are required." >&2
        exit 1
    fi
    umask 077
    printf 'APCA_API_KEY_ID=%s\nAPCA_API_SECRET_KEY=%s\n' "$KEYID" "$SECRET" > "$CFGDIR/.env"
    chmod 600 "$CFGDIR/.env"
    echo "Credentials saved to $CFGDIR/.env (readable only by you)"
fi

echo
echo "=========================================="
echo "  Checking the connection"
echo "=========================================="
if ! .venv/bin/trader doctor; then
    echo
    echo "Setup finished, but the connection check failed -- see the errors above." >&2
    echo "The most common causes are a mistyped secret key, or keys from the live" >&2
    echo "dashboard instead of the paper one." >&2
    exit 1
fi

echo
echo "Setup complete. From now on use ./trader.sh, for example:"
echo
echo "    ./trader.sh status"
echo "    ./trader.sh backtest"
echo "    ./trader.sh run --once --dry-run"
