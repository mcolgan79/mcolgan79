"""The Strategy interface.

A strategy is a pure function of (market data, account state) -> Decision. It
never places orders and never knows which broker it is running against; the
engine turns its target weights into orders. That keeps strategies trivially
unit-testable and reusable across venues.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import Decision, StrategyContext


class StrategyError(Exception):
    """Raised for misconfigured strategy parameters."""


class Strategy(ABC):
    #: Short identifier used in config, logs, and storage.
    name: str = "base"

    def __init__(self, **params: Any) -> None:
        self.params = params

    @abstractmethod
    def symbols(self) -> list[str]:
        """Every symbol this strategy needs bars for and may trade."""

    @property
    def timeframe(self) -> str:
        """Bar size the strategy wants, e.g. '1Day', '1Hour', '15Min'."""
        return str(self.params.get("timeframe", "1Day"))

    #: When False, an open position is left alone while the strategy reports
    #: MAINTAIN -- the engine will not top it up as prices and equity drift.
    #: Set True on a strategy that genuinely wants continuous rebalancing.
    rebalance_on_maintain: bool = False

    @property
    def required_bars(self) -> int:
        """How many bars back the engine should fetch."""
        return 200

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> Decision:
        """Decide the target portfolio given current data and positions."""

    def describe(self) -> str:
        """One-line human summary, shown by `trader status`."""
        return self.name
