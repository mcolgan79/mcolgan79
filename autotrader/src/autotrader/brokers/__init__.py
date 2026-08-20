"""Broker registry.

Adding a venue: subclass ``Broker``, give it a unique ``name``, and register it
here. ``build_broker`` is the only place the rest of the code constructs one.
"""

from __future__ import annotations

from ..config import Config
from .base import Broker, BrokerError
from .robinhood import RobinhoodBroker
from .tastytrade import TastytradeBroker

REGISTRY: dict[str, type[Broker]] = {
    "robinhood": RobinhoodBroker,
    "tastytrade": TastytradeBroker,
}


def available_brokers() -> list[str]:
    return sorted(set(REGISTRY) | {"alpaca"})


def build_broker(config: Config) -> Broker:
    name = config.broker.name.lower()
    if name == "alpaca":
        # Imported lazily: pulls in the alpaca-py SDK.
        from .alpaca import AlpacaBroker

        key, secret = config.require_credentials()
        return AlpacaBroker(
            key,
            secret,
            paper=config.broker.paper,
            data_feed=config.broker.data_feed,
            url_override=config.broker.base_url,
        )
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise BrokerError(
            f"unknown broker {name!r}; available: {', '.join(available_brokers())}"
        ) from None
    return cls()


__all__ = [
    "Broker",
    "BrokerError",
    "REGISTRY",
    "available_brokers",
    "build_broker",
]
