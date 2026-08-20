#!/usr/bin/env bash
# autotrader first-time setup (macOS / Linux).
# Creates a virtual environment, installs the package, and stores your Alpaca
# paper credentials in ~/.autotrader/
#
# If your Python 3.11+ lives somewhere unusual, point at it directly:
#     PYTHON=/opt/homebrew/bin/python3.12 ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "=========================================="
echo "  autotrader setup"
echo "=========================================="

MIN_VERSION_CHECK='import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'

version_of() {
    "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo "unknown"
}

is_new_enough() {
    "$1" -c "$MIN_VERSION_CHECK" >/dev/null 2>&1
}

# Candidate interpreters, best first. Homebrew and the python.org installer put
# their binaries outside the default PATH on some machines, so check directly.
CANDIDATES=(
    python3.14 python3.13 python3.12 python3.11
    /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13
    /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11
    /opt/homebrew/bin/python3
    /usr/local/bin/python3.14 /usr/local/bin/python3.13
    /usr/local/bin/python3.12 /usr/local/bin/python3.11
    /usr/local/bin/python3
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3
    python3 /usr/bin/python3
)

PYCMD=""
if [ -n "${PYTHON:-}" ]; then
    # An explicit choice is honored, or refused with a reason -- never ignored.
    if ! command -v "$PYTHON" >/dev/null 2>&1 && [ ! -x "$PYTHON" ]; then
        echo "ERROR: PYTHON=$PYTHON is not an executable this shell can find." >&2
        exit 1
    fi
    if ! is_new_enough "$PYTHON"; then
        echo "ERROR: PYTHON=$PYTHON is version $(version_of "$PYTHON"); 3.11 or newer is required." >&2
        exit 1
    fi
    PYCMD="$PYTHON"
else
    for candidate in "${CANDIDATES[@]}"; do
        if { command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; } &&
           is_new_enough "$candidate"; then
            PYCMD="$candidate"
            break
        fi
    done
fi

if [ -z "$PYCMD" ]; then
    echo
    echo "ERROR: no Python 3.11 or newer found. This project needs 3.11+ for tomllib." >&2
    echo >&2
    echo "Interpreters found on this machine:" >&2
    FOUND=""
    for candidate in "${CANDIDATES[@]}"; do
        if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
            RESOLVED="$(command -v "$candidate" 2>/dev/null || echo "$candidate")"
            case " $FOUND " in *" $RESOLVED "*) continue ;; esac
            FOUND="$FOUND $RESOLVED"
            echo "  $RESOLVED  ->  $(version_of "$candidate")" >&2
        fi
    done
    [ -n "$FOUND" ] || echo "  (none)" >&2
    echo >&2
    if [ "$(uname -s)" = "Darwin" ]; then
        echo "macOS ships Python 3.9, which is too old. Install a newer one:" >&2
        echo >&2
        echo "    brew install python@3.12          # if you have Homebrew" >&2
        echo >&2
        echo "or download the installer from https://www.python.org/downloads/macos/" >&2
        echo "Then re-run ./setup.sh" >&2
    else
        echo "Install Python 3.11+ from https://www.python.org/downloads/" >&2
        echo "or via your package manager, then re-run ./setup.sh" >&2
    fi
    echo >&2
    echo "Already have one somewhere unusual? Point at it directly:" >&2
    echo "    PYTHON=/path/to/python3.12 ./setup.sh" >&2
    exit 1
fi

if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "NOTE: another virtualenv is active ($VIRTUAL_ENV)."
    echo "      This script builds its own .venv, so that is fine, but running"
    echo "      'deactivate' first avoids confusion."
fi

echo "[1/4] Using $PYCMD ($(version_of "$PYCMD"))"

if [ -x ".venv/bin/python" ] && is_new_enough ".venv/bin/python"; then
    echo "[2/4] Reusing existing .venv"
else
    if [ -d ".venv" ]; then
        echo "[2/4] Replacing .venv (it was built with an older Python) ..."
        rm -rf .venv
    else
        echo "[2/4] Creating .venv ..."
    fi
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
