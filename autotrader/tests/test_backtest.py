"""Historical replay: accounting, fills, alignment, and statistics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autotrader.backtest import (
    BacktestError,
    Backtester,
    Fill,
    SimPortfolio,
    align_bars,
    max_drawdown,
)
from autotrader.models import (
    Action,
    Bar,
    Decision,
    OrderSide,
    StrategyContext,
)
from autotrader.strategies.base import Strategy
from autotrader.strategies.pair_zscore import PairZScore
from conftest import bars_from_prices, prices_from_spreads, spreads_for_z

ORIGIN = datetime(2026, 1, 2, tzinfo=timezone.utc)


def ohlc_bars(rows: list[tuple[float, float]], start: datetime = ORIGIN) -> list[Bar]:
    """Bars from (open, close) pairs so fill mode is observable."""
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=o,
            high=max(o, c),
            low=min(o, c),
            close=c,
            volume=1_000,
        )
        for i, (o, c) in enumerate(rows)
    ]


class ScriptedStrategy(Strategy):
    """Returns preset decisions so the replay machinery can be tested alone."""

    name = "scripted"

    def __init__(self, script: dict[int, tuple[Action, dict]], symbols=("AAA",)):
        super().__init__()
        self.script = script
        self._symbols = list(symbols)
        self.seen_bar_counts: list[int] = []
        self.seen_last_stamps: list[datetime] = []
        self._calls = 0

    def symbols(self):
        return list(self._symbols)

    @property
    def required_bars(self) -> int:
        return 1000

    def evaluate(self, ctx: StrategyContext) -> Decision:
        index = self._calls
        self._calls += 1
        series = ctx.snapshot.bars[self._symbols[0]]
        self.seen_bar_counts.append(len(series))
        self.seen_last_stamps.append(series[-1].timestamp)
        # Unscripted bars are a no-op: empty targets mean "leave it alone".
        action, targets = self.script.get(index, (Action.NONE, {}))
        return Decision(
            strategy=self.name, action=action, targets=targets, reason="scripted", metrics={"z": 0.0}
        )


# -- portfolio accounting ----------------------------------------------


def test_buying_moves_cash_into_position_value():
    portfolio = SimPortfolio(10_000)
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.BUY, 10, 100.0, 0.0))
    assert portfolio.cash == 9_000
    assert portfolio.equity({"AAA": 100.0}) == 10_000


def test_a_short_sale_is_equity_neutral_at_the_fill():
    portfolio = SimPortfolio(10_000)
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.SELL, 10, 100.0, 0.0))
    assert portfolio.cash == 11_000
    assert portfolio.qty["AAA"] == -10
    assert portfolio.equity({"AAA": 100.0}) == 10_000


def test_a_short_profits_when_the_price_falls():
    portfolio = SimPortfolio(10_000)
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.SELL, 10, 100.0, 0.0))
    assert portfolio.equity({"AAA": 90.0}) == 10_100


def test_commission_comes_out_of_cash():
    portfolio = SimPortfolio(10_000)
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.BUY, 10, 100.0, 5.0))
    assert portfolio.cash == 8_995
    assert portfolio.equity({"AAA": 100.0}) == 9_995


def test_closing_a_position_leaves_the_portfolio_flat():
    portfolio = SimPortfolio(10_000)
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.BUY, 10, 100.0, 0.0))
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.SELL, 10, 110.0, 0.0))
    assert portfolio.is_flat
    assert portfolio.cash == 10_100


def test_averaging_into_a_position_blends_the_cost_basis():
    portfolio = SimPortfolio(10_000)
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.BUY, 10, 100.0, 0.0))
    portfolio.apply(Fill(ORIGIN, "AAA", OrderSide.BUY, 10, 120.0, 0.0))
    assert portfolio.cost_basis["AAA"] == pytest.approx(110.0)


# -- alignment ----------------------------------------------------------


def test_alignment_keeps_only_shared_timestamps():
    a = bars_from_prices([1, 2, 3, 4, 5])
    b = bars_from_prices([1, 2, 3])
    stamps, aligned = align_bars({"A": a, "B": b})
    assert len(stamps) == 3
    assert [bar.timestamp for bar in aligned["A"]] == stamps
    assert [bar.timestamp for bar in aligned["B"]] == stamps


def test_alignment_drops_duplicate_timestamps():
    """A repeated bar would otherwise shift one symbol against the other."""
    series = bars_from_prices([1, 2, 3])
    stamps, aligned = align_bars({"A": series + [series[1]], "B": series})
    assert len(stamps) == 3
    assert len(aligned["A"]) == 3


def test_no_overlap_is_a_clear_error():
    a = bars_from_prices([1, 2, 3], start=ORIGIN)
    b = bars_from_prices([1, 2, 3], start=ORIGIN + timedelta(days=100))
    with pytest.raises(BacktestError, match="no common bar timestamps"):
        align_bars({"A": a, "B": b})


# -- replay mechanics ---------------------------------------------------


def test_the_strategy_only_ever_sees_bars_up_to_the_current_one():
    """The whole backtest is worthless if this leaks."""
    bars = {"AAA": ohlc_bars([(10, 10)] * 6)}
    strategy = ScriptedStrategy({})
    result = Backtester(strategy, bars, starting_equity=1_000).run()
    assert strategy.seen_bar_counts == [1, 2, 3, 4, 5, 6]
    assert strategy.seen_last_stamps == [b.timestamp for b in bars["AAA"]]
    assert len(result.equity_curve) == 6


def test_next_open_fill_uses_the_following_bar_open():
    bars = {"AAA": ohlc_bars([(10, 10), (20, 30), (30, 30)])}
    strategy = ScriptedStrategy({0: (Action.ENTER, {"AAA": 1.0})})
    result = Backtester(
        strategy, bars, starting_equity=1_000, slippage_bps=0, fill="next_open"
    ).run()
    assert result.fills[0].price == 20.0  # bar 1's open, not bar 0's close


def test_close_fill_uses_the_signal_bar_close():
    bars = {"AAA": ohlc_bars([(10, 10), (20, 30), (30, 30)])}
    strategy = ScriptedStrategy({0: (Action.ENTER, {"AAA": 1.0})})
    result = Backtester(
        strategy, bars, starting_equity=1_000, slippage_bps=0, fill="close"
    ).run()
    assert result.fills[0].price == 10.0


def test_slippage_pushes_the_fill_against_us_on_both_sides():
    bars = {"AAA": ohlc_bars([(100, 100)] * 4)}
    strategy = ScriptedStrategy(
        {0: (Action.ENTER, {"AAA": 1.0}), 1: (Action.EXIT, {"AAA": 0.0})}
    )
    result = Backtester(strategy, bars, starting_equity=1_000, slippage_bps=10).run()
    buy, sell = result.fills[0], result.fills[1]
    assert buy.price == pytest.approx(100.1)  # paid up
    assert sell.price == pytest.approx(99.9)  # sold down


def test_a_signal_on_the_final_bar_cannot_fill_under_next_open():
    bars = {"AAA": ohlc_bars([(10, 10), (10, 10)])}
    strategy = ScriptedStrategy({1: (Action.ENTER, {"AAA": 1.0})})
    result = Backtester(strategy, bars, starting_equity=1_000).run()
    assert result.fills == []


def test_a_round_trip_is_recorded_with_its_pnl():
    bars = {"AAA": ohlc_bars([(10, 10), (10, 10), (12, 12), (12, 12)])}
    strategy = ScriptedStrategy(
        {0: (Action.ENTER, {"AAA": 1.0}), 2: (Action.EXIT, {"AAA": 0.0})}
    )
    result = Backtester(strategy, bars, starting_equity=1_000, slippage_bps=0).run()
    assert len(result.trades) == 1
    trade = result.trades[0]
    # 100 shares bought at 10, sold at 12.
    assert trade.pnl == pytest.approx(200.0)
    assert trade.won and trade.exit_action == "exit"
    assert result.final_equity == pytest.approx(1_200.0)


def test_a_losing_round_trip_is_marked_as_such():
    bars = {"AAA": ohlc_bars([(10, 10), (10, 10), (8, 8), (8, 8)])}
    strategy = ScriptedStrategy(
        {0: (Action.ENTER, {"AAA": 1.0}), 2: (Action.STOP, {"AAA": 0.0})}
    )
    result = Backtester(strategy, bars, starting_equity=1_000, slippage_bps=0).run()
    trade = result.trades[0]
    assert not trade.won and trade.exit_action == "stop"
    assert trade.pnl == pytest.approx(-200.0)


def test_maintain_does_not_resize_during_replay():
    """Same rule as live: holding is holding."""
    bars = {"AAA": ohlc_bars([(10, 10), (10, 10), (5, 5), (5, 5), (5, 5)])}
    strategy = ScriptedStrategy(
        {
            0: (Action.ENTER, {"AAA": 1.0}),
            2: (Action.MAINTAIN, {"AAA": 1.0}),  # price halved: a resize would buy more
            3: (Action.MAINTAIN, {"AAA": 1.0}),
        }
    )
    result = Backtester(strategy, bars, starting_equity=1_000, slippage_bps=0).run()
    assert len(result.fills) == 1


def test_skipped_warmup_bars_are_counted_and_excluded():
    bars = {"AAA": ohlc_bars([(10, 10)] * 5)}
    strategy = ScriptedStrategy({0: (Action.SKIP, {}), 1: (Action.SKIP, {})})
    result = Backtester(strategy, bars, starting_equity=1_000).run()
    assert result.warmup_bars == 2
    assert len(result.equity_curve) == 3


def test_a_strategy_that_never_warms_up_fails_loudly():
    bars = {"AAA": ohlc_bars([(10, 10)] * 3)}
    strategy = ScriptedStrategy({i: (Action.SKIP, {}) for i in range(3)})
    with pytest.raises(BacktestError, match="never had enough history"):
        Backtester(strategy, bars, starting_equity=1_000).run()


# -- statistics ---------------------------------------------------------


def test_max_drawdown_finds_the_deepest_trough():
    curve = [(ORIGIN + timedelta(days=i), v) for i, v in enumerate([100, 120, 60, 90, 130])]
    depth, at = max_drawdown(curve)
    assert depth == pytest.approx(-0.5)  # 120 -> 60
    assert at == curve[2][0]


def test_stats_summarize_a_winning_and_a_losing_trip():
    bars = {
        "AAA": ohlc_bars([(10, 10), (10, 10), (12, 12), (12, 12), (12, 12), (6, 6), (6, 6)])
    }
    strategy = ScriptedStrategy(
        {
            0: (Action.ENTER, {"AAA": 1.0}),
            2: (Action.EXIT, {"AAA": 0.0}),
            3: (Action.ENTER, {"AAA": 1.0}),
            5: (Action.EXIT, {"AAA": 0.0}),
        }
    )
    result = Backtester(strategy, bars, starting_equity=1_000, slippage_bps=0).run()
    stats = result.stats()
    assert stats["trades"] == 2
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["max_drawdown"] < 0
    assert stats["total_return"] == pytest.approx(stats["final_equity"] / 1_000 - 1)


# -- the real strategy end to end ---------------------------------------


def mean_reverting_pair(lookback: int = 20) -> dict[str, list[Bar]]:
    """A quiet stretch, one dislocation wide enough to trade, then reversion."""
    jitter = [0.01 if i % 2 else -0.01 for i in range(40)]
    shock = spreads_for_z(2.6, lookback)[-1]
    path = jitter + [shock, shock] + [0.01 if i % 2 else -0.01 for i in range(30)]
    closes_a, closes_b = prices_from_spreads(path)
    return {"GLD": bars_from_prices(closes_a), "GDX": bars_from_prices(closes_b)}


def test_the_pair_strategy_trades_a_dislocation_and_profits_from_reversion():
    strategy = PairZScore(lookback=20, entry_z=2.0, exit_z=0.5, stop_z=3.5, leg_weight=0.25)
    result = Backtester(
        strategy, mean_reverting_pair(), starting_equity=100_000, slippage_bps=0
    ).run()
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "short_spread"  # GLD was the rich leg
    assert trade.exit_action == "exit"
    assert trade.pnl > 0
    assert result.stats()["win_rate"] == 1.0


def test_the_pair_strategy_stands_aside_when_nothing_dislocates():
    quiet = [0.01 if i % 2 else -0.01 for i in range(80)]
    closes_a, closes_b = prices_from_spreads(quiet)
    bars = {"GLD": bars_from_prices(closes_a), "GDX": bars_from_prices(closes_b)}
    strategy = PairZScore(lookback=20)
    result = Backtester(strategy, bars, starting_equity=100_000).run()
    assert result.trades == []
    assert result.final_equity == 100_000


def test_the_benchmark_curve_tracks_buy_and_hold():
    strategy = PairZScore(lookback=20)
    result = Backtester(
        strategy, mean_reverting_pair(), starting_equity=100_000, benchmark="GDX"
    ).run()
    stats = result.stats()
    assert result.benchmark_symbol == "GDX"
    # GDX is flat at 60 throughout, so buying and holding it returns nothing.
    assert stats["benchmark_return"] == pytest.approx(0.0, abs=1e-9)
