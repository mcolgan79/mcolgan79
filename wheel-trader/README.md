# Wheel Trader — Autonomous Option-Selling System

An agentic option-selling system that runs the **wheel strategy** (cash-secured
puts → assignment → covered calls) on Robinhood via the Robinhood Agentic MCP,
executed by Claude Code sessions on this repo.

## How it works

There is no standalone daemon — Robinhood's agentic access is only available
inside a Claude Code session. The "program" is a set of runbooks (slash
commands) that Claude executes deterministically against live market data:

| Command   | What it does                                                                |
|-----------|-----------------------------------------------------------------------------|
| `/trade`  | Full daily cycle: manage open positions, take profits, handle assignment, open new positions per the rules, update the journal, commit + push. |
| `/review` | Weekly: compute performance stats from the journal and tune strategy parameters **within hard bounds**, logging every change. |

All rules live in [`STRATEGY.md`](STRATEGY.md). All tunable numbers live in
[`config/params.json`](config/params.json). Every trade is logged to
[`journal/trades.csv`](journal/trades.csv) and committed to git, so the full
history is auditable.

## Setup checklist (blockers — nothing trades until these are done)

1. **Enable options on the Agentic account.** The only agentic-enabled account
   (••••6961, nickname "Agentic") has no options approval. Apply for
   **Level 2** here:
   https://applink.robinhood.com/upgrade_options?account_number=465026961
2. **Fund the account.** It currently holds **$97.24**, which cannot secure a
   single put on any quality underlying (a $25-strike put requires $2,500
   collateral). Recommended minimum: **$3,000+**; the more capital, the better
   the diversification across underlyings.
3. **Run it.** Open a Claude Code session on this repo each trading day and
   type `/trade` (or `/loop 6h /trade` to repeat within a session). Run
   `/review` weekly.

## Safety rails

- **Kill switch:** create a file named `HALT` at the repo root (or set
  `"halt": true` in `config/params.json`). `/trade` exits immediately without
  trading.
- **Defined-risk only by construction:** cash-secured puts and covered calls
  only (the MCP supports nothing riskier — no naked options, no spreads).
- **Limit orders only.** Never market orders.
- **Every order is simulated first** (`review_option_order`); any
  buying-power, restriction, or anomalous-quote alert aborts the order.
- **Position limits can never be raised by the self-adjustment process** —
  `/review` may only move parameters within the `adjustment_bounds` in
  `config/params.json`. Loosening a bound requires a human edit.

## Honest expectations

Selling options harvests premium most months and takes occasional large
drawdowns when the market gaps down — that is the trade-off, not a bug to be
tuned away. This system enforces discipline (sizing, exits, journaling); it
does not guarantee profit, and you should only deploy money you can afford to
see drawn down 30%+ in a bad month. "Set and forget" applies to the rules, not
to the risk.
