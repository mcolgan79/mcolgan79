"""The Alpaca adapter's own logic, with the SDK client stubbed out.

No network: the clients are injected directly, so these tests cover the parts
we wrote (sign normalization, timeframe mapping, URL handling, error surfacing)
rather than the SDK's.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from autotrader.brokers.alpaca import AlpacaBroker
from autotrader.brokers.base import BrokerError


def broker(**kwargs) -> AlpacaBroker:
    return AlpacaBroker("key", "secret", **kwargs)


class StubPosition:
    def __init__(self, symbol, qty, side, avg="100", value="1000"):
        self.symbol = symbol
        self.qty = qty
        self.side = side
        self.avg_entry_price = avg
        self.market_value = value


class StubTrading:
    def __init__(self, positions=None, asset=None, raises=None):
        self._positions = positions or []
        self._asset = asset
        self._raises = raises

    def get_all_positions(self):
        if self._raises:
            raise self._raises
        return self._positions

    def get_asset(self, symbol):
        if self._raises:
            raise self._raises
        return self._asset


class StubAsset:
    def __init__(self, shortable):
        self.shortable = shortable


def test_a_pasted_endpoint_with_the_version_suffix_is_normalized():
    """Alpaca's dashboard shows .../v2, but the SDK appends its own version."""
    assert (
        broker(url_override="https://paper-api.alpaca.markets/v2")._url_override
        == "https://paper-api.alpaca.markets"
    )


def test_short_positions_come_back_with_a_negative_quantity():
    b = broker()
    b._trading = StubTrading([StubPosition("GDX", "-166", "PositionSide.SHORT")])
    assert b.get_positions()["GDX"].qty == -166


def test_a_short_reported_with_a_positive_quantity_is_corrected():
    """Defensive: the sign is what every downstream calculation keys off."""
    b = broker()
    b._trading = StubTrading([StubPosition("GDX", "166", "PositionSide.SHORT")])
    assert b.get_positions()["GDX"].qty == -166


def test_long_positions_keep_their_sign():
    b = broker()
    b._trading = StubTrading([StubPosition("GLD", "33", "PositionSide.LONG")])
    assert b.get_positions()["GLD"].qty == 33


def test_shortability_reports_the_asset_flag():
    b = broker()
    b._trading = StubTrading(asset=StubAsset(True))
    assert b.is_shortable("GDX") is True
    b._trading = StubTrading(asset=StubAsset(False))
    assert b.is_shortable("GDX") is False


def test_a_failed_shortability_lookup_raises_rather_than_claiming_yes():
    """A diagnostic that reports a check it never ran as passing is worse than
    one that reports nothing."""
    b = broker()
    b._trading = StubTrading(raises=RuntimeError("network down"))
    with pytest.raises(BrokerError, match="could not check whether GDX"):
        b.is_shortable("GDX")


def test_position_fetch_failures_are_wrapped_in_a_broker_error():
    b = broker()
    b._trading = StubTrading(raises=RuntimeError("boom"))
    with pytest.raises(BrokerError, match="could not fetch Alpaca positions"):
        b.get_positions()


@pytest.mark.parametrize(
    "given, expected", [("1Day", "1Day"), ("15Min", "15Min"), ("1Hour", "1Hour"), ("day", "1Day")]
)
def test_timeframes_map_onto_the_sdk(given, expected):
    assert AlpacaBroker.parse_timeframe(given)[0].value == expected


def test_an_unknown_timeframe_is_a_clear_error():
    with pytest.raises(BrokerError, match="unsupported timeframe"):
        AlpacaBroker.parse_timeframe("fortnightly")


@pytest.mark.parametrize(
    "amount, unit, limit",
    [(1, "day", 750), (1, "hour", 120), (15, "minute", 96)],
)
def test_history_windows_stretch_past_the_raw_bar_count(amount, unit, limit):
    """Sessions are 6.5h and there are 252 a year, so wall-clock span must be
    generously larger than the number of bars requested."""
    window = AlpacaBroker.history_window(amount, unit, limit)
    assert window > timedelta(days=0)
    if unit == "day":
        assert window.days > limit  # weekends and holidays
