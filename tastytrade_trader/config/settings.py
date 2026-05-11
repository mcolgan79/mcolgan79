import json
import os
import keyring
from pathlib import Path
from typing import Optional

APP_NAME = "TastyTradeTrader"
CONFIG_DIR = Path.home() / ".tastytrade_trader"
CONFIG_FILE = CONFIG_DIR / "config.json"
TRADES_FILE = CONFIG_DIR / "trades.json"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


class SettingsManager:
    def __init__(self):
        ensure_config_dir()
        self._data = self._load()

    def _load(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "account_number": None,
            "use_sandbox": False,
            "dry_run": False,
            "strategies": [],
            "username": None,
            "scan_interval_seconds": 60,
            "theme": "dark",
        }

    def save(self):
        ensure_config_dir()
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    # ---- credential helpers (stored in OS keychain) ----

    def save_credentials(self, username: str, password: str):
        self._data["username"] = username
        self.save()
        keyring.set_password(APP_NAME, username, password)

    def load_credentials(self) -> tuple[Optional[str], Optional[str]]:
        username = self._data.get("username")
        if not username:
            return None, None
        password = keyring.get_password(APP_NAME, username)
        return username, password

    def clear_credentials(self):
        username = self._data.get("username")
        if username:
            try:
                keyring.delete_password(APP_NAME, username)
            except Exception:
                pass
        self._data["username"] = None
        self.save()

    # ---- strategy storage ----

    def get_strategies(self) -> list:
        return self._data.get("strategies", [])

    def save_strategies(self, strategies: list):
        self._data["strategies"] = strategies
        self.save()

    # ---- general settings ----

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    # ---- trade log ----

    def append_trade(self, trade: dict):
        ensure_config_dir()
        trades = self.load_trades()
        trades.append(trade)
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)

    def load_trades(self) -> list:
        if TRADES_FILE.exists():
            try:
                with open(TRADES_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []
