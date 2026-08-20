"""Strategy registry.

Adding a strategy: subclass ``Strategy``, give it a unique ``name``, and add it
to ``REGISTRY``. Nothing else in the codebase needs to change.
"""

from __future__ import annotations

from typing import Any

from .base import Strategy, StrategyError
from .pair_zscore import PairZScore

REGISTRY: dict[str, type[Strategy]] = {
    PairZScore.name: PairZScore,
}


def available_strategies() -> list[str]:
    return sorted(REGISTRY)


def build_strategy(name: str, params: dict[str, Any] | None = None) -> Strategy:
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise StrategyError(
            f"unknown strategy {name!r}; available: {', '.join(available_strategies())}"
        ) from None
    return cls(**(params or {}))


__all__ = [
    "REGISTRY",
    "PairZScore",
    "Strategy",
    "StrategyError",
    "available_strategies",
    "build_strategy",
]
