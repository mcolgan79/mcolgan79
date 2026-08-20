"""Mean-reversion pair trading on the z-score of a log price ratio.

    spread_t = log(P_a,t) - log(P_b,t)
    z_t      = (spread_t - mean(spread, lookback)) / stdev(spread, lookback)

A high z means leg A is rich relative to leg B, so we short A and buy B and wait
for the ratio to revert. The default pair is GLD (gold) vs GDX (gold miners),
which share a common driver but wander apart on miner-specific risk.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from ..models import Action, Decision, StrategyContext
from .base import Strategy, StrategyError

# Which way we are leaning on the spread.
LONG_SPREAD = 1  # long A, short B  (entered on a low z, expecting z to rise)
SHORT_SPREAD = -1  # short A, long B  (entered on a high z, expecting z to fall)
FLAT = 0


class PairZScore(Strategy):
    name = "pair_zscore"

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.symbol_a = str(params.get("symbol_a", "GLD")).upper()
        self.symbol_b = str(params.get("symbol_b", "GDX")).upper()
        self.lookback = int(params.get("lookback", 60))
        self.entry_z = float(params.get("entry_z", 2.0))
        self.exit_z = float(params.get("exit_z", 0.5))
        self.stop_z = float(params.get("stop_z", 3.5))
        self.leg_weight = float(params.get("leg_weight", 0.10))
        self._validate()

    def _validate(self) -> None:
        if self.symbol_a == self.symbol_b:
            raise StrategyError("symbol_a and symbol_b must differ")
        if self.lookback < 5:
            raise StrategyError("lookback must be at least 5 bars")
        if not 0 <= self.exit_z < self.entry_z:
            raise StrategyError("need 0 <= exit_z < entry_z")
        if self.stop_z <= self.entry_z:
            raise StrategyError("stop_z must be greater than entry_z")
        if not 0 < self.leg_weight <= 1:
            raise StrategyError("leg_weight must be in (0, 1]")

    def symbols(self) -> list[str]:
        return [self.symbol_a, self.symbol_b]

    @property
    def required_bars(self) -> int:
        # A few extra so a single missing bar on one leg does not starve us.
        return self.lookback + 10

    def describe(self) -> str:
        return (
            f"{self.name}: {self.symbol_a}/{self.symbol_b} on {self.timeframe}, "
            f"lookback={self.lookback}, entry=±{self.entry_z}, exit=±{self.exit_z}, "
            f"stop=±{self.stop_z}, {self.leg_weight:.0%} equity per leg"
        )

    # -- signal math ----------------------------------------------------

    def spread_series(self, ctx: StrategyContext) -> list[float]:
        """log(A) - log(B), aligned on the shorter of the two histories."""
        closes_a = ctx.snapshot.closes(self.symbol_a)
        closes_b = ctx.snapshot.closes(self.symbol_b)
        n = min(len(closes_a), len(closes_b))
        if n == 0:
            return []
        # Align from the right: the most recent bars are the ones that matter.
        closes_a, closes_b = closes_a[-n:], closes_b[-n:]
        if any(p <= 0 for p in closes_a + closes_b):
            raise StrategyError("non-positive price in history; cannot take a log")
        return [math.log(a) - math.log(b) for a, b in zip(closes_a, closes_b)]

    def zscore(self, spreads: list[float]) -> tuple[float, float, float]:
        """Returns (z, window_mean, window_stdev) for the latest spread."""
        window = spreads[-self.lookback :]
        mean = statistics.fmean(window)
        stdev = statistics.stdev(window)  # sample stdev; window is a sample
        if stdev == 0:
            raise StrategyError("spread has zero variance over the lookback window")
        return (spreads[-1] - mean) / stdev, mean, stdev

    # -- position state -------------------------------------------------

    def _current_side(self, ctx: StrategyContext) -> tuple[int, bool]:
        """(side, is_clean) -- is_clean is False for a half-filled or same-way pair."""
        qty_a, qty_b = ctx.qty(self.symbol_a), ctx.qty(self.symbol_b)
        sign_a = (qty_a > 0) - (qty_a < 0)
        sign_b = (qty_b > 0) - (qty_b < 0)
        if sign_a == 0 and sign_b == 0:
            return FLAT, True
        if sign_a == -sign_b and sign_a != 0:
            return (LONG_SPREAD if sign_a > 0 else SHORT_SPREAD), True
        return FLAT, False  # one leg missing, or both legs the same way

    def _targets(self, side: int) -> dict[str, float]:
        weight = self.leg_weight * side
        return {self.symbol_a: weight, self.symbol_b: -weight}

    def _flat_targets(self) -> dict[str, float]:
        return {self.symbol_a: 0.0, self.symbol_b: 0.0}

    # -- decision -------------------------------------------------------

    def evaluate(self, ctx: StrategyContext) -> Decision:
        spreads = self.spread_series(ctx)
        if len(spreads) < self.lookback:
            return Decision(
                strategy=self.name,
                action=Action.SKIP,
                targets={},
                reason=(
                    f"need {self.lookback} aligned bars, have {len(spreads)} "
                    f"-- waiting for more history"
                ),
                metrics={"bars_available": float(len(spreads))},
            )

        z, mean, stdev = self.zscore(spreads)
        price_a = ctx.snapshot.last_price(self.symbol_a) or 0.0
        price_b = ctx.snapshot.last_price(self.symbol_b) or 0.0
        metrics = {
            "z": z,
            "spread": spreads[-1],
            "spread_mean": mean,
            "spread_stdev": stdev,
            "price_a": price_a,
            "price_b": price_b,
            "ratio": (price_a / price_b) if price_b else 0.0,
            "bars_used": float(min(len(spreads), self.lookback)),
        }
        side, clean = self._current_side(ctx)

        if not clean:
            return Decision(
                strategy=self.name,
                action=Action.EXIT,
                targets=self._flat_targets(),
                reason=(
                    f"legs are inconsistent ({self.symbol_a}={ctx.qty(self.symbol_a):g}, "
                    f"{self.symbol_b}={ctx.qty(self.symbol_b):g}); flattening to resync"
                ),
                metrics=metrics,
            )

        if side == FLAT:
            return self._evaluate_flat(z, metrics)
        return self._evaluate_open(side, z, metrics)

    def _evaluate_flat(self, z: float, metrics: dict[str, float]) -> Decision:
        if abs(z) >= self.stop_z:
            return Decision(
                strategy=self.name,
                action=Action.NONE,
                targets=self._flat_targets(),
                reason=(
                    f"z={z:+.2f} is beyond the stop band (±{self.stop_z}); the "
                    f"relationship may have broken -- standing aside"
                ),
                metrics=metrics,
            )
        if z >= self.entry_z:
            return Decision(
                strategy=self.name,
                action=Action.ENTER,
                targets=self._targets(SHORT_SPREAD),
                reason=(
                    f"z={z:+.2f} >= +{self.entry_z}: {self.symbol_a} rich vs "
                    f"{self.symbol_b} -- short {self.symbol_a} / long {self.symbol_b}"
                ),
                metrics=metrics,
            )
        if z <= -self.entry_z:
            return Decision(
                strategy=self.name,
                action=Action.ENTER,
                targets=self._targets(LONG_SPREAD),
                reason=(
                    f"z={z:+.2f} <= -{self.entry_z}: {self.symbol_a} cheap vs "
                    f"{self.symbol_b} -- long {self.symbol_a} / short {self.symbol_b}"
                ),
                metrics=metrics,
            )
        return Decision(
            strategy=self.name,
            action=Action.NONE,
            targets=self._flat_targets(),
            reason=f"z={z:+.2f} inside the ±{self.entry_z} entry band -- no trade",
            metrics=metrics,
        )

    def _evaluate_open(
        self, side: int, z: float, metrics: dict[str, float]
    ) -> Decision:
        metrics["side"] = float(side)
        # Favorable direction depends on which way we leaned. A long spread was
        # opened on a deeply negative z and profits as z rises toward zero, so
        # reaching (or overshooting) -exit_z is the take-profit.
        reverted = z >= -self.exit_z if side == LONG_SPREAD else z <= self.exit_z
        stopped = z <= -self.stop_z if side == LONG_SPREAD else z >= self.stop_z
        label = "long" if side == LONG_SPREAD else "short"

        if reverted:
            return Decision(
                strategy=self.name,
                action=Action.EXIT,
                targets=self._flat_targets(),
                reason=(
                    f"z={z:+.2f} reached the ±{self.exit_z} exit band; closing the "
                    f"{label} spread"
                ),
                metrics=metrics,
            )
        if stopped:
            return Decision(
                strategy=self.name,
                action=Action.STOP,
                targets=self._flat_targets(),
                reason=(
                    f"z={z:+.2f} moved against the {label} spread past ±{self.stop_z}; "
                    f"stopping out"
                ),
                metrics=metrics,
            )
        return Decision(
            strategy=self.name,
            action=Action.MAINTAIN,
            targets=self._targets(side),
            reason=f"z={z:+.2f}; holding the {label} spread",
            metrics=metrics,
        )
