"""Signal logic for the GLD/GDX pair strategy."""

from __future__ import annotations

import pytest

from autotrader.models import Action
from autotrader.strategies.base import StrategyError
from autotrader.strategies.pair_zscore import PairZScore
from conftest import make_context, position, spreads_for_z

LOOKBACK = 20


def strategy(**overrides) -> PairZScore:
    params = dict(
        symbol_a="GLD",
        symbol_b="GDX",
        lookback=LOOKBACK,
        entry_z=2.0,
        exit_z=0.5,
        stop_z=3.5,
        leg_weight=0.10,
    )
    params.update(overrides)
    return PairZScore(**params)


def test_zscore_matches_the_constructed_series():
    strat = strategy()
    ctx = make_context(spreads_for_z(2.4, LOOKBACK))
    z, _, _ = strat.zscore(strat.spread_series(ctx))
    assert z == pytest.approx(2.4, abs=1e-6)


def test_high_z_while_flat_shorts_the_rich_leg():
    strat = strategy()
    decision = strat.evaluate(make_context(spreads_for_z(2.4, LOOKBACK)))
    assert decision.action is Action.ENTER
    assert decision.targets == {"GLD": -0.10, "GDX": 0.10}


def test_low_z_while_flat_buys_the_cheap_leg():
    strat = strategy()
    decision = strat.evaluate(make_context(spreads_for_z(-2.4, LOOKBACK)))
    assert decision.action is Action.ENTER
    assert decision.targets == {"GLD": 0.10, "GDX": -0.10}


def test_inside_the_entry_band_does_nothing():
    strat = strategy()
    decision = strat.evaluate(make_context(spreads_for_z(1.2, LOOKBACK)))
    assert decision.action is Action.NONE
    assert decision.wants_flat


def test_beyond_the_stop_band_refuses_a_new_entry():
    """A z past the stop band means the relationship may have broken."""
    strat = strategy()
    decision = strat.evaluate(make_context(spreads_for_z(4.0, LOOKBACK)))
    assert decision.action is Action.NONE
    assert "stop band" in decision.reason


def test_open_short_spread_holds_while_z_stays_wide():
    strat = strategy()
    held = {"GLD": position("GLD", -33), "GDX": position("GDX", 166)}
    decision = strat.evaluate(make_context(spreads_for_z(1.8, LOOKBACK), held))
    assert decision.action is Action.MAINTAIN
    assert decision.targets == {"GLD": -0.10, "GDX": 0.10}


def test_short_spread_exits_inside_the_exit_band():
    strat = strategy()
    held = {"GLD": position("GLD", -33), "GDX": position("GDX", 166)}
    decision = strat.evaluate(make_context(spreads_for_z(0.3, LOOKBACK), held))
    assert decision.action is Action.EXIT
    assert decision.wants_flat


def test_short_spread_exits_after_overshooting_through_zero():
    """A gap straight past the exit band must still close, not flip."""
    strat = strategy()
    held = {"GLD": position("GLD", -33), "GDX": position("GDX", 166)}
    decision = strat.evaluate(make_context(spreads_for_z(-1.9, LOOKBACK), held))
    assert decision.action is Action.EXIT
    assert decision.wants_flat


def test_short_spread_stops_out_when_z_widens_past_the_stop():
    strat = strategy()
    held = {"GLD": position("GLD", -33), "GDX": position("GDX", 166)}
    decision = strat.evaluate(make_context(spreads_for_z(3.6, LOOKBACK), held))
    assert decision.action is Action.STOP
    assert decision.wants_flat


def test_long_spread_stops_out_on_the_negative_side():
    strat = strategy()
    held = {"GLD": position("GLD", 33), "GDX": position("GDX", -166)}
    decision = strat.evaluate(make_context(spreads_for_z(-3.6, LOOKBACK), held))
    assert decision.action is Action.STOP


def test_long_spread_maintains_while_still_wide():
    strat = strategy()
    held = {"GLD": position("GLD", 33), "GDX": position("GDX", -166)}
    decision = strat.evaluate(make_context(spreads_for_z(-1.7, LOOKBACK), held))
    assert decision.action is Action.MAINTAIN


def test_half_filled_pair_is_flattened_to_resync():
    strat = strategy()
    held = {"GLD": position("GLD", -33)}  # GDX leg never filled
    decision = strat.evaluate(make_context(spreads_for_z(2.4, LOOKBACK), held))
    assert decision.action is Action.EXIT
    assert "inconsistent" in decision.reason


def test_both_legs_the_same_direction_is_also_inconsistent():
    strat = strategy()
    held = {"GLD": position("GLD", 33), "GDX": position("GDX", 166)}
    decision = strat.evaluate(make_context(spreads_for_z(0.1, LOOKBACK), held))
    assert decision.action is Action.EXIT


def test_insufficient_history_skips_instead_of_guessing():
    strat = strategy()
    decision = strat.evaluate(make_context(spreads_for_z(2.4, 8)))
    assert decision.action is Action.SKIP
    assert decision.metrics["bars_available"] == 8


def test_misaligned_histories_align_on_the_most_recent_bars():
    """A missing bar on one leg must not shift the pairing by a day."""
    strat = strategy()
    full = spreads_for_z(2.4, LOOKBACK + 5)
    ctx = make_context(full)
    trimmed = dict(ctx.snapshot.bars)
    trimmed["GDX"] = trimmed["GDX"][3:]  # leg B is missing its three oldest bars
    object.__setattr__(ctx.snapshot, "bars", trimmed)

    spreads = strat.spread_series(ctx)

    assert len(spreads) == LOOKBACK + 2  # the shorter leg governs
    # Right-anchored: every value still equals the correct same-day spread.
    assert spreads == pytest.approx(full[-(LOOKBACK + 2) :], abs=1e-12)


@pytest.mark.parametrize(
    "params, message",
    [
        ({"symbol_b": "GLD"}, "must differ"),
        ({"lookback": 3}, "at least 5"),
        ({"exit_z": 2.5}, "exit_z < entry_z"),
        ({"stop_z": 1.0}, "greater than entry_z"),
        ({"leg_weight": 0}, "leg_weight"),
        ({"leg_weight": 1.5}, "leg_weight"),
    ],
)
def test_bad_parameters_are_rejected_at_construction(params, message):
    with pytest.raises(StrategyError, match=message):
        strategy(**params)
