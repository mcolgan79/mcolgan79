import logging
from typing import List

from trading.strategy import StrategyConfig, StrategyType

logger = logging.getLogger(__name__)


class RiskManager:
    """Validates proposed trades against per-strategy and account-level risk rules."""

    def check_entry(
        self,
        strategy: StrategyConfig,
        proposed_risk: float,
        existing_positions: List[dict],
    ) -> tuple[bool, str]:
        """Return (allowed, reason). proposed_risk is max $ loss for the new trade."""

        # Per-trade risk cap
        if proposed_risk > strategy.max_risk_per_trade:
            return False, (
                f"Trade risk ${proposed_risk:,.0f} exceeds per-trade limit "
                f"${strategy.max_risk_per_trade:,.0f}"
            )

        # Total strategy risk cap (existing + new)
        strategy_risk = self._calc_strategy_risk(strategy, existing_positions)
        if strategy_risk + proposed_risk > strategy.max_total_risk:
            return False, (
                f"Total strategy risk ${strategy_risk + proposed_risk:,.0f} would exceed "
                f"limit ${strategy.max_total_risk:,.0f}"
            )

        return True, "OK"

    # ------------------------------------------------------------------

    def _calc_strategy_risk(
        self, strategy: StrategyConfig, positions: List[dict]
    ) -> float:
        """Rough max-risk estimate for positions that belong to this strategy."""
        total = 0.0
        for pos in positions:
            underlying = pos.get("underlying_symbol", "")
            if underlying not in strategy.underlyings:
                continue
            if pos.get("instrument_type") != "Equity Option":
                continue
            qty = abs(float(pos.get("quantity", 0)))
            multiplier = float(pos.get("multiplier", 100))
            # For short naked options the max loss is ~strike * multiplier * qty.
            # Use the mark value as a rough proxy when strike isn't handy.
            mark = abs(float(pos.get("mark_price", 0) or 0))
            total += mark * multiplier * qty
        return total

    def max_risk_for_strategy(self, strategy: StrategyConfig, strike: float, qty: int) -> float:
        """Estimate max risk (dollars) for a new options position."""
        multiplier = 100
        if strategy.strategy_type in (
            StrategyType.BULL_PUT_SPREAD,
            StrategyType.BEAR_CALL_SPREAD,
            StrategyType.IRON_CONDOR,
        ):
            return strategy.wing_width * multiplier * qty
        # naked puts/calls/strangles: use strike value as worst-case
        return strike * multiplier * qty
