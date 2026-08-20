"""Historical replay of a strategy, using the live decision and sizing code.

The point of this module is that it does *not* reimplement the strategy or the
order math. It walks bars forward, hands the strategy the same
``StrategyContext`` the engine builds, and feeds the resulting targets through
the same ``plan_orders``. What differs from live is only the fill: instead of a
broker, orders hit a simulated portfolio at a modeled price.

Lookahead is avoided by construction -- at bar *i* the strategy only ever sees
bars ``[0..i]``, and the default fill happens at the *next* bar's open.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Literal

from .engine import plan_orders
from .models import (
    Account,
    Action,
    Bar,
    Decision,
    MarketSnapshot,
    OrderRequest,
    OrderSide,
    Position,
    StrategyContext,
)
from .strategies.base import Strategy
from .timeframes import periods_per_year

log = logging.getLogger(__name__)

FillMode = Literal["next_open", "close"]


class BacktestError(Exception):
    """Raised when a backtest cannot be run at all (no data, no overlap)."""


@dataclass
class Fill:
    timestamp: datetime
    symbol: str
    side: OrderSide
    qty: float
    price: float  # after slippage
    commission: float
    intent: str = ""


@dataclass
class Trade:
    """One round trip: flat -> positioned -> flat."""

    entry_at: datetime
    exit_at: datetime
    side: str  # "long_spread" / "short_spread" / "long" / "short"
    entry_equity: float
    exit_equity: float
    entry_z: float | None
    exit_z: float | None
    exit_action: str
    bars_held: int

    @property
    def pnl(self) -> float:
        return self.exit_equity - self.entry_equity

    @property
    def return_pct(self) -> float:
        return self.pnl / self.entry_equity if self.entry_equity else 0.0

    @property
    def won(self) -> bool:
        return self.pnl > 0


@dataclass
class BacktestResult:
    strategy: str
    timeframe: str
    symbols: list[str]
    starting_equity: float
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    decisions: list[tuple[datetime, Decision]] = field(default_factory=list)
    warmup_bars: int = 0
    benchmark_curve: list[tuple[datetime, float]] = field(default_factory=list)
    benchmark_symbol: str | None = None

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1][1] if self.equity_curve else self.starting_equity

    @property
    def start(self) -> datetime | None:
        return self.equity_curve[0][0] if self.equity_curve else None

    @property
    def end(self) -> datetime | None:
        return self.equity_curve[-1][0] if self.equity_curve else None

    def stats(self) -> dict[str, float]:
        return compute_stats(self)


# -- portfolio ----------------------------------------------------------


class SimPortfolio:
    """Cash plus signed share counts. No margin limits are enforced.

    Equity is cash plus the mark-to-market value of the positions, so a short
    sale is equity-neutral at the moment of the fill (cash in, negative market
    value out) and profits as the price falls.
    """

    def __init__(self, starting_cash: float) -> None:
        self.cash = starting_cash
        self.qty: dict[str, float] = {}
        self.cost_basis: dict[str, float] = {}

    def positions(self, prices: dict[str, float]) -> dict[str, Position]:
        out: dict[str, Position] = {}
        for symbol, qty in self.qty.items():
            if qty == 0:
                continue
            price = prices.get(symbol, 0.0)
            out[symbol] = Position(
                symbol=symbol,
                qty=qty,
                avg_entry_price=self.cost_basis.get(symbol, price),
                market_value=qty * price,
            )
        return out

    def equity(self, prices: dict[str, float]) -> float:
        held = sum(qty * prices.get(sym, 0.0) for sym, qty in self.qty.items())
        return self.cash + held

    @property
    def is_flat(self) -> bool:
        return all(qty == 0 for qty in self.qty.values())

    def apply(self, fill: Fill) -> None:
        delta = fill.qty if fill.side is OrderSide.BUY else -fill.qty
        previous = self.qty.get(fill.symbol, 0.0)
        new_qty = previous + delta

        # Average cost is only meaningful while the position keeps its sign.
        if previous == 0 or (previous > 0) != (new_qty > 0):
            self.cost_basis[fill.symbol] = fill.price
        elif abs(new_qty) > abs(previous):
            prior_cost = self.cost_basis.get(fill.symbol, fill.price)
            self.cost_basis[fill.symbol] = (
                prior_cost * abs(previous) + fill.price * abs(delta)
            ) / abs(new_qty)

        self.qty[fill.symbol] = new_qty
        self.cash -= delta * fill.price
        self.cash -= fill.commission


# -- data alignment -----------------------------------------------------


def align_bars(bars: dict[str, list[Bar]]) -> tuple[list[datetime], dict[str, list[Bar]]]:
    """Restrict every symbol to the timestamps all of them share.

    A pair signal computed from bars that are a day apart is not a signal, so
    the backtest refuses to guess: only fully overlapping timestamps survive.
    """
    if not bars:
        raise BacktestError("no bars to backtest")
    stamps: set[datetime] | None = None
    for series in bars.values():
        symbol_stamps = {bar.timestamp for bar in series}
        stamps = symbol_stamps if stamps is None else (stamps & symbol_stamps)
    common = sorted(stamps or ())
    if not common:
        raise BacktestError(
            "the symbols share no common bar timestamps; check the data feed"
        )
    wanted = set(common)
    aligned: dict[str, list[Bar]] = {}
    for symbol, series in bars.items():
        by_stamp = {
            bar.timestamp: bar for bar in series if bar.timestamp in wanted
        }  # a repeated timestamp would silently misalign the symbols
        aligned[symbol] = [by_stamp[t] for t in common]
    return common, aligned


# -- the backtester -----------------------------------------------------


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        bars: dict[str, list[Bar]],
        *,
        starting_equity: float = 100_000.0,
        slippage_bps: float = 1.0,
        commission_per_share: float = 0.0,
        fill: FillMode = "next_open",
        allow_fractional: bool = False,
        benchmark: str | None = None,
    ) -> None:
        self.strategy = strategy
        self.timestamps, self.bars = align_bars(bars)
        self.starting_equity = starting_equity
        self.slippage_bps = slippage_bps
        self.commission_per_share = commission_per_share
        self.fill = fill
        self.allow_fractional = allow_fractional
        self.benchmark = benchmark

    # -- fills ----------------------------------------------------------

    def _fill_price(self, request: OrderRequest, index: int) -> float | None:
        """Modeled execution price, or None when there is no bar to fill on."""
        series = self.bars[request.symbol]
        if self.fill == "close":
            base = series[index].close
        else:
            if index + 1 >= len(series):
                return None  # signal on the final bar: nothing left to fill against
            base = series[index + 1].open
        drift = self.slippage_bps / 10_000.0
        return base * (1 + drift) if request.side is OrderSide.BUY else base * (1 - drift)

    def _execute(
        self, portfolio: SimPortfolio, orders: Iterable[OrderRequest], index: int
    ) -> list[Fill]:
        fills: list[Fill] = []
        for request in orders:
            price = self._fill_price(request, index)
            if price is None:
                log.debug("no fill bar for %s; dropping the order", request)
                continue
            fill = Fill(
                timestamp=self.timestamps[index],
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                price=price,
                commission=self.commission_per_share * request.qty,
                intent=request.intent,
            )
            portfolio.apply(fill)
            fills.append(fill)
        return fills

    # -- main loop ------------------------------------------------------

    def run(self) -> BacktestResult:
        portfolio = SimPortfolio(self.starting_equity)
        result = BacktestResult(
            strategy=self.strategy.name,
            timeframe=self.strategy.timeframe,
            symbols=list(self.strategy.symbols()),
            starting_equity=self.starting_equity,
        )

        open_trade: dict | None = None
        warmup = 0
        counting_warmup = True

        for index, stamp in enumerate(self.timestamps):
            closes = {
                symbol: series[index].close for symbol, series in self.bars.items()
            }
            equity = portfolio.equity(closes)
            positions = portfolio.positions(closes)

            snapshot = MarketSnapshot(
                as_of=stamp,
                bars={symbol: series[: index + 1] for symbol, series in self.bars.items()},
            )
            ctx = StrategyContext(
                account=Account(equity=equity, cash=portfolio.cash, buying_power=equity * 2),
                positions=positions,
                snapshot=snapshot,
            )
            decision = self.strategy.evaluate(ctx)

            if decision.action is Action.SKIP:
                if counting_warmup:
                    warmup = index + 1
                continue
            counting_warmup = False
            result.decisions.append((stamp, decision))
            result.equity_curve.append((stamp, equity))

            # Mirror the live engine: holding means holding, not re-sizing.
            if (
                decision.action is Action.MAINTAIN
                and not self.strategy.rebalance_on_maintain
            ):
                if open_trade is not None:
                    open_trade["bars"] += 1
                continue

            orders = plan_orders(
                decision.targets,
                positions,
                closes,
                equity,
                allow_fractional=self.allow_fractional,
            )
            fills = self._execute(portfolio, orders, index)
            result.fills.extend(fills)

            was_flat = open_trade is None
            now_flat = portfolio.is_flat

            if was_flat and not now_flat:
                open_trade = {
                    "at": stamp,
                    "equity": equity,
                    "z": decision.metrics.get("z"),
                    "side": _side_label(portfolio.qty, self.strategy.symbols()),
                    "bars": 0,
                }
            elif not was_flat and now_flat:
                exit_equity = portfolio.equity(closes)
                result.trades.append(
                    Trade(
                        entry_at=open_trade["at"],
                        exit_at=stamp,
                        side=open_trade["side"],
                        entry_equity=open_trade["equity"],
                        exit_equity=exit_equity,
                        entry_z=open_trade["z"],
                        exit_z=decision.metrics.get("z"),
                        exit_action=decision.action.value,
                        bars_held=open_trade["bars"] + 1,
                    )
                )
                open_trade = None
            elif open_trade is not None:
                open_trade["bars"] += 1

        result.warmup_bars = warmup
        if not result.equity_curve:
            raise BacktestError(
                f"the strategy never had enough history: only {len(self.timestamps)} "
                f"aligned bars were available"
            )
        # End the curve on terminal equity rather than the final pre-trade mark.
        last_closes = {s: series[-1].close for s, series in self.bars.items()}
        final_point = (self.timestamps[-1], portfolio.equity(last_closes))
        if result.equity_curve[-1][0] == final_point[0]:
            result.equity_curve[-1] = final_point
        else:
            result.equity_curve.append(final_point)
        result.benchmark_symbol = self.benchmark
        if self.benchmark and self.benchmark in self.bars:
            result.benchmark_curve = self._buy_and_hold(self.benchmark, warmup)
        return result

    def _buy_and_hold(self, symbol: str, warmup: int) -> list[tuple[datetime, float]]:
        """Equity curve for putting the whole account into one symbol at warmup."""
        series = self.bars[symbol]
        if warmup >= len(series):
            return []
        entry = series[warmup].close
        if entry <= 0:
            return []
        shares = self.starting_equity / entry
        return [(bar.timestamp, shares * bar.close) for bar in series[warmup:]]


def _side_label(qty: dict[str, float], symbols: list[str]) -> str:
    """Name the position: for a two-leg strategy, which way the spread leans."""
    if len(symbols) == 2:
        first = qty.get(symbols[0], 0.0)
        if first > 0:
            return "long_spread"
        if first < 0:
            return "short_spread"
    net = sum(qty.values())
    return "long" if net > 0 else "short" if net < 0 else "flat"


# -- statistics ---------------------------------------------------------


def max_drawdown(curve: list[tuple[datetime, float]]) -> tuple[float, datetime | None]:
    """Deepest peak-to-trough fall as a fraction, and when it bottomed."""
    peak = -math.inf
    worst = 0.0
    worst_at: datetime | None = None
    for stamp, value in curve:
        peak = max(peak, value)
        if peak > 0:
            drawdown = value / peak - 1
            if drawdown < worst:
                worst, worst_at = drawdown, stamp
    return worst, worst_at


def compute_stats(result: BacktestResult) -> dict[str, float]:
    curve = result.equity_curve
    values = [value for _, value in curve]
    initial, final = result.starting_equity, values[-1]

    returns = [
        values[i] / values[i - 1] - 1
        for i in range(1, len(values))
        if values[i - 1] != 0
    ]
    ann = periods_per_year(result.timeframe)
    if len(returns) > 1 and statistics.pstdev(returns) > 0:
        sharpe = statistics.fmean(returns) / statistics.stdev(returns) * math.sqrt(ann)
        volatility = statistics.stdev(returns) * math.sqrt(ann)
    else:
        sharpe = 0.0
        volatility = 0.0

    years = 0.0
    if result.start and result.end:
        years = (result.end - result.start).days / 365.25
    total_return = final / initial - 1 if initial else 0.0
    cagr = ((final / initial) ** (1 / years) - 1) if years > 0.05 and initial > 0 and final > 0 else 0.0

    drawdown, _ = max_drawdown(curve)
    wins = [t for t in result.trades if t.won]
    losses = [t for t in result.trades if not t.won]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)

    # Exposure: share of evaluated bars spent holding something.
    held_bars = sum(t.bars_held for t in result.trades)
    evaluated = max(len(result.decisions), 1)

    stats = {
        "starting_equity": initial,
        "final_equity": final,
        "total_return": total_return,
        "cagr": cagr,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": drawdown,
        "trades": float(len(result.trades)),
        "win_rate": len(wins) / len(result.trades) if result.trades else 0.0,
        "avg_win": statistics.fmean([t.pnl for t in wins]) if wins else 0.0,
        "avg_loss": statistics.fmean([t.pnl for t in losses]) if losses else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else math.inf if gross_win else 0.0,
        "avg_bars_held": statistics.fmean([t.bars_held for t in result.trades]) if result.trades else 0.0,
        "exposure": held_bars / evaluated,
        "bars": float(len(result.decisions)),
        "years": years,
        "commission_paid": sum(f.commission for f in result.fills),
        "stops": float(sum(1 for t in result.trades if t.exit_action == "stop")),
    }
    if result.benchmark_curve:
        bench_initial = result.benchmark_curve[0][1]
        bench_final = result.benchmark_curve[-1][1]
        stats["benchmark_return"] = bench_final / bench_initial - 1 if bench_initial else 0.0
        stats["benchmark_max_drawdown"] = max_drawdown(result.benchmark_curve)[0]
    return stats
