# autotrader

A small CLI automated trading platform. Version 1 trades one strategy — a
GLD/GDX z-score pair — against an **Alpaca paper account**. Brokers and
strategies sit behind interfaces, so adding Robinhood, Tastytrade, or a second
strategy is a new file rather than a rewrite.

```
trader backtest        # how would this have done?
trader signal          # what does the strategy think right now?
trader run --once      # evaluate and place the resulting orders
trader run --loop      # keep evaluating on an interval
trader history         # why did it do that?
```

## Install it on your laptop

**Windows** — double-click `setup.bat` (or run it from a Command Prompt). It
finds Python, builds a virtual environment, installs everything, prompts for
your Alpaca paper keys, and runs a connection check. After that, use
`trader.bat`:

```bat
trader.bat status
trader.bat backtest
trader.bat run --once --dry-run
```

**macOS / Linux** — the same thing:

```bash
./setup.sh
./trader.sh status
```

Setup needs **Python 3.11 or newer** (the config loader uses `tomllib`). On
Windows, install it from [python.org](https://www.python.org/downloads/windows/)
and tick *"Add python.exe to PATH"*.

Your credentials and config are written to `%USERPROFILE%\.autotrader\`
(Windows) or `~/.autotrader/` (macOS/Linux), not into the project folder, so
the CLI works from any directory:

```
~/.autotrader/.env            APCA_API_KEY_ID and APCA_API_SECRET_KEY
~/.autotrader/config.toml     strategy and guardrail settings
~/.autotrader/autotrader.db   signal and order history
~/.autotrader/autotrader.log  rotating log
```

To change credentials later, delete `.env` and re-run setup. A `.env` in the
project folder still wins over the one in your home directory, which is handy
for testing a second account.

### A standalone .exe

`setup.bat` already produces `.venv\Scripts\trader.exe`, but that one needs
the virtual environment beside it. For a single file you can copy anywhere,
with no Python installed at all:

```bat
scripts\build-exe.bat        REM produces dist\trader.exe (~45 MB)
```

macOS/Linux: `./scripts/build-exe.sh`. The binary reads the same
`~/.autotrader/` files, so it works from any folder. Build it on the machine
you intend to run it on — PyInstaller does not cross-compile, so a Linux build
will not produce a Windows executable.

## Manual install

If you would rather not use the scripts:

```bash
cd autotrader
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env          # add your Alpaca *paper* keys
trader init                   # writes config.toml
trader doctor                 # verifies keys, clock, data, shortability
trader backtest               # replay it over history first
trader signal                 # look before you trade
trader run --once --dry-run   # see the orders it would send
trader run --once             # send them
```

Paper API keys come from the [Alpaca paper dashboard](https://app.alpaca.markets/paper/dashboard/overview)
under **API Keys**. The key ID starts with `PK`; the secret is shown only once,
when you create the pair. `.env` and `config.toml` are both gitignored.

You do **not** need to set `base_url` — `paper = true` already selects the paper
endpoint. If you do set it, either `https://paper-api.alpaca.markets` or the
`.../v2` form the dashboard displays will work; the version suffix is stripped,
because the SDK appends its own and would otherwise request `/v2/v2/...`.

## The default strategy

`pair_zscore` trades the log price ratio of two correlated instruments — by
default GLD (spot gold) against GDX (gold miners), which share a driver but
drift apart on miner-specific risk.

```
spread_t = log(GLD_t) - log(GDX_t)
z_t      = (spread_t - mean(spread, 60)) / stdev(spread, 60)
```

| z | position | meaning |
|---|---|---|
| `z >= +2.0` | short GLD / long GDX | GLD is rich relative to GDX |
| `z <= -2.0` | long GLD / short GDX | GLD is cheap relative to GDX |
| `abs(z) <= 0.5` | flat | reverted — take the trade off |
| `abs(z) >= 3.5` while positioned | flat | moved against us — stop out |
| `abs(z) >= 3.5` while flat | stay flat | the relationship may have broken; stand aside |

Each leg targets 10% of account equity, floored to whole shares. Evaluated on
daily bars.

Once a pair is on, it is **held, not rebalanced** — the engine will not top the
legs up as prices and equity drift, because that is a slow pyramid rather than a
hold. Set `rebalance_on_maintain = True` on a strategy that genuinely wants
continuous rebalancing.

## Commands

| command | what it does |
|---|---|
| `trader init` | write a starter `config.toml` |
| `trader doctor` | check credentials, market clock, bar availability, shortability |
| `trader backtest` | replay the strategy over historical bars |
| `trader status` | account, clock, positions, and the current signal |
| `trader signal` | evaluate and print the signal; never trades |
| `trader run --once` | evaluate once and place orders (cron-friendly) |
| `trader run --loop -i 15m` | evaluate on an interval until Ctrl-C |
| `trader run --once --dry-run` | print the orders without submitting them |
| `trader positions` | open positions at the broker |
| `trader close` | flatten every leg this strategy trades, ignoring the signal |
| `trader history` / `--orders` | recorded signals or orders from the local database |
| `trader list` | registered brokers and strategies |

On Windows every command above is `trader.bat <command>`; on macOS/Linux,
`./trader.sh <command>` (or plain `trader` inside an activated venv).

Global flags: `--config PATH`, `--log-level DEBUG`.

`run --once` exits non-zero if any order was rejected, so cron and CI can tell
that something went wrong.

## Configuration

`config.toml` (searched in `./config.toml`, then `~/.autotrader/config.toml`;
the setup scripts write the second one). Credentials never live here — they come
from the environment or a `.env`, searched in the same order.

```toml
[broker]
name = "alpaca"       # alpaca | robinhood (planned) | tastytrade (planned)
paper = true
data_feed = "iex"     # "iex" on free plans, "sip" if you subscribe
data_adjustment = "split"    # never "raw": an unadjusted split fakes a dislocation

[engine]
execute = true        # submit by default; `--dry-run` overrides per invocation
poll_interval = "15m"

[engine.guardrails]
require_market_open = true   # never trade outside regular hours
respect_calendar = true      # honor holidays and half-days
max_open_strategies = 1      # no pyramiding onto an open position
allow_fractional = false     # short legs must be whole shares anyway

[strategy]
name = "pair_zscore"

[strategy.params]
symbol_a = "GLD"
symbol_b = "GDX"
timeframe = "1Day"    # also "1Hour", "15Min"
lookback = 60
entry_z = 2.0
exit_z = 0.5
stop_z = 3.5
leg_weight = 0.10     # fraction of equity per leg
```

State lives in SQLite at `~/.autotrader/autotrader.db`: one row per evaluation,
with the signal, its metrics, the orders, and a position snapshot. Logs rotate
at `~/.autotrader/autotrader.log`.

## Backtesting

```bash
trader backtest                                  # ~3 years of daily bars
trader backtest --start 2020-01-01 --end 2024-12-31
trader backtest -p entry_z=2.5 -p lookback=90    # try other parameters
trader backtest --csv ./out                      # equity.csv, trades.csv, signals.csv
```

The backtest runs the **same** `Strategy.evaluate` and the same `plan_orders`
the live engine uses. It is a replay harness, not a second implementation of
the strategy — if the two ever disagreed, the backtest would be worthless.

```
╭───────────────────────────── backtest ─────────────────────────────╮
│ pair_zscore: GLD/GDX on 1Day, lookback=60, entry=±2.0, exit=±0.5   │
│ 2023-01-03 → 2026-08-19 · 892 bars evaluated · 59 warmup           │
╰────────────────────────────────────────────────────────────────────╯
▁▁▂▂▃▃▄▄▄▅▅▆▆▆▇▇█  $100,000 → $107,412
total return    +7.41%      round trips        14
CAGR            +2.05%      win rate        64.3%
Sharpe (ann.)     0.71      profit factor    1.83
max drawdown    -3.12%      time in market  31.4%
```

*(illustrative output — run it against your own data)*

What it models, and what it does not:

- **No lookahead.** At bar *i* the strategy sees bars `[0..i]` and nothing more.
  A test asserts this directly, because everything else is meaningless if it
  leaks.
- **Fills.** `--fill next_open` (default) executes at the *next* bar's open,
  which is the honest assumption for a signal computed on a close.
  `--fill close` executes at the signal bar's close instead — closer to what a
  15:45 cron actually gets, and slightly optimistic.
- **Costs.** `--slippage-bps` (default 1bp, applied against you on both sides)
  and `--commission` per share (default 0, matching Alpaca).
- **Warmup.** The first `lookback` bars fill the rolling window and are excluded
  from the results; `--bars 750` gives roughly three years of daily data, of
  which 60 are consumed.
- **Not modeled:** short borrow fees, dividends on the short leg, margin
  interest, buying-power limits, partial fills, and the possibility that a
  short was not available at all. All of these make real results worse than the
  backtest, and shorting GDX is exactly where they bite.
- The benchmark line is buy-and-hold of the first leg, for context only — a
  market-neutral pair is not really comparable to a directional hold.

The usual caveat applies with force here: a backtest of a strategy whose
parameters you tuned on the same data tells you very little. Change one
threshold, re-run, and you have already started overfitting.

## Scheduling

Daily bars only need one evaluation a day. Run it shortly before the close so
the last bar is meaningful:

```cron
# 15:45 America/New_York, weekdays
45 15 * * 1-5 cd /path/to/autotrader && .venv/bin/trader run --once >> cron.log 2>&1
```

On Windows, Task Scheduler does the same job: create a Basic Task, trigger it
daily at 3:45 PM, and point the action at `trader.bat` with the argument
`run --once` and the project folder as "Start in".

The market-hours guardrail makes a misfire harmless — outside regular hours it
records the signal and places nothing. For intraday timeframes use
`trader run --loop -i 15m` under systemd or launchd instead.

## Known limitations

Worth knowing before you trust it with anything:

- **Dollar-neutral is not risk-neutral.** GDX is roughly 2–3x as volatile as
  GLD, so equal notional legs leave the position dominated by miner risk. A
  beta- or vol-weighted sizing mode is the natural next step (see below).
- **Whole-share rounding.** Both legs floor toward zero, so the realized
  notional is slightly under target and never exactly matched. The engine logs
  the drift on every entry.
- **Paper shorting is simulated.** Alpaca's paper environment does not model
  borrow availability or hard-to-borrow fees. `trader doctor` checks the
  shortable flag, but live behavior can still differ.
- **The defaults are not fitted.** ±2.0 / 0.5 / 3.5 on a 60-bar window are
  conventional starting points. Run `trader backtest` before trusting them, and
  read the caveats in that section before trusting the backtest.
- **Leg fill risk.** The two legs are separate market orders. The engine
  sequences closes before opens and aborts the remaining orders if one is
  rejected, but a fill can still land at a worse price than the signal assumed.
- This is a personal hobby project, not investment advice.

## Extending it

**A new strategy** — subclass `Strategy`, return target weights, register it:

```python
# src/autotrader/strategies/my_strategy.py
class MyStrategy(Strategy):
    name = "my_strategy"

    def symbols(self) -> list[str]:
        return ["SPY"]

    def evaluate(self, ctx: StrategyContext) -> Decision:
        return Decision(strategy=self.name, action=Action.ENTER,
                        targets={"SPY": 0.25}, reason="because", metrics={})
```

Add it to `REGISTRY` in `strategies/__init__.py` and set `strategy.name` in
config. Strategies never place orders and never know which broker they run
against — they emit target weights and the engine does the rest, which is why
they unit-test without a network.

**A new broker** — subclass `Broker` (`brokers/base.py`), implement the five
abstract methods, register it in `brokers/__init__.py`.
`brokers/robinhood.py` and `brokers/tastytrade.py` are stubs that document what
each one needs; the short version:

- **Tastytrade** is the easier port — official SDK, a certification sandbox,
  margin shorting, and native multi-leg orders that would remove the leg fill
  risk above.
- **Robinhood** has no official API, no paper environment, and no equity
  shorting, so the pair strategy cannot run there as written.

## Roadmap

Rough order of usefulness:

1. Parameter sweeps — `--sweep entry_z=1.5,2,2.5` over a grid, with a
   walk-forward split so the tuning is not scored on its own training data.
2. Beta- or vol-weighted leg sizing.
3. Limit orders with a marketable offset, instead of market orders.
4. Borrow-cost modeling in the backtest.
5. Multiple concurrent strategies with a portfolio-level risk budget.
6. Daily loss kill-switch.
7. Tastytrade adapter, then Robinhood.
8. Webhook/email alerts on entry, exit, and stop-out.

## Tests

```bash
.venv/bin/python -m pytest -q
```

128 tests, no network required — the suite runs against an in-memory fake broker
and synthetic price series constructed to hit exact z-scores. The backtest is
covered by a scripted strategy that isolates replay and portfolio accounting
from the signal math, and the Alpaca adapter's own logic is tested with the SDK
client stubbed out.
