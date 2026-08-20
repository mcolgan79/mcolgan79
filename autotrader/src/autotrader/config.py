"""Configuration loading: TOML file + environment (with .env support).

Secrets never live in the config file -- they come from the environment, which
``load_dotenv`` will populate from a gitignored ``.env`` if one is present.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATHS = (
    Path("config.toml"),
    Path("~/.autotrader/config.toml"),
)

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd])?\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class ConfigError(Exception):
    """Raised when the config file is missing, malformed, or inconsistent."""


def parse_duration(value: str | int | float) -> int:
    """'15m' -> 900. Bare numbers are seconds."""
    if isinstance(value, (int, float)):
        return int(value)
    match = _DURATION_RE.match(value)
    if not match:
        raise ConfigError(f"invalid duration: {value!r} (try '30s', '15m', '1h')")
    amount, unit = match.groups()
    return int(float(amount) * _UNIT_SECONDS[(unit or "s").lower()])


def load_dotenv(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Minimal .env loader -- KEY=VALUE lines, '#' comments, optional quotes.

    Deliberately dependency-free; we only need the subset python-dotenv's users
    actually write.
    """
    env_path = Path(path) if path else Path(".env")
    loaded: dict[str, str] = {}
    if not env_path.is_file():
        return loaded
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


@dataclass
class BrokerConfig:
    name: str = "alpaca"
    paper: bool = True
    data_feed: str = "iex"  # free Alpaca plans get IEX; "sip" needs a subscription
    base_url: str | None = None


@dataclass
class GuardrailConfig:
    require_market_open: bool = True
    respect_calendar: bool = True
    max_open_strategies: int = 1
    allow_fractional: bool = False  # shorts are never fractional at Alpaca


@dataclass
class EngineConfig:
    execute: bool = True  # paper account: execute unless --dry-run is passed
    poll_interval: int = 900  # seconds, loop mode
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)


@dataclass
class StorageConfig:
    path: Path = Path("~/.autotrader/autotrader.db")

    def resolved(self) -> Path:
        return Path(self.path).expanduser()


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: Path | None = Path("~/.autotrader/autotrader.log")
    max_bytes: int = 5_000_000
    backups: int = 5

    def resolved_file(self) -> Path | None:
        return Path(self.file).expanduser() if self.file else None


@dataclass
class StrategyConfig:
    name: str = "pair_zscore"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    source_path: Path | None = None

    @property
    def api_key(self) -> str | None:
        return os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY_ID")

    @property
    def api_secret(self) -> str | None:
        return os.environ.get("APCA_API_SECRET_KEY") or os.environ.get(
            "ALPACA_API_SECRET_KEY"
        )

    def require_credentials(self) -> tuple[str, str]:
        if not self.api_key or not self.api_secret:
            raise ConfigError(
                "Missing Alpaca credentials. Set APCA_API_KEY_ID and "
                "APCA_API_SECRET_KEY in your environment or in a .env file "
                "(see .env.example)."
            )
        return self.api_key, self.api_secret


def find_config(explicit: Path | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
        return path
    for candidate in DEFAULT_CONFIG_PATHS:
        path = candidate.expanduser()
        if path.is_file():
            return path
    return None


def load_config(explicit: Path | None = None) -> Config:
    """Load config from TOML, falling back to built-in defaults when absent."""
    load_dotenv()
    path = find_config(explicit)
    if path is None:
        return Config()

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    cfg = Config(source_path=path)

    broker = raw.get("broker", {})
    cfg.broker = BrokerConfig(
        name=broker.get("name", cfg.broker.name),
        paper=broker.get("paper", cfg.broker.paper),
        data_feed=broker.get("data_feed", cfg.broker.data_feed),
        base_url=broker.get("base_url"),
    )

    engine = raw.get("engine", {})
    guards = engine.get("guardrails", {})
    cfg.engine = EngineConfig(
        execute=engine.get("execute", cfg.engine.execute),
        poll_interval=parse_duration(engine.get("poll_interval", "15m")),
        guardrails=GuardrailConfig(
            require_market_open=guards.get("require_market_open", True),
            respect_calendar=guards.get("respect_calendar", True),
            max_open_strategies=guards.get("max_open_strategies", 1),
            allow_fractional=guards.get("allow_fractional", False),
        ),
    )

    storage = raw.get("storage", {})
    cfg.storage = StorageConfig(path=Path(storage.get("path", cfg.storage.path)))

    logging_raw = raw.get("logging", {})
    log_file = logging_raw.get("file", cfg.logging.file)
    cfg.logging = LoggingConfig(
        level=str(logging_raw.get("level", cfg.logging.level)).upper(),
        file=Path(log_file) if log_file else None,
        max_bytes=int(logging_raw.get("max_bytes", cfg.logging.max_bytes)),
        backups=int(logging_raw.get("backups", cfg.logging.backups)),
    )

    strategy = raw.get("strategy", {})
    cfg.strategy = StrategyConfig(
        name=strategy.get("name", cfg.strategy.name),
        params=dict(strategy.get("params", {})),
    )
    return cfg


EXAMPLE_CONFIG = """\
# autotrader configuration.
# Credentials do NOT belong here -- put them in .env (see .env.example).

[broker]
name = "alpaca"       # alpaca | robinhood (planned) | tastytrade (planned)
paper = true          # keep this true until you have proven the strategy
data_feed = "iex"     # "iex" on free Alpaca plans, "sip" if you subscribe

[engine]
execute = true        # submit orders by default; `trader run --dry-run` overrides
poll_interval = "15m" # how often `trader run --loop` re-evaluates

[engine.guardrails]
require_market_open = true   # never trade outside regular hours
respect_calendar = true      # honor holidays and half-days
max_open_strategies = 1      # no pyramiding: one open pair position at a time
allow_fractional = false     # short legs must be whole shares anyway

[storage]
path = "~/.autotrader/autotrader.db"

[logging]
level = "INFO"
file = "~/.autotrader/autotrader.log"
max_bytes = 5000000
backups = 5

[strategy]
name = "pair_zscore"

[strategy.params]
symbol_a = "GLD"       # the "rich when z is high" leg
symbol_b = "GDX"
timeframe = "1Day"
lookback = 60          # bars in the rolling mean/std window
entry_z = 2.0          # |z| at or above this opens the pair
exit_z = 0.5           # |z| at or below this flattens (mean reversion achieved)
stop_z = 3.5           # |z| at or above this flattens (relationship broke)
leg_weight = 0.10      # each leg targets 10% of account equity
"""
