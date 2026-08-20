"""Timeframe parsing shared by the broker adapters and the backtester.

Kept free of any SDK import so the backtester and tests can use it without
pulling in alpaca-py.
"""

from __future__ import annotations

import re

_TIMEFRAME_RE = re.compile(r"^\s*(\d+)?\s*(min|minute|hour|day|week|month)s?\s*$", re.I)

#: Approximate regular-hours bars per session for a 1-unit bar of each kind.
BARS_PER_SESSION = {
    "minute": 390.0,
    "hour": 6.5,
    "day": 1.0,
    "week": 0.2,
    "month": 1 / 21,
}

#: US equity trading days per year.
SESSIONS_PER_YEAR = 252


class TimeframeError(ValueError):
    """Raised for a timeframe string we cannot parse."""


def parse_timeframe_parts(timeframe: str) -> tuple[int, str]:
    """'15Min' -> (15, 'minute'). Unit names are normalized."""
    match = _TIMEFRAME_RE.match(timeframe)
    if not match:
        raise TimeframeError(
            f"unsupported timeframe {timeframe!r}; try '1Day', '1Hour', '15Min'"
        )
    amount = int(match.group(1) or 1)
    unit = match.group(2).lower()
    return amount, ("minute" if unit == "min" else unit)


def bars_per_session(timeframe: str) -> float:
    """How many bars of this size fit in one trading session."""
    amount, unit = parse_timeframe_parts(timeframe)
    return BARS_PER_SESSION[unit] / max(amount, 1)


def periods_per_year(timeframe: str) -> float:
    """Annualization factor for returns sampled at this bar size."""
    return bars_per_session(timeframe) * SESSIONS_PER_YEAR
