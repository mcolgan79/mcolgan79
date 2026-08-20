"""Config parsing, duration handling, and .env loading."""

from __future__ import annotations

import os

import pytest

from autotrader.config import (
    Config,
    ConfigError,
    EXAMPLE_CONFIG,
    load_config,
    load_dotenv,
    parse_duration,
)


@pytest.mark.parametrize(
    "value, seconds",
    [("30s", 30), ("15m", 900), ("1h", 3600), ("2d", 172800), ("45", 45), (60, 60)],
)
def test_duration_parsing(value, seconds):
    assert parse_duration(value) == seconds


def test_bad_duration_is_rejected():
    with pytest.raises(ConfigError, match="invalid duration"):
        parse_duration("soon")


def test_example_config_is_loadable_and_matches_the_documented_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(EXAMPLE_CONFIG)
    cfg = load_config(path)
    assert cfg.broker.name == "alpaca" and cfg.broker.paper is True
    assert cfg.broker.data_adjustment == "split"  # never "raw" for a price ratio
    assert cfg.engine.execute is True
    assert cfg.engine.poll_interval == 900
    assert cfg.engine.guardrails.require_market_open is True
    assert cfg.engine.guardrails.max_open_strategies == 1
    assert cfg.strategy.name == "pair_zscore"
    assert cfg.strategy.params["symbol_a"] == "GLD"
    assert cfg.strategy.params["symbol_b"] == "GDX"
    assert cfg.strategy.params["lookback"] == 60
    assert cfg.strategy.params["entry_z"] == 2.0


def test_missing_config_file_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_partial_config_keeps_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[strategy]\nname = "pair_zscore"\n\n[strategy.params]\nlookback = 90\n')
    cfg = load_config(path)
    assert cfg.strategy.params["lookback"] == 90
    assert cfg.broker.data_feed == "iex"  # untouched default
    assert cfg.engine.guardrails.respect_calendar is True


def test_dotenv_populates_the_environment_without_clobbering(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "APCA_API_KEY_ID=from_file\n"
        'APCA_API_SECRET_KEY="quoted_secret"\n'
        "\n"
        "EXISTING=from_file\n"
    )
    monkeypatch.setenv("EXISTING", "from_shell")
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    load_dotenv(env)

    assert os.environ["APCA_API_KEY_ID"] == "from_file"
    assert os.environ["APCA_API_SECRET_KEY"] == "quoted_secret"
    assert os.environ["EXISTING"] == "from_shell"  # the shell wins


def test_missing_credentials_raise_a_helpful_error(monkeypatch):
    for key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ConfigError, match="Missing Alpaca credentials"):
        Config().require_credentials()
