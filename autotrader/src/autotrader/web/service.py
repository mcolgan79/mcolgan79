"""Thread-safe wrapper around the Engine, plus the background trading loop.

Two kinds of caller reach the engine: HTTP request handlers (one thread per
request) and the polling loop. Everything funnels through a single lock, so the
Engine, the Broker's HTTP client, and the SQLite connection only ever see one
caller at a time.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..brokers.base import Broker, BrokerError
from ..config import Config
from ..engine import Engine
from ..models import RunReport
from ..storage import Store
from ..strategies.base import Strategy, StrategyError

log = logging.getLogger(__name__)

#: Never let the UI request a punishing poll rate against the broker's API.
MIN_LOOP_INTERVAL = 30


@dataclass
class LoopStatus:
    running: bool = False
    interval: int = 900
    dry_run: bool = False
    started_at: datetime | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    runs: int = 0
    last_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "interval": self.interval,
            "dry_run": self.dry_run,
            "started_at": _iso(self.started_at),
            "last_run_at": _iso(self.last_run_at),
            "next_run_at": _iso(self.next_run_at),
            "runs": self.runs,
            "last_error": self.last_error,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class TradingService:
    """Everything the web layer is allowed to do, serialized behind one lock."""

    def __init__(
        self,
        config: Config,
        broker: Broker,
        strategy: Strategy,
        store: Store,
    ) -> None:
        self.config = config
        self.broker = broker
        self.strategy = strategy
        self.store = store
        self.engine = Engine(config, broker, strategy, store)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.loop = LoopStatus(interval=config.engine.poll_interval)
        self._last_report: RunReport | None = None

    # -- reads ----------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Everything the dashboard renders in one call."""
        with self._lock:
            payload: dict[str, Any] = {
                "broker": {
                    "name": self.broker.name,
                    "paper": bool(self.broker.paper),
                },
                "strategy": {
                    "name": self.strategy.name,
                    "description": self.strategy.describe(),
                    "symbols": self.strategy.symbols(),
                    "params": _strategy_params(self.strategy),
                },
                "loop": self.loop.as_dict(),
                "errors": [],
                "as_of": datetime.now(timezone.utc).isoformat(),
            }
            try:
                account = self.broker.get_account()
                payload["account"] = {
                    "equity": account.equity,
                    "cash": account.cash,
                    "buying_power": account.buying_power,
                }
            except BrokerError as exc:
                payload["account"] = None
                payload["errors"].append(str(exc))
            try:
                market = self.broker.get_market_status()
                payload["market"] = {
                    "is_open": market.is_open,
                    "detail": market.detail,
                    "next_open": _iso(market.next_open),
                    "next_close": _iso(market.next_close),
                }
            except BrokerError as exc:
                payload["market"] = None
                payload["errors"].append(str(exc))
            try:
                positions = self.broker.get_positions()
                payload["positions"] = [
                    {
                        "symbol": p.symbol,
                        "qty": p.qty,
                        "side": p.side,
                        "avg_entry_price": p.avg_entry_price,
                        "market_value": p.market_value,
                        "is_strategy_leg": p.symbol in self.strategy.symbols(),
                    }
                    for p in sorted(positions.values(), key=lambda p: p.symbol)
                ]
            except BrokerError as exc:
                payload["positions"] = []
                payload["errors"].append(str(exc))

            payload["signal"] = self._evaluate_quietly()
            payload["activity"] = self._recent_activity()
            return payload

    def _evaluate_quietly(self) -> dict[str, Any] | None:
        """Compute the current signal without trading and without recording it."""
        saved_store, saved_execute = self.engine.store, self.config.engine.execute
        self.engine.store = None
        self.config.engine.execute = False
        try:
            report = self.engine.run_once(dry_run=True)
        except (BrokerError, StrategyError) as exc:
            log.warning("signal evaluation failed: %s", exc)
            return {"error": str(exc)}
        finally:
            self.engine.store = saved_store
            self.config.engine.execute = saved_execute
        return _decision_payload(report)

    def _recent_activity(self) -> dict[str, list[dict[str, Any]]]:
        signals = [
            {
                "ts": row["ts"],
                "action": row["action"],
                "reason": row["reason"],
                "metrics": row["metrics"],
            }
            for row in self.store.recent_signals(limit=12)
        ]
        orders = [
            {
                "ts": row["ts"],
                "symbol": row["symbol"],
                "side": row["side"],
                "qty": row["qty"],
                "status": row["status"],
                "filled_qty": row["filled_qty"],
                "filled_avg_price": row["filled_avg_price"],
                "dry_run": bool(row["dry_run"]),
                "error": row["error"],
                "intent": row["intent"],
            }
            for row in self.store.recent_orders(limit=12)
        ]
        return {"signals": signals, "orders": orders}

    # -- actions --------------------------------------------------------

    def run_once(self, *, dry_run: bool, ignore_market_hours: bool = False) -> dict[str, Any]:
        with self._lock:
            report = self.engine.run_once(
                dry_run=dry_run, ignore_market_hours=ignore_market_hours
            )
            self._last_report = report
            return _report_payload(report)

    def flatten(self, *, dry_run: bool = False) -> dict[str, Any]:
        with self._lock:
            report = self.engine.flatten(dry_run=dry_run)
            self._last_report = report
            return _report_payload(report)

    # -- the loop -------------------------------------------------------

    def start_loop(self, *, interval: int, dry_run: bool) -> LoopStatus:
        with self._lock:
            if self.loop.running:
                return self.loop
            interval = max(int(interval), MIN_LOOP_INTERVAL)
            self._stop.clear()
            self.loop = LoopStatus(
                running=True,
                interval=interval,
                dry_run=dry_run,
                started_at=datetime.now(timezone.utc),
                next_run_at=datetime.now(timezone.utc),
            )
            self._thread = threading.Thread(
                target=self._loop_body, name="autotrader-loop", daemon=True
            )
            self._thread.start()
            log.warning(
                "trading loop STARTED (every %ss, %s) -- it keeps running until "
                "stopped or the server exits",
                interval,
                "dry run" if dry_run else "LIVE on the paper account",
            )
            return self.loop

    def stop_loop(self) -> LoopStatus:
        thread = self._thread
        self._stop.set()
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5)
        with self._lock:
            self.loop.running = False
            self.loop.next_run_at = None
            self._thread = None
            log.warning("trading loop STOPPED after %d run(s)", self.loop.runs)
            return self.loop

    def _loop_body(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    dry_run = self.loop.dry_run
                # Routed through run_once so the lock and bookkeeping are
                # identical to a manual run from the dashboard.
                payload = self.run_once(dry_run=dry_run)
                with self._lock:
                    self.loop.runs += 1
                    self.loop.last_run_at = datetime.now(timezone.utc)
                    self.loop.last_error = payload.get("error")
            except Exception as exc:  # noqa: BLE001 - a loop must survive one bad pass
                log.exception("loop iteration failed")
                with self._lock:
                    self.loop.last_error = str(exc)
            with self._lock:
                interval = self.loop.interval
                self.loop.next_run_at = datetime.now(timezone.utc) + timedelta(
                    seconds=interval
                )
            self._stop.wait(interval)
        with self._lock:
            self.loop.running = False
            self.loop.next_run_at = None

    def shutdown(self) -> None:
        self.stop_loop()
        with self._lock:
            self.store.close()
            self.broker.close()


def _strategy_params(strategy: Strategy) -> dict[str, Any]:
    keys = ("entry_z", "exit_z", "stop_z", "lookback", "leg_weight", "timeframe")
    out: dict[str, Any] = {}
    for key in keys:
        value = getattr(strategy, key, None)
        if value is None:
            value = strategy.params.get(key)
        if value is not None:
            out[key] = value
    return out


def _decision_payload(report: RunReport) -> dict[str, Any]:
    decision = report.decision
    if decision is None:
        return {"error": "no decision produced"}
    return {
        "action": decision.action.value,
        "reason": decision.reason,
        "metrics": decision.metrics,
        "targets": decision.targets,
        "blocked": report.skipped_reason,
        "would_trade": bool(report.orders),
        "orders": [
            {
                "symbol": o.symbol,
                "side": o.side.value,
                "qty": o.qty,
                "intent": o.intent,
            }
            for o in report.orders
        ],
    }


def _report_payload(report: RunReport) -> dict[str, Any]:
    payload = _decision_payload(report)
    payload.update(
        {
            "executed": report.executed,
            "skipped_reason": report.skipped_reason,
            "results": [
                {
                    "symbol": r.request.symbol,
                    "side": r.request.side.value,
                    "qty": r.request.qty,
                    "status": r.status,
                    "filled_qty": r.filled_qty,
                    "filled_avg_price": r.filled_avg_price,
                    "error": r.error,
                }
                for r in report.results
            ],
            "had_errors": report.had_errors,
        }
    )
    if report.had_errors:
        payload["error"] = next(
            (r.error for r in report.results if r.error), "an order was rejected"
        )
    return payload


__all__ = ["LoopStatus", "TradingService", "MIN_LOOP_INTERVAL"]
