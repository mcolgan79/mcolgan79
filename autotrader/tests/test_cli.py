"""End-to-end CLI behavior with the broker swapped for the fake."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from autotrader import cli
from conftest import position, spreads_for_z

LOOKBACK = 20
runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch, fake_broker_factory):
    """A config pointing at temp storage, with a fake broker wired in."""
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
[broker]
name = "fake"
paper = true

[engine]
execute = true

[storage]
path = "{tmp_path / 'test.db'}"

[logging]
level = "WARNING"
file = ""

[strategy]
name = "pair_zscore"

[strategy.params]
symbol_a = "GLD"
symbol_b = "GDX"
lookback = {LOOKBACK}
entry_z = 2.0
exit_z = 0.5
stop_z = 3.5
leg_weight = 0.10
"""
    )

    def make(z: float = 2.4, **kwargs):
        broker = fake_broker_factory(spreads_for_z(z, LOOKBACK), **kwargs)
        monkeypatch.setattr(cli, "build_broker", lambda _cfg: broker)
        return broker

    return config, make


def invoke(config, *args):
    return runner.invoke(cli.app, ["--config", str(config), *args])


def test_signal_reports_the_z_score_without_trading(project):
    config, make = project
    broker = make(z=2.4)
    result = invoke(config, "signal")
    assert result.exit_code == 0
    assert "ENTER" in result.stdout
    assert broker.submitted == []


def test_run_once_submits_both_legs(project):
    config, make = project
    broker = make(z=2.4)
    result = invoke(config, "run", "--once")
    assert result.exit_code == 0
    assert {o.symbol for o in broker.submitted} == {"GLD", "GDX"}


def test_run_dry_run_submits_nothing(project):
    config, make = project
    broker = make(z=2.4)
    result = invoke(config, "run", "--once", "--dry-run")
    assert result.exit_code == 0
    assert "DRY RUN" in result.stdout
    assert broker.submitted == []


def test_run_exits_nonzero_when_a_leg_is_rejected(project):
    config, make = project
    make(z=2.4, fail_symbols={"GLD"})
    result = invoke(config, "run", "--once")
    assert result.exit_code == 1
    assert "failed" in result.stdout


def test_status_shows_account_and_positions(project):
    config, make = project
    make(z=0.5, positions={"GLD": position("GLD", -33, 300.0)})
    result = invoke(config, "status")
    assert result.exit_code == 0
    assert "equity" in result.stdout and "GLD" in result.stdout


def test_close_requires_confirmation_and_then_flattens(project):
    config, make = project
    broker = make(z=2.4, positions={"GLD": position("GLD", -33, 300.0)})
    assert invoke(config, "close").exit_code == 1  # declined at the prompt
    assert broker.submitted == []
    result = invoke(config, "close", "--yes")
    assert result.exit_code == 0
    assert [o.symbol for o in broker.submitted] == ["GLD"]


def test_history_reads_back_what_run_recorded(project):
    config, make = project
    make(z=2.4)
    invoke(config, "run", "--once")
    result = invoke(config, "history")
    assert "enter" in result.stdout
    orders = invoke(config, "history", "--orders")
    assert "GLD" in orders.stdout


def test_closed_market_is_reported_not_traded(project):
    config, make = project
    broker = make(z=2.4, market_open=False)
    result = invoke(config, "run", "--once")
    assert result.exit_code == 0
    assert "market is closed" in result.stdout
    assert broker.submitted == []


def test_init_writes_a_config(tmp_path):
    target = tmp_path / "generated.toml"
    result = runner.invoke(cli.app, ["init", "--path", str(target)])
    assert result.exit_code == 0 and target.exists()
    assert "pair_zscore" in target.read_text()
    # A second write without --force must not clobber it.
    assert runner.invoke(cli.app, ["init", "--path", str(target)]).exit_code == 1


def test_list_shows_planned_brokers_as_planned():
    result = runner.invoke(cli.app, ["list"])
    assert "alpaca" in result.stdout and "planned" in result.stdout


def test_unknown_broker_fails_with_a_clear_message(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[broker]\nname = "etrade"\n')
    result = runner.invoke(cli.app, ["--config", str(config), "status"])
    assert result.exit_code == 1
    assert "unknown broker" in result.stdout


def test_planned_broker_explains_itself(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[broker]\nname = "robinhood"\n')
    result = runner.invoke(cli.app, ["--config", str(config), "status"])
    assert result.exit_code == 1
    assert "not implemented yet" in result.stdout


# -- backtest -----------------------------------------------------------


@pytest.fixture
def backtest_project(tmp_path, monkeypatch):
    """A config plus a fake broker holding a long, tradeable price history."""
    from conftest import FakeBroker
    from test_backtest import mean_reverting_pair

    config = tmp_path / "config.toml"
    config.write_text(
        f"""
[broker]
name = "fake"

[storage]
path = "{tmp_path / 'test.db'}"

[logging]
level = "WARNING"
file = ""

[strategy]
name = "pair_zscore"

[strategy.params]
lookback = {LOOKBACK}
entry_z = 2.0
exit_z = 0.5
stop_z = 3.5
leg_weight = 0.25
"""
    )
    broker = FakeBroker(bars=mean_reverting_pair())
    monkeypatch.setattr(cli, "build_broker", lambda _cfg: broker)
    return config, broker


def test_backtest_reports_the_round_trip(backtest_project):
    config, _ = backtest_project
    result = invoke(config, "backtest", "--slippage-bps", "0")
    assert result.exit_code == 0
    assert "total return" in result.stdout
    assert "round trips" in result.stdout
    assert "short" in result.stdout


def test_backtest_never_submits_an_order(backtest_project):
    config, broker = backtest_project
    invoke(config, "backtest")
    assert broker.submitted == []


def test_backtest_param_override_changes_the_result(backtest_project):
    config, _ = backtest_project
    tradeable = invoke(config, "backtest", "--slippage-bps", "0")
    assert "no round trips" not in tradeable.stdout
    # An entry threshold nothing can reach must produce no trades.
    quiet = invoke(config, "backtest", "-p", "entry_z=9.0", "-p", "stop_z=99.0")
    assert quiet.exit_code == 0
    assert "no round trips" in quiet.stdout


def test_backtest_writes_csv_exports(backtest_project, tmp_path):
    config, _ = backtest_project
    out = tmp_path / "export"
    result = invoke(config, "backtest", "--csv", str(out), "--no-trades")
    assert result.exit_code == 0
    equity = (out / "equity.csv").read_text().splitlines()
    trades = (out / "trades.csv").read_text().splitlines()
    signals = (out / "signals.csv").read_text().splitlines()
    assert equity[0] == "timestamp,equity" and len(equity) > 2
    assert trades[0].startswith("entry_at,exit_at,side")
    assert len(trades) == 2  # header plus the one round trip
    assert signals[0] == "timestamp,action,z,reason" and len(signals) > 2


def test_backtest_rejects_a_bad_fill_mode(backtest_project):
    config, _ = backtest_project
    result = invoke(config, "backtest", "--fill", "magic")
    assert result.exit_code == 1
    assert "next_open" in result.stdout


def test_backtest_rejects_a_malformed_param(backtest_project):
    config, _ = backtest_project
    result = invoke(config, "backtest", "-p", "entry_z")
    assert result.exit_code == 1
    assert "KEY=VALUE" in result.stdout


def test_backtest_rejects_a_bad_date(backtest_project):
    config, _ = backtest_project
    result = invoke(config, "backtest", "--start", "last tuesday")
    assert result.exit_code == 1
    assert "YYYY-MM-DD" in result.stdout


def test_backtest_explains_when_history_is_too_short(tmp_path, monkeypatch):
    from conftest import FakeBroker, bars_from_prices, prices_from_spreads

    config = tmp_path / "config.toml"
    config.write_text(
        f'[broker]\nname="fake"\n[storage]\npath="{tmp_path}/t.db"\n'
        '[logging]\nlevel="WARNING"\nfile=""\n'
        "[strategy]\nname=\"pair_zscore\"\n[strategy.params]\nlookback=60\n"
    )
    closes_a, closes_b = prices_from_spreads([0.01, -0.01] * 5)
    broker = FakeBroker(
        bars={"GLD": bars_from_prices(closes_a), "GDX": bars_from_prices(closes_b)}
    )
    monkeypatch.setattr(cli, "build_broker", lambda _cfg: broker)
    result = runner.invoke(cli.app, ["--config", str(config), "backtest"])
    assert result.exit_code == 1
    assert "never had enough history" in result.stdout
