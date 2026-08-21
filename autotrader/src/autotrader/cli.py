"""`trader` -- the command line surface."""

from __future__ import annotations

import csv
import json
import logging
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .backtest import BacktestError, BacktestResult, Backtester
from .brokers import available_brokers, build_broker
from .brokers.base import Broker, BrokerError
from .config import Config, ConfigError, EXAMPLE_CONFIG, load_config, parse_duration
from .engine import Engine
from .logging_setup import setup_logging
from .models import Action, RunReport
from .storage import Store
from .strategies import available_strategies, build_strategy
from .strategies.base import Strategy, StrategyError

console = Console()
log = logging.getLogger("autotrader.cli")

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Automated trading CLI. Defaults to GLD/GDX pair trading on an Alpaca paper account.",
)

ACTION_STYLE = {
    Action.ENTER: "bold green",
    Action.EXIT: "bold cyan",
    Action.STOP: "bold red",
    Action.MAINTAIN: "yellow",
    Action.NONE: "dim",
    Action.SKIP: "dim italic",
}


class AppState:
    def __init__(self, config_path: Path | None, log_level: str | None) -> None:
        self.config_path = config_path
        self.log_level = log_level
        self._config: Config | None = None

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = load_config(self.config_path)
            setup_logging(self._config.logging, level=self.log_level)
        return self._config


def _state(ctx: typer.Context) -> AppState:
    return ctx.ensure_object(AppState)


def _fail(message: str) -> None:
    console.print(f"[bold red]error:[/] {message}")
    raise typer.Exit(code=1)


def _build(ctx: typer.Context) -> tuple[Config, Broker, Strategy, Store, Engine]:
    state = _state(ctx)
    try:
        config = state.config
        broker = build_broker(config)
        strategy = build_strategy(config.strategy.name, config.strategy.params)
    except (ConfigError, BrokerError, StrategyError) as exc:
        _fail(str(exc))
    store = Store(config.storage.resolved())
    return config, broker, strategy, store, Engine(config, broker, strategy, store)


@app.callback()
def main_callback(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config.toml (default: ./config.toml, then ~/.autotrader/config.toml)."
    ),
    log_level: Optional[str] = typer.Option(
        None, "--log-level", help="Override console log level (DEBUG/INFO/WARNING)."
    ),
) -> None:
    ctx.obj = AppState(config_path=config, log_level=log_level)


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"autotrader {__version__}")


@app.command()
def init(
    path: Path = typer.Option(Path("config.toml"), "--path", "-p", help="Where to write the config."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Write a starter config.toml you can edit."""
    target = path.expanduser()
    if target.exists() and not force:
        _fail(f"{target} already exists (use --force to overwrite)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(EXAMPLE_CONFIG)
    console.print(f"[green]wrote[/] {target}")
    console.print(
        "Next: copy [cyan].env.example[/] to [cyan].env[/] and add your Alpaca "
        "paper keys, then run [cyan]trader doctor[/]."
    )


@app.command(name="list")
def list_components() -> None:
    """List the brokers and strategies this build knows about."""
    table = Table(title="registered components", header_style="bold")
    table.add_column("kind")
    table.add_column("name")
    for name in available_brokers():
        implemented = "alpaca" == name
        table.add_row("broker", f"{name}" if implemented else f"[dim]{name} (planned)[/]")
    for name in available_strategies():
        table.add_row("strategy", name)
    console.print(table)


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check config, credentials, connectivity, data, and shortability."""
    config, broker, strategy, store, _ = _build(ctx)
    console.print(
        Panel(
            f"config: {config.source_path or '[dim]built-in defaults[/]'}\n"
            f"broker: {config.broker.name} ({'paper' if config.broker.paper else '[bold red]LIVE[/]'}), "
            f"feed={config.broker.data_feed}\n"
            f"strategy: {strategy.describe()}\n"
            f"storage: {config.storage.resolved()}",
            title="setup",
        )
    )
    checks: list[tuple[str, bool, str]] = []
    try:
        account = broker.get_account()
        checks.append(("credentials + account", True, f"equity ${account.equity:,.2f}"))
    except BrokerError as exc:
        checks.append(("credentials + account", False, str(exc)))
        account = None
    try:
        status = broker.get_market_status()
        checks.append(("market clock", True, status.detail))
    except BrokerError as exc:
        checks.append(("market clock", False, str(exc)))
    try:
        bars = broker.get_bars(strategy.symbols(), strategy.timeframe, strategy.required_bars)
        counts = ", ".join(f"{sym}={len(series)}" for sym, series in bars.items())
        enough = all(len(series) >= getattr(strategy, "lookback", 1) for series in bars.values())
        checks.append((f"{strategy.timeframe} bars", enough, counts))
    except BrokerError as exc:
        checks.append((f"{strategy.timeframe} bars", False, str(exc)))
    for symbol in strategy.symbols():
        try:
            shortable = broker.is_shortable(symbol)
            checks.append((f"{symbol} shortable", shortable, "yes" if shortable else "NO -- the short leg will be rejected"))
        except BrokerError as exc:
            checks.append((f"{symbol} shortable", False, str(exc)))

    table = Table(header_style="bold")
    table.add_column("check")
    table.add_column("ok", justify="center")
    table.add_column("detail", overflow="fold")
    for name, ok, detail in checks:
        table.add_row(name, "[green]✓[/]" if ok else "[red]✗[/]", detail)
    console.print(table)
    store.close()
    if not all(ok for _, ok, _ in checks):
        raise typer.Exit(code=1)


@app.command()
def status(ctx: typer.Context) -> None:
    """Account, market clock, open positions, and the current signal."""
    config, broker, strategy, store, engine = _build(ctx)
    try:
        account = broker.get_account()
        market = broker.get_market_status()
        positions = broker.get_positions()
    except BrokerError as exc:
        _fail(str(exc))

    console.print(
        Panel(
            f"equity [bold]${account.equity:,.2f}[/]   cash ${account.cash:,.2f}   "
            f"buying power ${account.buying_power:,.2f}\n"
            f"market: {'[green]OPEN[/]' if market.is_open else '[yellow]CLOSED[/]'} — {market.detail}\n"
            f"{strategy.describe()}",
            title=f"{config.broker.name} {'paper' if config.broker.paper else 'LIVE'}",
        )
    )
    _print_positions(positions, strategy.symbols())
    _print_signal(engine, store)
    store.close()


@app.command()
def positions(ctx: typer.Context) -> None:
    """Show open positions at the broker."""
    _, broker, strategy, store, _ = _build(ctx)
    try:
        _print_positions(broker.get_positions(), strategy.symbols())
    except BrokerError as exc:
        _fail(str(exc))
    store.close()


@app.command()
def signal(ctx: typer.Context) -> None:
    """Evaluate the strategy and show the signal without trading."""
    _, _, _, store, engine = _build(ctx)
    _print_signal(engine, store, record=True)
    store.close()


@app.command()
def run(
    ctx: typer.Context,
    once: bool = typer.Option(True, "--once/--loop", help="Evaluate once and exit, or poll on an interval."),
    dry_run: bool = typer.Option(
        None, "--dry-run/--execute", help="Override the config's execute setting for this run."
    ),
    interval: Optional[str] = typer.Option(None, "--interval", "-i", help="Loop interval, e.g. '15m'. Implies --loop."),
    ignore_market_hours: bool = typer.Option(
        False, "--ignore-market-hours", help="Bypass the market-open guardrail (orders will queue for the next session)."
    ),
) -> None:
    """Evaluate the strategy and place the resulting orders."""
    config, broker, strategy, store, engine = _build(ctx)
    if interval:
        once = False
        try:
            config.engine.poll_interval = parse_duration(interval)
        except ConfigError as exc:
            _fail(str(exc))

    execute = config.engine.execute if dry_run is None else not dry_run
    if execute and not config.broker.paper:
        console.print("[bold red]WARNING: this is a LIVE account, not paper.[/]")
        if not typer.confirm("Submit real orders?", default=False):
            raise typer.Exit(code=1)

    def one_pass() -> RunReport:
        report = engine.run_once(dry_run=dry_run, ignore_market_hours=ignore_market_hours)
        _render_report(report, execute_default=config.engine.execute)
        return report

    if once:
        report = one_pass()
        store.close()
        raise typer.Exit(code=1 if report.had_errors else 0)

    seconds = config.engine.poll_interval
    console.print(f"[dim]looping every {seconds}s — Ctrl-C to stop[/]")
    try:
        while True:
            try:
                one_pass()
            except BrokerError as exc:
                log.error("broker error: %s", exc)
            except Exception:  # noqa: BLE001 - a loop must survive one bad pass
                log.exception("unexpected error during evaluation")
            time.sleep(seconds)
    except KeyboardInterrupt:
        console.print("\n[dim]stopped[/]")
    finally:
        store.close()


@app.command()
def close(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be closed."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Flatten every position this strategy trades, ignoring the signal."""
    config, broker, strategy, store, engine = _build(ctx)
    if not dry_run and not yes:
        symbols = ", ".join(strategy.symbols())
        if not typer.confirm(f"Close all {symbols} positions?", default=False):
            raise typer.Exit(code=1)
    report = engine.flatten(dry_run=dry_run)
    _render_report(report, execute_default=config.engine.execute)
    store.close()


@app.command()
def history(
    ctx: typer.Context,
    limit: int = typer.Option(15, "--limit", "-n", help="Rows to show."),
    orders: bool = typer.Option(False, "--orders", help="Show orders instead of signals."),
    live_only: bool = typer.Option(False, "--live-only", help="Exclude dry-run orders."),
) -> None:
    """Show recorded signals or orders from the local database."""
    state = _state(ctx)
    config = state.config
    store = Store(config.storage.resolved())
    if orders:
        rows = store.recent_orders(limit=limit, include_dry_run=not live_only)
        table = Table(title="recent orders", header_style="bold")
        for column in ("when", "symbol", "side", "qty", "status", "filled", "mode", "note"):
            table.add_column(column, overflow="fold")
        for row in rows:
            table.add_row(
                _short_ts(row["ts"]),
                row["symbol"],
                row["side"],
                f"{row['qty']:g}",
                row["error"] and f"[red]{row['status']}[/]" or row["status"],
                f"{row['filled_qty'] or 0:g}"
                + (f" @ ${row['filled_avg_price']:.2f}" if row["filled_avg_price"] else ""),
                "dry-run" if row["dry_run"] else "live",
                row["error"] or row["intent"] or "",
            )
    else:
        rows = store.recent_signals(limit=limit)
        table = Table(title="recent signals", header_style="bold")
        for column in ("when", "strategy", "action", "z", "reason"):
            table.add_column(column, overflow="fold")
        for row in rows:
            metrics = json.loads(row["metrics"] or "{}")
            z = metrics.get("z")
            action = row["action"]
            table.add_row(
                _short_ts(row["ts"]),
                row["strategy"],
                f"[{ACTION_STYLE.get(Action(action), '')}]{action}[/]",
                f"{z:+.2f}" if isinstance(z, (int, float)) else "—",
                row["reason"] or "",
            )
    if not rows:
        console.print("[dim]nothing recorded yet[/]")
    else:
        console.print(table)
    store.close()


@app.command()
def backtest(
    ctx: typer.Context,
    bars: int = typer.Option(750, "--bars", "-b", help="Bars to fetch (about 3 years of daily)."),
    start: Optional[str] = typer.Option(None, "--start", help="Start date, YYYY-MM-DD. Overrides --bars."),
    end: Optional[str] = typer.Option(None, "--end", help="End date, YYYY-MM-DD. Defaults to now."),
    equity: float = typer.Option(100_000.0, "--equity", help="Starting equity."),
    slippage_bps: float = typer.Option(1.0, "--slippage-bps", help="Slippage per fill, in basis points."),
    commission: float = typer.Option(0.0, "--commission", help="Commission per share."),
    fill: str = typer.Option(
        "next_open", "--fill", help="Fill at the next bar's open (honest) or this bar's close (matches a pre-close cron)."
    ),
    benchmark: Optional[str] = typer.Option(
        None, "--benchmark", help="Symbol to buy and hold for comparison (default: the strategy's first symbol)."
    ),
    param: list[str] = typer.Option(
        [], "--param", "-p", help="Override a strategy param for this run, e.g. -p entry_z=2.5. Repeatable."
    ),
    show_trades: bool = typer.Option(True, "--trades/--no-trades", help="List the round trips."),
    csv_dir: Optional[Path] = typer.Option(None, "--csv", help="Write equity.csv, trades.csv, and signals.csv here."),
) -> None:
    """Replay the strategy over historical bars using the live decision code."""
    state = _state(ctx)
    try:
        config = state.config
        params = dict(config.strategy.params)
        params.update(_parse_overrides(param))
        strategy = build_strategy(config.strategy.name, params)
        broker = build_broker(config)
    except (ConfigError, BrokerError, StrategyError) as exc:
        _fail(str(exc))

    if fill not in ("next_open", "close"):
        _fail("--fill must be 'next_open' or 'close'")

    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    limit = bars if start_dt is None else 100_000

    with console.status("fetching history…"):
        try:
            history = broker.get_bars(
                strategy.symbols(), strategy.timeframe, limit, start_dt, end_dt
            )
        except BrokerError as exc:
            _fail(str(exc))

    try:
        result = Backtester(
            strategy,
            history,
            starting_equity=equity,
            slippage_bps=slippage_bps,
            commission_per_share=commission,
            fill=fill,
            allow_fractional=config.engine.guardrails.allow_fractional,
            benchmark=benchmark or strategy.symbols()[0],
        ).run()
    except (BacktestError, StrategyError) as exc:
        _fail(str(exc))

    _render_backtest(result, strategy, fill, slippage_bps, show_trades)
    if csv_dir:
        _write_backtest_csv(result, csv_dir)
        console.print(f"[green]wrote[/] {csv_dir}/equity.csv, trades.csv, signals.csv")


def _parse_overrides(pairs: list[str]) -> dict:
    """'entry_z=2.5' -> {'entry_z': 2.5}, keeping strings as strings."""
    out: dict[str, object] = {}
    for item in pairs:
        if "=" not in item:
            _fail(f"--param needs KEY=VALUE, got {item!r}")
        key, _, raw = item.partition("=")
        value: object = raw
        try:
            value = int(raw)
        except ValueError:
            try:
                value = float(raw)
            except ValueError:
                pass
        out[key.strip()] = value
    return out


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail(f"dates must look like YYYY-MM-DD, got {value!r}")


SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: int = 64) -> str:
    """A one-line equity curve. Buckets down to `width` columns by average."""
    if len(values) < 2:
        return ""
    if len(values) > width:
        size = len(values) / width
        values = [
            statistics.fmean(values[int(i * size) : max(int((i + 1) * size), int(i * size) + 1)])
            for i in range(width)
        ]
    low, high = min(values), max(values)
    if high == low:
        return SPARK_BLOCKS[0] * len(values)
    span = high - low
    return "".join(
        SPARK_BLOCKS[min(int((v - low) / span * len(SPARK_BLOCKS)), len(SPARK_BLOCKS) - 1)]
        for v in values
    )


def _pct(value: float) -> str:
    return f"{value * 100:+.2f}%"


def _render_backtest(
    result: BacktestResult, strategy: Strategy, fill: str, slippage_bps: float, show_trades: bool
) -> None:
    stats = result.stats()
    period = f"{result.start:%Y-%m-%d} → {result.end:%Y-%m-%d}" if result.start else "—"
    console.print(
        Panel(
            f"{strategy.describe()}\n"
            f"{period}  ·  {int(stats['bars'])} bars evaluated  ·  "
            f"{result.warmup_bars} warmup  ·  fill at {fill}, {slippage_bps:g}bp slippage",
            title="backtest",
        )
    )

    curve = [value for _, value in result.equity_curve]
    spark = sparkline(curve)
    if spark:
        colour = "green" if curve[-1] >= curve[0] else "red"
        console.print(f"[{colour}]{spark}[/]  ${curve[0]:,.0f} → ${curve[-1]:,.0f}")

    left = Table.grid(padding=(0, 2))
    left.add_column(style="dim")
    left.add_column(justify="right")
    right = Table.grid(padding=(0, 2))
    right.add_column(style="dim")
    right.add_column(justify="right")

    total_style = "green" if stats["total_return"] >= 0 else "red"
    left.add_row("total return", f"[{total_style}]{_pct(stats['total_return'])}[/]")
    # Annualizing a few weeks of data produces a confident-looking lie.
    left.add_row("CAGR", _pct(stats["cagr"]) if stats["years"] >= 0.5 else "—")
    left.add_row("volatility (ann.)", f"{stats['volatility'] * 100:.2f}%")
    left.add_row("Sharpe (ann.)", f"{stats['sharpe']:.2f}")
    left.add_row("max drawdown", f"[red]{_pct(stats['max_drawdown'])}[/]")
    left.add_row("final equity", f"${stats['final_equity']:,.2f}")

    right.add_row("round trips", f"{int(stats['trades'])}")
    right.add_row("win rate", f"{stats['win_rate'] * 100:.1f}%")
    right.add_row("avg win / loss", f"${stats['avg_win']:,.0f} / ${stats['avg_loss']:,.0f}")
    profit_factor = stats["profit_factor"]
    right.add_row("profit factor", "∞" if profit_factor == float("inf") else f"{profit_factor:.2f}")
    right.add_row("avg bars held", f"{stats['avg_bars_held']:.1f}")
    right.add_row("stopped out", f"{int(stats['stops'])}")
    right.add_row("time in market", f"{stats['exposure'] * 100:.1f}%")

    summary = Table.grid(padding=(0, 6))
    summary.add_column()
    summary.add_column()
    summary.add_row(left, right)
    console.print(summary)

    if "benchmark_return" in stats:
        console.print(
            f"[dim]buy & hold {result.benchmark_symbol}: {_pct(stats['benchmark_return'])} "
            f"with a {_pct(stats['benchmark_max_drawdown'])} drawdown[/]"
        )
    if stats["commission_paid"]:
        console.print(f"[dim]commission paid: ${stats['commission_paid']:,.2f}[/]")

    if int(stats["trades"]) == 0:
        console.print(
            "[yellow]no round trips[/] — the entry threshold was never crossed, or the "
            "window was too short. Try a longer period or a lower entry_z."
        )
        return

    if show_trades:
        table = Table(title="round trips", header_style="bold")
        for column in ("entry", "exit", "side", "z in", "z out", "why", "bars", "P&L", "return"):
            table.add_column(column, justify="right" if column not in ("side", "why") else "left")
        for trade in result.trades:
            style = "green" if trade.won else "red"
            table.add_row(
                f"{trade.entry_at:%Y-%m-%d}",
                f"{trade.exit_at:%Y-%m-%d}",
                trade.side.replace("_spread", ""),
                f"{trade.entry_z:+.2f}" if trade.entry_z is not None else "—",
                f"{trade.exit_z:+.2f}" if trade.exit_z is not None else "—",
                trade.exit_action,
                str(trade.bars_held),
                f"[{style}]${trade.pnl:,.0f}[/]",
                f"[{style}]{_pct(trade.return_pct)}[/]",
            )
        console.print(table)


def _write_backtest_csv(result: BacktestResult, directory: Path) -> None:
    directory = directory.expanduser()
    directory.mkdir(parents=True, exist_ok=True)

    with (directory / "equity.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "equity"])
        writer.writerows([[ts.isoformat(), f"{value:.2f}"] for ts, value in result.equity_curve])

    with (directory / "trades.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["entry_at", "exit_at", "side", "entry_z", "exit_z", "exit_action", "bars_held", "pnl", "return"]
        )
        for t in result.trades:
            writer.writerow(
                [
                    t.entry_at.isoformat(),
                    t.exit_at.isoformat(),
                    t.side,
                    "" if t.entry_z is None else f"{t.entry_z:.4f}",
                    "" if t.exit_z is None else f"{t.exit_z:.4f}",
                    t.exit_action,
                    t.bars_held,
                    f"{t.pnl:.2f}",
                    f"{t.return_pct:.6f}",
                ]
            )

    with (directory / "signals.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "action", "z", "reason"])
        for ts, decision in result.decisions:
            writer.writerow(
                [
                    ts.isoformat(),
                    decision.action.value,
                    f"{decision.metrics.get('z', float('nan')):.4f}",
                    decision.reason,
                ]
            )

@app.command()
def gui(
    ctx: typer.Context,
    port: int = typer.Option(8787, "--port", "-p", help="Port to serve the dashboard on."),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Bind address. Leave as loopback unless you know why not."
    ),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the dashboard in your browser automatically."
    ),
) -> None:
    """Serve the local dashboard in your browser."""
    try:
        from .web import TradingService, serve
    except ImportError:  # pragma: no cover - only when the extra is missing
        _fail(
            "the dashboard needs fastapi and uvicorn: "
            'pip install -e ".[gui]" (or re-run setup.sh / setup.bat)'
        )

    config, broker, strategy, store, _ = _build(ctx)
    if host != "127.0.0.1":
        console.print(
            f"[bold red]WARNING:[/] binding to {host} exposes a trading dashboard "
            "beyond this machine."
        )
        if not typer.confirm("Continue?", default=False):
            raise typer.Exit(code=1)
    if not config.broker.paper:
        console.print("[bold red]WARNING: this dashboard is wired to a LIVE account.[/]")
        if not typer.confirm("Continue?", default=False):
            raise typer.Exit(code=1)

    service = TradingService(config, broker, strategy, store)
    try:
        serve(service, host=host, port=port, open_browser=open_browser)
    except OSError as exc:
        _fail(f"could not start the server on {host}:{port} ({exc}). Try --port 8788.")


# -- rendering helpers --------------------------------------------------


def _short_ts(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M")
    except ValueError:
        return value[:16]


def _print_positions(positions: dict, symbols: list[str]) -> None:
    relevant = {s: positions[s] for s in symbols if s in positions}
    other = {s: p for s, p in positions.items() if s not in symbols}
    if not positions:
        console.print("[dim]no open positions[/]")
        return
    table = Table(title="positions", header_style="bold")
    for column in ("symbol", "side", "qty", "avg entry", "market value"):
        table.add_column(column, justify="right" if column != "symbol" else "left")
    for source, dim in ((relevant, False), (other, True)):
        for symbol, pos in source.items():
            style = "dim" if dim else ("green" if pos.qty > 0 else "red")
            table.add_row(
                Text(symbol, style=style),
                pos.side,
                f"{pos.qty:g}",
                f"${pos.avg_entry_price:,.2f}",
                f"${pos.market_value:,.2f}",
            )
    console.print(table)


def _print_signal(engine: Engine, store: Store, record: bool = False) -> None:
    """Evaluate without trading and print the signal."""
    saved_execute = engine.config.engine.execute
    saved_store = engine.store
    engine.config.engine.execute = False
    if not record:
        engine.store = None
    try:
        report = engine.run_once(dry_run=True)
    except (BrokerError, StrategyError) as exc:
        _fail(str(exc))
    finally:
        engine.config.engine.execute = saved_execute
        engine.store = saved_store
    _render_decision(report)
    if report.orders:
        console.print("[dim]orders this signal would produce:[/]")
        _print_orders(report)


def _render_decision(report: RunReport) -> None:
    decision = report.decision
    if decision is None:
        console.print("[dim]no decision produced[/]")
        return
    style = ACTION_STYLE.get(decision.action, "")
    lines = [f"[{style}]{decision.action.value.upper()}[/] — {decision.reason}"]
    metrics = decision.metrics
    if "z" in metrics:
        lines.append(
            f"z=[bold]{metrics['z']:+.3f}[/]  spread={metrics['spread']:+.5f}  "
            f"mean={metrics['spread_mean']:+.5f}  sd={metrics['spread_stdev']:.5f}"
        )
    if "price_a" in metrics:
        lines.append(
            f"prices: ${metrics['price_a']:,.2f} / ${metrics['price_b']:,.2f}  "
            f"ratio={metrics.get('ratio', 0):.4f}  bars={int(metrics.get('bars_used', 0))}"
        )
    if decision.targets:
        targets = "  ".join(f"{s}={w:+.1%}" for s, w in decision.targets.items())
        lines.append(f"targets: {targets}")
    console.print(Panel("\n".join(lines), title=f"signal — {decision.strategy}"))


def _print_orders(report: RunReport) -> None:
    table = Table(header_style="bold")
    for column in ("order", "why", "status"):
        table.add_column(column, overflow="fold")
    results = {id(r.request): r for r in report.results}
    for request in report.orders:
        result = results.get(id(request))
        if result is None:
            status = "[dim]not submitted[/]"
        elif result.ok:
            fill = ""
            if result.filled_qty:
                fill = f" {result.filled_qty:g}"
                if result.filled_avg_price:
                    fill += f" @ ${result.filled_avg_price:,.2f}"
            status = f"[green]{result.status}[/]{fill}"
        else:
            status = f"[red]{result.status}: {result.error}[/]"
        table.add_row(str(request), request.intent, status)
    console.print(table)


def _render_report(report: RunReport, execute_default: bool) -> None:
    _render_decision(report)
    if report.skipped_reason:
        console.print(f"[yellow]no action:[/] {report.skipped_reason}")
        return
    if not report.orders:
        console.print("[dim]portfolio already matches the target; nothing to do[/]")
        return
    mode = "[green]LIVE (paper account)[/]" if report.executed else "[yellow]DRY RUN — nothing submitted[/]"
    console.print(f"{mode}")
    _print_orders(report)
    if report.had_errors:
        console.print("[bold red]one or more orders failed; see above[/]")


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
