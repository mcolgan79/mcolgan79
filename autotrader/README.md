# autotrader

A small CLI automated trading platform. Version 1 trades one strategy — a
GLD/GDX z-score pair — against an **Alpaca paper account**. Brokers and
strategies sit behind interfaces, so adding Robinhood, Tastytrade, or a second
strategy is a new file rather than a rewrite.

```
trader signal          # what does the strategy think right now?
trader run --once      # evaluate and place the resulting orders
trader run --loop      # keep evaluating on an interval
trader history         # why did it do that?
```

## Quickstart

```bash
cd autotrader
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env          # add your Alpaca *paper* keys
trader init                   # writes config.toml
trader doctor                 # verifies keys, clock, data, shortability
trader signal                 # look before you trade
trader run --once --dry-run   # see the orders it would send
trader run --once             # send them
```

Paper API keys come from the [Alpaca paper dashboard](https://app.alpaca.markets/paper/dashboard/overview)
under **API Keys**. `.env` and `config.toml` are both gitignored.

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
| `trader status` | account, clock, positions, and the current signal |
| `trader signal` | evaluate and print the signal; never trades |
| `trader run --once` | evaluate once and place orders (cron-friendly) |
| `trader run --loop -i 15m` | evaluate on an interval until Ctrl-C |
| `trader run --once --dry-run` | print the orders without submitting them |
| `trader positions` | open positions at the broker |
| `trader close` | flatten every leg this strategy trades, ignoring the signal |
| `trader history` / `--orders` | recorded signals or orders from the local database |
| `trader list` | registered brokers and strategies |

Global flags: `--config PATH`, `--log-level DEBUG`.

`run --once` exits non-zero if any order was rejected, so cron and CI can tell
that something went wrong.

## Configuration

`config.toml` (searched in `./config.toml`, then `~/.autotrader/config.toml`).
Credentials never live here — they come from the environment or `.env`.

```toml
[broker]
name = "alpaca"       # alpaca | robinhood (planned) | tastytrade (planned)
paper = true
data_feed = "iex"     # "iex" on free plans, "sip" if you subscribe

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

## Scheduling

Daily bars only need one evaluation a day. Run it shortly before the close so
the last bar is meaningful:

```cron
# 15:45 America/New_York, weekdays
45 15 * * 1-5 cd /path/to/autotrader && .venv/bin/trader run --once >> cron.log 2>&1
```

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
- **No backtest yet.** The parameters here are conventional defaults, not
  fitted ones. Nothing in this repo has been validated against history.
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

1. `trader backtest` — replay historical bars through the same `Strategy` code.
2. Beta- or vol-weighted leg sizing.
3. Limit orders with a marketable offset, instead of market orders.
4. Multiple concurrent strategies with a portfolio-level risk budget.
5. Daily loss kill-switch.
6. Tastytrade adapter, then Robinhood.
7. Webhook/email alerts on entry, exit, and stop-out.

## Tests

```bash
.venv/bin/python -m pytest -q
```

71 tests, no network required — the suite runs against an in-memory fake broker
and synthetic price series constructed to hit exact z-scores.
