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
