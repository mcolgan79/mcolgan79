"""Shared test fixtures: a deterministic in-memory broker and spread builders."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from autotrader.brokers.base import Broker
from autotrader.models import (
    Account,
    Bar,
    MarketSnapshot,
    MarketStatus,
    OrderResult,
    Position,
    StrategyContext,
)

BASE_PRICE_B = 60.0


def bars_from_prices(prices: list[float], start: datetime | None = None) -> list[Bar]:
    origin = start or datetime(2026, 1, 2, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=origin + timedelta(days=i),
            open=p,
            high=p,
            low=p,
            close=p,
            volume=1_000_000,
        )
        for i, p in enumerate(prices)
    ]


def prices_from_spreads(spreads: list[float]) -> tuple[list[float], list[float]]:
    """Turn a spread series into two price series with exactly that log ratio."""
    closes_b = [BASE_PRICE_B] * len(spreads)
    closes_a = [BASE_PRICE_B * math.exp(s) for s in spreads]
    return closes_a, closes_b


def spreads_for_z(target_z: float, n: int, jitter: float = 0.01) -> list[float]:
    """A spread series whose final z-score over an n-bar window is ~target_z.

    The first n-1 values alternate around zero to give the window a stable
    standard deviation; the last value is solved for by bisection, since z is
    monotonic in it.
    """
    base = [jitter if i % 2 else -jitter for i in range(n - 1)]

    def z_of(last: float) -> float:
        window = base + [last]
        mean = sum(window) / n
        var = sum((x - mean) ** 2 for x in window) / (n - 1)
        return (last - mean) / math.sqrt(var)

    lo, hi = -5.0, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if z_of(mid) < target_z:
            lo = mid
        else:
            hi = mid
    return base + [(lo + hi) / 2]


def make_context(
    spreads: list[float],
    positions: dict[str, Position] | None = None,
    equity: float = 100_000.0,
    symbol_a: str = "GLD",
    symbol_b: str = "GDX",
) -> StrategyContext:
    closes_a, closes_b = prices_from_spreads(spreads)
    snapshot = MarketSnapshot(
        as_of=datetime(2026, 3, 2, tzinfo=timezone.utc),
        bars={symbol_a: bars_from_prices(closes_a), symbol_b: bars_from_prices(closes_b)},
    )
    return StrategyContext(
        account=Account(equity=equity, cash=equity, buying_power=equity * 2),
        positions=positions or {},
        snapshot=snapshot,
    )


def position(symbol: str, qty: float, price: float = 100.0) -> Position:
    return Position(
        symbol=symbol, qty=qty, avg_entry_price=price, market_value=qty * price
    )


class FakeBroker(Broker):
    """An in-memory broker that records orders instead of sending them."""

    name = "fake"
    paper = True

    def __init__(
        self,
        bars: dict[str, list[Bar]] | None = None,
        positions: dict[str, Position] | None = None,
        equity: float = 100_000.0,
        market_open: bool = True,
        trading_day: bool = True,
        fail_symbols: set[str] | None = None,
    ) -> None:
        self._bars = bars or {}
        self._positions = dict(positions or {})
        self._equity = equity
        self._market_open = market_open
        self._trading_day = trading_day
        self._fail_symbols = fail_symbols or set()
        self.submitted: list = []

    def get_account(self) -> Account:
        return Account(
            equity=self._equity, cash=self._equity, buying_power=self._equity * 2
        )

    def get_positions(self) -> dict[str, Position]:
        return dict(self._positions)

    def get_bars(self, symbols, timeframe, limit, start=None, end=None):
        out = {}
        for symbol in symbols:
            series = self._bars.get(symbol, [])
            if start is not None:
                series = [b for b in series if b.timestamp >= start]
            if end is not None:
                series = [b for b in series if b.timestamp <= end]
            out[symbol] = series[-limit:]
        return out

    def get_market_status(self) -> MarketStatus:
        return MarketStatus(
            is_open=self._market_open,
            detail="open" if self._market_open else "closed for the day",
        )

    def is_trading_day(self, day=None) -> bool:
        return self._trading_day

    def submit_order(self, request) -> OrderResult:
        self.submitted.append(request)
        if request.symbol in self._fail_symbols:
            return OrderResult(
                request=request, status="rejected", error="simulated rejection"
            )
        return OrderResult(
            request=request,
            status="filled",
            broker_order_id=f"fake-{len(self.submitted)}",
            filled_qty=request.qty,
            filled_avg_price=100.0,
            submitted_at=datetime(2026, 3, 2, 15, 0, tzinfo=timezone.utc),
        )


@pytest.fixture
def fake_broker_factory():
    def _factory(spreads: list[float], **kwargs) -> FakeBroker:
        closes_a, closes_b = prices_from_spreads(spreads)
        bars = {
            "GLD": bars_from_prices(closes_a),
            "GDX": bars_from_prices(closes_b),
        }
        return FakeBroker(bars=bars, **kwargs)

    return _factory
