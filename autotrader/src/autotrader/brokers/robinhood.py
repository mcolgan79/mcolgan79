"""Robinhood adapter -- planned, not implemented.

What a working implementation needs:

* An unofficial client (``robin_stocks`` is the usual choice) plus device-token
  and MFA handling; Robinhood has no public trading API and no paper account,
  so there is no safe sandbox to develop against.
* Equity shorting is not supported on Robinhood cash/instant accounts, which
  rules out the default pair strategy as written. A Robinhood build of this
  platform realistically trades long-only or long/inverse-ETF variants, or uses
  options for the short leg.
* ``get_bars`` maps to the historicals endpoint (5minute/10minute/hour/day
  intervals), which needs translating into this project's timeframe strings.

Until then this class exists so ``brokers.build_broker("robinhood")`` fails with
an explanation rather than a KeyError.
"""

from __future__ import annotations

from .base import Broker, BrokerError

_MESSAGE = (
    "The Robinhood broker is not implemented yet. Robinhood has no official "
    "trading API and no paper environment, and it does not support equity "
    "shorting -- the default GLD/GDX pair strategy cannot run there as written. "
    "Use broker.name = \"alpaca\" for now."
)


class RobinhoodBroker(Broker):
    name = "robinhood"
    paper = False

    def __init__(self, *args, **kwargs) -> None:
        raise BrokerError(_MESSAGE)

    def get_account(self):  # pragma: no cover - unreachable
        raise BrokerError(_MESSAGE)

    def get_positions(self):  # pragma: no cover
        raise BrokerError(_MESSAGE)

    def get_bars(self, symbols, timeframe, limit):  # pragma: no cover
        raise BrokerError(_MESSAGE)

    def get_market_status(self):  # pragma: no cover
        raise BrokerError(_MESSAGE)

    def submit_order(self, request):  # pragma: no cover
        raise BrokerError(_MESSAGE)
