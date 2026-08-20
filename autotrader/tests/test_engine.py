"""Order planning, guardrails, and execution flow."""

from __future__ import annotations


from autotrader.config import Config
from autotrader.engine import Engine, plan_orders
from autotrader.models import Action, OrderSide
from autotrader.storage import Store
from autotrader.strategies.pair_zscore import PairZScore
from conftest import position, spreads_for_z

LOOKBACK = 20
PRICES = {"GLD": 300.0, "GDX": 60.0}
EQUITY = 100_000.0


def strategy(**overrides) -> PairZScore:
    params = dict(lookback=LOOKBACK, entry_z=2.0, exit_z=0.5, stop_z=3.5, leg_weight=0.10)
    params.update(overrides)
    return PairZScore(**params)


def config(**engine_overrides) -> Config:
    cfg = Config()
    for key, value in engine_overrides.items():
        if hasattr(cfg.engine.guardrails, key):
            setattr(cfg.engine.guardrails, key, value)
        else:
            setattr(cfg.engine, key, value)
    return cfg


# -- plan_orders --------------------------------------------------------


def test_opening_a_pair_floors_both_legs_to_whole_shares():
    orders = plan_orders({"GLD": -0.10, "GDX": 0.10}, {}, PRICES, EQUITY)
    by_symbol = {o.symbol: o for o in orders}
    # 10% of 100k is 10,000: 33.3 GLD -> 33, 166.6 GDX -> 166.
    assert by_symbol["GLD"].qty == 33 and by_symbol["GLD"].side is OrderSide.SELL
    assert by_symbol["GDX"].qty == 166 and by_symbol["GDX"].side is OrderSide.BUY


def test_flooring_never_overshoots_the_requested_weight():
    orders = plan_orders({"GLD": 0.10}, {}, PRICES, EQUITY)
    notional = orders[0].qty * PRICES["GLD"]
    assert notional <= 0.10 * EQUITY


def test_flat_targets_close_both_legs():
    held = {"GLD": position("GLD", -33), "GDX": position("GDX", 166)}
    orders = plan_orders({"GLD": 0.0, "GDX": 0.0}, held, PRICES, EQUITY)
    by_symbol = {o.symbol: o for o in orders}
    assert by_symbol["GLD"].side is OrderSide.BUY and by_symbol["GLD"].qty == 33
    assert by_symbol["GDX"].side is OrderSide.SELL and by_symbol["GDX"].qty == 166


def test_a_sign_flip_is_split_into_close_then_open():
    held = {"GLD": position("GLD", 40)}
    orders = plan_orders({"GLD": -0.10}, held, PRICES, EQUITY)
    assert [(o.side, o.qty) for o in orders] == [
        (OrderSide.SELL, 40),  # close the long first
        (OrderSide.SELL, 33),  # then open the short
    ]
    assert "close long" in orders[0].intent


def test_closes_are_sequenced_before_opens_across_symbols():
    held = {"GDX": position("GDX", 200)}
    orders = plan_orders({"GLD": 0.10, "GDX": 0.05}, held, PRICES, EQUITY)
    assert orders[0].symbol == "GDX"  # reducing GDX frees buying power
    assert orders[0].side is OrderSide.SELL
    assert orders[1].symbol == "GLD"


def test_matching_position_produces_no_orders():
    held = {"GLD": position("GLD", -33), "GDX": position("GDX", 166)}
    assert plan_orders({"GLD": -0.10, "GDX": 0.10}, held, PRICES, EQUITY) == []


def test_sub_share_targets_are_dropped_rather_than_rounded_up():
    orders = plan_orders({"GLD": 0.001}, {}, PRICES, EQUITY)  # $100 of a $300 share
    assert orders == []


def test_missing_price_skips_the_leg_without_crashing():
    orders = plan_orders({"GLD": 0.10, "GDX": 0.10}, {}, {"GLD": 300.0}, EQUITY)
    assert [o.symbol for o in orders] == ["GLD"]


# -- Engine -------------------------------------------------------------


def build_engine(broker, tmp_path, cfg=None, strat=None):
    store = Store(tmp_path / "test.db")
    return Engine(cfg or config(), broker, strat or strategy(), store), store


def test_run_once_enters_and_submits_both_legs(fake_broker_factory, tmp_path):
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK))
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert report.decision.action is Action.ENTER
    assert report.executed
    assert {o.symbol for o in broker.submitted} == {"GLD", "GDX"}
    assert all(r.ok for r in report.results)
    store.close()


def test_dry_run_submits_nothing_but_still_plans(fake_broker_factory, tmp_path):
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK))
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once(dry_run=True)
    assert report.orders and not report.executed
    assert broker.submitted == []
    store.close()


def test_closed_market_blocks_trading_but_records_the_signal(
    fake_broker_factory, tmp_path
):
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK), market_open=False)
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert broker.submitted == []
    assert "market is closed" in report.skipped_reason
    assert report.decision.action is Action.ENTER  # the signal is still logged
    assert store.recent_signals(limit=1)[0]["action"] == "enter"
    store.close()


def test_ignore_market_hours_lets_orders_through(fake_broker_factory, tmp_path):
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK), market_open=False)
    engine, store = build_engine(broker, tmp_path)
    engine.run_once(ignore_market_hours=True)
    assert len(broker.submitted) == 2
    store.close()


def test_holiday_blocks_trading(fake_broker_factory, tmp_path):
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK), trading_day=False)
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert broker.submitted == []
    assert "trading day" in report.skipped_reason
    store.close()


def test_no_pyramiding_guardrail_blocks_adding_to_an_open_leg(
    fake_broker_factory, tmp_path
):
    """The strategy would not ask for this, but the engine refuses it anyway."""
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK))
    engine, store = build_engine(broker, tmp_path)
    engine.strategy = strategy()
    report = engine.run_once(dry_run=True)
    # Force the ENTER path against an already-open leg.
    positions = {"GLD": position("GLD", -33)}
    blocked = engine._blocking_guardrail(
        broker.get_market_status(), report.decision, positions
    )
    assert blocked and "max_open_strategies" in blocked
    store.close()


def test_insufficient_history_skips_before_touching_the_broker(
    fake_broker_factory, tmp_path
):
    broker = fake_broker_factory(spreads_for_z(2.4, 6))
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert report.decision.action is Action.SKIP
    assert broker.submitted == []
    store.close()


def test_a_rejected_leg_aborts_the_remaining_orders(fake_broker_factory, tmp_path):
    """If the first leg fails we must not open the second one unhedged."""
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK), fail_symbols={"GLD"})
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert report.had_errors
    assert [o.symbol for o in broker.submitted] == ["GLD"]
    store.close()


def test_maintaining_an_open_pair_places_no_new_orders(fake_broker_factory, tmp_path):
    held = {"GLD": position("GLD", -33, 300.0), "GDX": position("GDX", 166, 60.0)}
    broker = fake_broker_factory(spreads_for_z(1.8, LOOKBACK), positions=held)
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert report.decision.action is Action.MAINTAIN
    assert broker.submitted == []
    store.close()


def test_exit_signal_closes_the_pair(fake_broker_factory, tmp_path):
    held = {"GLD": position("GLD", -33, 300.0), "GDX": position("GDX", 166, 60.0)}
    broker = fake_broker_factory(spreads_for_z(0.2, LOOKBACK), positions=held)
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert report.decision.action is Action.EXIT
    assert {(o.symbol, o.side) for o in broker.submitted} == {
        ("GLD", OrderSide.BUY),
        ("GDX", OrderSide.SELL),
    }
    store.close()


def test_flatten_closes_positions_regardless_of_signal(fake_broker_factory, tmp_path):
    held = {"GLD": position("GLD", -33, 300.0), "GDX": position("GDX", 166, 60.0)}
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK), positions=held)
    engine, store = build_engine(broker, tmp_path)
    report = engine.flatten()
    assert report.executed
    assert {o.symbol for o in broker.submitted} == {"GLD", "GDX"}
    store.close()


def test_flatten_dry_run_submits_nothing(fake_broker_factory, tmp_path):
    held = {"GLD": position("GLD", -33, 300.0), "GDX": position("GDX", 166, 60.0)}
    broker = fake_broker_factory(spreads_for_z(2.4, LOOKBACK), positions=held)
    engine, store = build_engine(broker, tmp_path)
    report = engine.flatten(dry_run=True)
    assert report.orders and broker.submitted == []
    store.close()


def test_maintain_does_not_top_up_a_drifting_position(fake_broker_factory, tmp_path):
    """Holding means holding -- not re-sizing to the target weight each pass."""
    held = {"GLD": position("GLD", -5, 60.0), "GDX": position("GDX", 10, 60.0)}
    broker = fake_broker_factory(spreads_for_z(1.8, LOOKBACK), positions=held)
    engine, store = build_engine(broker, tmp_path)
    report = engine.run_once()
    assert report.decision.action is Action.MAINTAIN
    assert broker.submitted == []
    assert "no rebalancing" in report.skipped_reason
    store.close()


def test_a_rebalancing_strategy_does_top_up(fake_broker_factory, tmp_path):
    held = {"GLD": position("GLD", -5, 60.0), "GDX": position("GDX", 10, 60.0)}
    broker = fake_broker_factory(spreads_for_z(1.8, LOOKBACK), positions=held)
    strat = strategy()
    strat.rebalance_on_maintain = True
    engine, store = build_engine(broker, tmp_path, strat=strat)
    report = engine.run_once()
    assert report.decision.action is Action.MAINTAIN
    assert len(broker.submitted) == 2
    store.close()
