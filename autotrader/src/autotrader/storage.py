"""SQLite persistence for runs, signals, orders, and position snapshots.

One row per evaluation in ``runs``, with signals/orders/positions hanging off
it, so ``trader history`` can always answer "why did it do that?".
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import Decision, OrderResult, Position, RunReport

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    broker        TEXT NOT NULL,
    strategy      TEXT NOT NULL,
    mode          TEXT NOT NULL,
    executed      INTEGER NOT NULL,
    market_open   INTEGER,
    skipped       TEXT,
    equity        REAL,
    cash          REAL
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    ts          TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    action      TEXT NOT NULL,
    reason      TEXT,
    targets     TEXT,
    metrics     TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    ts              TEXT NOT NULL,
    broker          TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    qty             REAL NOT NULL,
    order_type      TEXT NOT NULL,
    intent          TEXT,
    dry_run         INTEGER NOT NULL,
    status          TEXT,
    broker_order_id TEXT,
    filled_qty      REAL,
    filled_avg_price REAL,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id   INTEGER NOT NULL REFERENCES runs(id),
    ts       TEXT NOT NULL,
    symbol   TEXT NOT NULL,
    qty      REAL NOT NULL,
    avg_entry_price REAL,
    market_value    REAL
);

CREATE INDEX IF NOT EXISTS idx_signals_run ON signals(run_id);
CREATE INDEX IF NOT EXISTS idx_orders_run ON orders(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
"""


def _iso(value: datetime | None) -> str:
    return (value or datetime.now(timezone.utc)).isoformat()


class Store:
    def __init__(self, path: Path | str, *, multithreaded: bool = False) -> None:
        """``multithreaded`` lets other threads use this connection.

        SQLite itself is fine with that; the caller must serialize access. The
        web server does exactly that -- every touch goes through one lock -- so
        the background trading loop and the HTTP handlers can share a Store.
        """
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=not multithreaded)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- writes ---------------------------------------------------------

    def record_run(self, report: RunReport, broker: str, mode: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, broker, strategy, mode, executed,"
            " market_open, skipped, equity, cash) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                _iso(report.started_at),
                broker,
                report.strategy,
                mode,
                int(report.executed),
                None if report.market is None else int(report.market.is_open),
                report.skipped_reason,
                report.account.equity if report.account else None,
                report.account.cash if report.account else None,
            ),
        )
        run_id = int(cur.lastrowid)

        if report.decision is not None:
            self.record_signal(run_id, report.decision, report.started_at)
        self.record_positions(run_id, report.positions.values(), report.started_at)

        dry_run = not report.executed
        if report.results:
            for result in report.results:
                self.record_order(run_id, result, broker, dry_run=dry_run)
        else:
            for request in report.orders:
                self.record_order(
                    run_id,
                    OrderResult(request=request, status="planned"),
                    broker,
                    dry_run=True,
                )
        self.conn.commit()
        return run_id

    def record_signal(
        self, run_id: int, decision: Decision, ts: datetime | None = None
    ) -> None:
        self.conn.execute(
            "INSERT INTO signals (run_id, ts, strategy, action, reason, targets,"
            " metrics) VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                _iso(ts),
                decision.strategy,
                decision.action.value,
                decision.reason,
                json.dumps(decision.targets),
                json.dumps(decision.metrics),
            ),
        )

    def record_order(
        self, run_id: int, result: OrderResult, broker: str, *, dry_run: bool
    ) -> None:
        req = result.request
        self.conn.execute(
            "INSERT INTO orders (run_id, ts, broker, symbol, side, qty, order_type,"
            " intent, dry_run, status, broker_order_id, filled_qty, filled_avg_price,"
            " error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                _iso(result.submitted_at),
                broker,
                req.symbol,
                req.side.value,
                req.qty,
                req.order_type,
                req.intent,
                int(dry_run),
                result.status,
                result.broker_order_id,
                result.filled_qty,
                result.filled_avg_price,
                result.error,
            ),
        )

    def record_positions(
        self, run_id: int, positions: Iterable[Position], ts: datetime | None = None
    ) -> None:
        stamp = _iso(ts)
        self.conn.executemany(
            "INSERT INTO position_snapshots (run_id, ts, symbol, qty,"
            " avg_entry_price, market_value) VALUES (?,?,?,?,?,?)",
            [
                (run_id, stamp, p.symbol, p.qty, p.avg_entry_price, p.market_value)
                for p in positions
            ],
        )

    # -- reads ----------------------------------------------------------

    def recent_signals(self, limit: int = 20, strategy: str | None = None):
        query = (
            "SELECT s.*, r.mode, r.executed FROM signals s"
            " JOIN runs r ON r.id = s.run_id"
        )
        params: list[Any] = []
        if strategy:
            query += " WHERE s.strategy = ?"
            params.append(strategy)
        query += " ORDER BY s.id DESC LIMIT ?"
        params.append(limit)
        with closing(self.conn.execute(query, params)) as cur:
            return cur.fetchall()

    def recent_orders(self, limit: int = 20, include_dry_run: bool = True):
        query = "SELECT * FROM orders"
        if not include_dry_run:
            query += " WHERE dry_run = 0"
        query += " ORDER BY id DESC LIMIT ?"
        with closing(self.conn.execute(query, (limit,))) as cur:
            return cur.fetchall()

    def recent_runs(self, limit: int = 20):
        with closing(
            self.conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
        ) as cur:
            return cur.fetchall()

    def last_metric_series(self, metric: str, limit: int = 60, strategy: str | None = None):
        """Recent values of one metric (e.g. 'z'), oldest first -- for sparklines."""
        rows = self.recent_signals(limit=limit, strategy=strategy)
        series: list[tuple[str, float]] = []
        for row in reversed(rows):
            try:
                metrics = json.loads(row["metrics"] or "{}")
            except json.JSONDecodeError:
                continue
            if metric in metrics:
                series.append((row["ts"], float(metrics[metric])))
        return series
