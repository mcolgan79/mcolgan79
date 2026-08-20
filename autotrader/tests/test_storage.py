"""Persistence of runs, signals, orders, and position snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from autotrader.models import (
    Account,
    Action,
    Decision,
    MarketStatus,
    OrderRequest,
    OrderResult,
    OrderSide,
    RunReport,
)
from autotrader.storage import Store
from conftest import position


def sample_report(executed: bool = True) -> RunReport:
    request = OrderRequest(symbol="GLD", qty=33, side=OrderSide.SELL, intent="open short leg")
    return RunReport(
        started_at=datetime(2026, 3, 2, 15, 0, tzinfo=timezone.utc),
        strategy="pair_zscore",
        decision=Decision(
            strategy="pair_zscore",
            action=Action.ENTER,
            targets={"GLD": -0.1, "GDX": 0.1},
            reason="z=+2.31 >= +2.0",
            metrics={"z": 2.31, "spread": 1.6},
        ),
        market=MarketStatus(is_open=True, detail="open"),
        orders=[request],
        results=(
            [OrderResult(request=request, status="filled", broker_order_id="abc", filled_qty=33)]
            if executed
            else []
        ),
        executed=executed,
        account=Account(equity=100_000, cash=50_000, buying_power=200_000),
        positions={"GLD": position("GLD", -33, 300.0)},
    )


def test_a_run_persists_its_signal_orders_and_positions(tmp_path):
    with Store(tmp_path / "t.db") as store:
        run_id = store.record_run(sample_report(), broker="alpaca", mode="live")
        assert run_id == 1

        signal = store.recent_signals(limit=1)[0]
        assert signal["action"] == "enter"
        assert json.loads(signal["metrics"])["z"] == 2.31
        assert json.loads(signal["targets"]) == {"GLD": -0.1, "GDX": 0.1}

        order = store.recent_orders(limit=1)[0]
        assert (order["symbol"], order["side"], order["qty"]) == ("GLD", "sell", 33)
        assert order["dry_run"] == 0 and order["broker_order_id"] == "abc"

        run = store.recent_runs(limit=1)[0]
        assert run["equity"] == 100_000 and run["market_open"] == 1


def test_dry_run_orders_are_recorded_as_planned_only(tmp_path):
    with Store(tmp_path / "t.db") as store:
        store.record_run(sample_report(executed=False), broker="alpaca", mode="dry-run")
        order = store.recent_orders(limit=1)[0]
        assert order["dry_run"] == 1
        assert order["status"] == "planned"
        assert store.recent_orders(limit=5, include_dry_run=False) == []


def test_metric_series_comes_back_oldest_first(tmp_path):
    with Store(tmp_path / "t.db") as store:
        for z in (1.0, 2.0, 3.0):
            report = sample_report()
            report.decision = Decision(
                strategy="pair_zscore", action=Action.NONE, metrics={"z": z}
            )
            store.record_run(report, broker="alpaca", mode="dry-run")
        series = store.last_metric_series("z", limit=10)
        assert [value for _, value in series] == [1.0, 2.0, 3.0]


def test_the_database_is_created_with_its_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "t.db"
    with Store(path):
        assert path.exists()
