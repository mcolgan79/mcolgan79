"""The execution engine: data -> decision -> orders -> broker.

The engine is the only component that knows about both brokers and strategies.
Strategies emit target weights; the engine converts those into whole-share
orders, applies the configured guardrails, submits, and records everything.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .brokers.base import Broker
from .config import Config
from .models import (
    Account,
    Action,
    Decision,
    MarketSnapshot,
    MarketStatus,
    OrderRequest,
    OrderResult,
    OrderSide,
    Position,
    RunReport,
    StrategyContext,
    signed_floor,
)
from .storage import Store
from .strategies.base import Strategy

log = logging.getLogger(__name__)

# Below this many shares an order is not worth sending.
MIN_SHARES = 1.0
MIN_FRACTIONAL_SHARES = 1e-4


def plan_orders(
    targets: dict[str, float],
    positions: dict[str, Position],
    prices: dict[str, float],
    equity: float,
    *,
    allow_fractional: bool = False,
) -> list[OrderRequest]:
    """Turn signed target weights into market orders.

    Two rules matter here:

    * Share counts are floored toward zero. A short leg can never be fractional
      at Alpaca, and rounding up would quietly overshoot the requested weight.
    * A position that flips sign is sent as two orders -- close, then open. A
      single order that crosses zero gets rejected by most venues, and splitting
      also means a rejected second leg leaves us flat rather than naked.
    """
    min_qty = MIN_FRACTIONAL_SHARES if allow_fractional else MIN_SHARES
    reducing: list[OrderRequest] = []
    opening: list[OrderRequest] = []

    for symbol, weight in targets.items():
        price = prices.get(symbol, 0.0)
        if price <= 0:
            log.warning("no price for %s; skipping its leg", symbol)
            continue

        raw_target = weight * equity / price
        target_qty = raw_target if allow_fractional else signed_floor(raw_target)
        if weight != 0 and target_qty == 0:
            log.warning(
                "%s target of %.2f%% equity is under one share at $%.2f; skipping",
                symbol,
                weight * 100,
                price,
            )
        current_qty = positions[symbol].qty if symbol in positions else 0.0
        delta = target_qty - current_qty
        if abs(delta) < min_qty:
            continue

        flips = current_qty != 0 and target_qty != 0 and (
            (current_qty > 0) != (target_qty > 0)
        )
        if flips:
            reducing.append(
                OrderRequest(
                    symbol=symbol,
                    qty=abs(current_qty),
                    side=OrderSide.SELL if current_qty > 0 else OrderSide.BUY,
                    intent=f"close {'long' if current_qty > 0 else 'short'} before flipping",
                )
            )
            opening.append(
                OrderRequest(
                    symbol=symbol,
                    qty=abs(target_qty),
                    side=OrderSide.BUY if target_qty > 0 else OrderSide.SELL,
                    intent=f"open {'long' if target_qty > 0 else 'short'} {abs(weight):.0%} leg",
                )
            )
            continue

        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        shrinking = abs(target_qty) < abs(current_qty)
        intent = (
            f"{'reduce' if target_qty else 'close'} {symbol}"
            if shrinking
            else f"{'open' if current_qty == 0 else 'add to'} {abs(weight):.0%} leg"
        )
        request = OrderRequest(symbol=symbol, qty=abs(delta), side=side, intent=intent)
        (reducing if shrinking else opening).append(request)

    # Closes first: they free up buying power for the opens that follow.
    return reducing + opening


class Engine:
    def __init__(
        self,
        config: Config,
        broker: Broker,
        strategy: Strategy,
        store: Store | None = None,
    ) -> None:
        self.config = config
        self.broker = broker
        self.strategy = strategy
        self.store = store

    # -- guardrails -----------------------------------------------------

    def _blocking_guardrail(
        self, market: MarketStatus, decision: Decision, positions: dict[str, Position]
    ) -> str | None:
        guards = self.config.engine.guardrails
        if guards.require_market_open and not market.is_open:
            return f"market is closed ({market.detail})"
        if guards.respect_calendar and not self.broker.is_trading_day():
            return "not a scheduled trading day"
        if decision.action is Action.ENTER and guards.max_open_strategies >= 1:
            already_open = [
                s for s in self.strategy.symbols() if abs(positions.get(s, _ZERO).qty) > 0
            ]
            if already_open:
                return (
                    f"guardrail: already holding {', '.join(already_open)} and "
                    f"max_open_strategies={guards.max_open_strategies} forbids adding"
                )
        return None

    # -- main loop ------------------------------------------------------

    def run_once(
        self, *, dry_run: bool | None = None, ignore_market_hours: bool = False
    ) -> RunReport:
        execute = self.config.engine.execute if dry_run is None else not dry_run
        report = RunReport(
            started_at=datetime.now(timezone.utc), strategy=self.strategy.name
        )

        report.market = self.broker.get_market_status()
        report.account = self.broker.get_account()
        report.positions = self.broker.get_positions()

        snapshot = MarketSnapshot(
            as_of=report.started_at,
            bars=self.broker.get_bars(
                self.strategy.symbols(),
                self.strategy.timeframe,
                self.strategy.required_bars,
            ),
        )
        ctx = StrategyContext(
            account=report.account, positions=report.positions, snapshot=snapshot
        )
        report.decision = self.strategy.evaluate(ctx)
        log.info(
            "%s -> %s: %s",
            self.strategy.name,
            report.decision.action.value,
            report.decision.reason,
        )

        if report.decision.action is Action.SKIP:
            report.skipped_reason = report.decision.reason
            return self._finish(report, execute=False)

        if (
            report.decision.action is Action.MAINTAIN
            and not self.strategy.rebalance_on_maintain
        ):
            # Re-sizing an open position on every pass is a slow pyramid, not a
            # hold. Leave it exactly as it is until the strategy says exit.
            report.skipped_reason = "holding the existing position (no rebalancing)"
            return self._finish(report, execute=False)

        blocked = None
        if not ignore_market_hours:
            blocked = self._blocking_guardrail(
                report.market, report.decision, report.positions
            )
        if blocked:
            log.info("not trading: %s", blocked)
            report.skipped_reason = blocked
            return self._finish(report, execute=False)

        prices = {
            symbol: snapshot.last_price(symbol) or 0.0
            for symbol in self.strategy.symbols()
        }
        report.orders = plan_orders(
            report.decision.targets,
            report.positions,
            prices,
            report.account.equity,
            allow_fractional=self.config.engine.guardrails.allow_fractional,
        )
        if not report.orders:
            log.info("no orders needed; portfolio already matches the target")
            return self._finish(report, execute=False)

        self._log_neutrality(report.decision, prices, report.account)

        if not execute:
            log.info("dry run: %d order(s) planned, none submitted", len(report.orders))
            return self._finish(report, execute=False)

        report.results = self._submit(report.orders)
        return self._finish(report, execute=True)

    def _submit(self, orders: list[OrderRequest]) -> list[OrderResult]:
        results: list[OrderResult] = []
        for request in orders:
            log.info("submitting %s (%s)", request, request.intent)
            result = self.broker.submit_order(request)
            results.append(result)
            if not result.ok:
                # A failed close would leave the follow-on open unhedged.
                log.error("aborting remaining orders after failure on %s", request)
                break
        return results

    def _log_neutrality(
        self, decision: Decision, prices: dict[str, float], account: Account
    ) -> None:
        """Report how far whole-share rounding pushed us off the target weights."""
        for symbol, weight in decision.targets.items():
            price = prices.get(symbol, 0.0)
            if not weight or price <= 0:
                continue
            wanted = abs(weight) * account.equity
            shares = abs(signed_floor(weight * account.equity / price))
            actual = shares * price
            log.info(
                "%s leg: %.0f shares = $%.0f vs $%.0f target (%+.2f%% rounding drift)",
                symbol,
                shares,
                actual,
                wanted,
                (actual - wanted) / wanted * 100 if wanted else 0.0,
            )

    def _finish(self, report: RunReport, *, execute: bool) -> RunReport:
        report.executed = execute
        if self.store is not None:
            self.store.record_run(
                report, broker=self.broker.name, mode="live" if execute else "dry-run"
            )
        return report

    # -- manual intervention --------------------------------------------

    def flatten(self, *, dry_run: bool = False) -> RunReport:
        """Close every position this strategy touches, regardless of signal."""
        report = RunReport(
            started_at=datetime.now(timezone.utc), strategy=self.strategy.name
        )
        report.market = self.broker.get_market_status()
        report.account = self.broker.get_account()
        report.positions = self.broker.get_positions()
        report.decision = Decision(
            strategy=self.strategy.name,
            action=Action.EXIT,
            targets={s: 0.0 for s in self.strategy.symbols()},
            reason="manual flatten requested",
        )
        prices = {
            symbol: (
                report.positions[symbol].market_value / report.positions[symbol].qty
                if symbol in report.positions and report.positions[symbol].qty
                else 1.0
            )
            for symbol in self.strategy.symbols()
        }
        report.orders = plan_orders(
            report.decision.targets,
            report.positions,
            prices,
            report.account.equity,
            allow_fractional=True,  # mirror whatever is actually held, fractions included
        )
        if report.orders and not dry_run:
            report.results = self._submit(report.orders)
            return self._finish(report, execute=True)
        return self._finish(report, execute=False)


_ZERO = Position(symbol="", qty=0.0, avg_entry_price=0.0, market_value=0.0)
