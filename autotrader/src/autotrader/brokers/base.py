"""The Broker interface every venue implementation must satisfy.

The engine only ever talks to this surface, so adding Robinhood or Tastytrade
later means writing one new subclass -- no changes to the engine or strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import (
    Account,
    Bar,
    MarketStatus,
    OrderRequest,
    OrderResult,
    Position,
)


class BrokerError(Exception):
    """Any failure talking to a venue."""


class Broker(ABC):
    #: Short identifier used in config, logs, and the storage layer.
    name: str = "base"

    #: Whether this connection points at a simulated account.
    paper: bool = True

    @abstractmethod
    def get_account(self) -> Account:
        """Equity, cash, and buying power for the connected account."""

    @abstractmethod
    def get_positions(self) -> dict[str, Position]:
        """Open positions keyed by symbol. Shorts carry a negative qty."""

    @abstractmethod
    def get_bars(
        self, symbols: list[str], timeframe: str, limit: int
    ) -> dict[str, list[Bar]]:
        """The most recent ``limit`` bars per symbol, oldest first."""

    @abstractmethod
    def get_market_status(self) -> MarketStatus:
        """Whether the venue is currently accepting regular-hours orders."""

    @abstractmethod
    def submit_order(self, request: OrderRequest) -> OrderResult:
        """Send a single order. Implementations must not raise on rejection --
        return an ``OrderResult`` with ``error`` set so the engine can report
        partial failure and keep going."""

    def is_trading_day(self, day: "datetime | None" = None) -> bool:
        """Whether the venue has a session on this date (holidays excluded).

        Defaults to True; override where the venue exposes a calendar.
        """
        return True

    def is_shortable(self, symbol: str) -> bool:
        """Whether the venue will accept a short sale in this symbol.

        Defaults to True; override where the venue can tell you.
        """
        return True

    def cancel_open_orders(self, symbols: list[str] | None = None) -> int:
        """Cancel resting orders. Returns the number cancelled. Optional."""
        return 0

    def close(self) -> None:
        """Release any network resources. Optional."""
