"""Tastytrade adapter -- planned, not implemented.

What a working implementation needs:

* The official ``tastytrade`` Python SDK against the certification (sandbox)
  environment at api.cert.tastyworks.com, which is the closest analogue to
  Alpaca's paper account and the right place to develop.
* Session auth (username/password -> session token, refreshed periodically)
  rather than the static key/secret pair Alpaca uses, so ``Config`` grows a
  credentials block for it.
* Order payloads are leg-based: a pair trade can be submitted as a single
  multi-leg order rather than the two independent orders the Alpaca adapter
  sends. Worth exploiting -- it removes the leg-fill-risk the engine currently
  manages by ordering closes before opens.
* Equity shorting is supported on margin accounts, so the default strategy
  transfers over unchanged.

Until then this class exists so ``brokers.build_broker("tastytrade")`` fails
with an explanation rather than a KeyError.
"""

from __future__ import annotations

from .base import Broker, BrokerError

_MESSAGE = (
    "The Tastytrade broker is not implemented yet. Planned path: the official "
    "tastytrade SDK against the certification sandbox, with multi-leg order "
    "support. Use broker.name = \"alpaca\" for now."
)


class TastytradeBroker(Broker):
    name = "tastytrade"
    paper = True

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
