"""Broker- and strategy-agnostic domain types.

Everything the engine passes around is defined here so that a new broker or a
new strategy only has to speak these types, never Alpaca's (or Robinhood's).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Account:
    equity: float
    cash: float
    buying_power: float
    currency: str = "USD"


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float  # signed: negative means short
    avg_entry_price: float
    market_value: float

    @property
    def side(self) -> str:
        if self.qty > 0:
            return "long"
        if self.qty < 0:
            return "short"
        return "flat"


@dataclass(frozen=True)
class MarketStatus:
    is_open: bool
    next_open: datetime | None = None
    next_close: datetime | None = None
    detail: str = ""


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    qty: float
    side: OrderSide
    order_type: str = "market"
    time_in_force: str = "day"
    # Why the engine wants this order, e.g. "close long leg before flipping short".
    intent: str = ""

    def __str__(self) -> str:
        return f"{self.side.value.upper()} {self.qty:g} {self.symbol}"


@dataclass(frozen=True)
class OrderResult:
    request: OrderRequest
    status: str
    broker_order_id: str | None = None
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    submitted_at: datetime | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Action(str, Enum):
    """What a strategy decided on this evaluation."""

    NONE = "none"  # flat, no signal
    ENTER = "enter"  # open a new position
    MAINTAIN = "maintain"  # already positioned, keep holding
    EXIT = "exit"  # target reached, flatten
    STOP = "stop"  # risk limit hit, flatten
    SKIP = "skip"  # could not evaluate (insufficient data, etc.)


@dataclass(frozen=True)
class Decision:
    """A strategy's output: target portfolio weights plus an explanation.

    ``targets`` maps symbol -> signed fraction of account equity. ``+0.1`` means
    "hold a long worth 10% of equity"; ``-0.1`` a short of the same size. Targets
    are absolute, not deltas, so a strategy that wants to be flat returns 0.0
    (or simply omits nothing -- every symbol it trades should appear).
    """

    strategy: str
    action: Action
    targets: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def wants_flat(self) -> bool:
        return all(abs(w) < 1e-9 for w in self.targets.values())


@dataclass(frozen=True)
class MarketSnapshot:
    as_of: datetime
    bars: dict[str, list[Bar]]

    def closes(self, symbol: str) -> list[float]:
        return [b.close for b in self.bars.get(symbol, [])]

    def last_price(self, symbol: str) -> float | None:
        series = self.bars.get(symbol)
        return series[-1].close if series else None


@dataclass(frozen=True)
class StrategyContext:
    account: Account
    positions: dict[str, Position]
    snapshot: MarketSnapshot

    def qty(self, symbol: str) -> float:
        pos = self.positions.get(symbol)
        return pos.qty if pos else 0.0


@dataclass
class RunReport:
    """Everything one evaluation produced, for display and persistence."""

    started_at: datetime
    strategy: str
    decision: Decision | None = None
    market: MarketStatus | None = None
    orders: list[OrderRequest] = field(default_factory=list)
    results: list[OrderResult] = field(default_factory=list)
    executed: bool = False
    skipped_reason: str | None = None
    account: Account | None = None
    positions: dict[str, Position] = field(default_factory=dict)

    @property
    def had_errors(self) -> bool:
        return any(not r.ok for r in self.results)


def signed_floor(value: float) -> float:
    """Floor toward zero -- 2.7 -> 2, -2.7 -> -2.

    Used for share counts: we never want rounding to *increase* exposure beyond
    the requested weight, in either direction.
    """
    return math.floor(value) if value >= 0 else math.ceil(value)
