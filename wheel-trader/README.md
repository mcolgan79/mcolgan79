# LEAPS Trend Trader — Autonomous Options System

An agentic trading system that buys **long-dated LEAPS calls on stocks in
confirmed uptrends** on Robinhood via the Robinhood Agentic MCP, executed by
Claude Code sessions on this repo. (Originally built as a wheel/option-selling
system; the owner replaced the strategy rules on 2026-08-06.)

## How it works

There is no standalone daemon — Robinhood's agentic access is only available
inside a Claude Code session. The "program" is a set of runbooks (slash
commands) that Claude executes deterministically against live market data:

| Command   | What it does                                                                |
|-----------|-----------------------------------------------------------------------------|
| `/trade`  | Full cycle: check exit rules on open LEAPS (trend break / profit target / time stop), open new qualifying positions, update the journal, commit + push. |
| `/review` | Periodic: performance stats from the journal. LEAPS rules are owner-fixed; only day-trade-mode parameters are tunable, within hard bounds. |

The system has two modes, selected automatically by account value:

| Account value | Mode | Rules |
|---|---|---|
| ≥ $500 | LEAPS trend following: longest-dated calls at ~110% strike, 200-day SMA filter | [`STRATEGY.md`](STRATEGY.md) |
| < $500 | Small-account: one bounded intraday stock trade per day, flat by close | [`DAYTRADE.md`](DAYTRADE.md) |

## The strategy in one paragraph

Entry: stock above its 200-day SMA, dividend yield ≤ 3% → buy the
longest-listed call at the strike nearest 110% of spot, keeping total LEAPS
cost ≤ 30% of the portfolio. Exit at the first of: three consecutive closes
below the 200-day SMA, 100% profit (GTC order rests at 2× cost), or 365 days
left to expiration. A poor-man's-covered-call overlay is specified but
**disabled** — it needs options Level 3 + a margin account, and the agentic
API can't do multi-leg on cash accounts (see STRATEGY.md §5).

## Operating it

Open a Claude Code session on this repo each trading day and type `/trade`
(or `/loop 6h /trade` within a session). Run `/review` weekly. The account
in use is the agentic-enabled cash account ••••6961 ("Agentic"), options
Level 2.

## Safety rails

- **Kill switch:** create a file named `HALT` at the repo root (or set
  `"halt": true` in `config/params.json`); `/trade` exits immediately.
- **Defined risk by construction:** long calls only — max loss is the premium
  paid, which is capped at 30% of the portfolio.
- **Limit orders only.** Every order is simulated first
  (`review_option_order`); alerts abort the order.
- **The strategy rules are owner-locked** — `/review` cannot modify them;
  it may only tune day-trade parameters within `adjustment_bounds`.
- Journals (`journal/leaps.csv`, `journal/daytrades.csv`) and run logs are
  committed to git for a full audit trail.

## Honest expectations

Long OTM LEAPS are a leveraged bet on the trend continuing: most positions
will either double (target) or bleed theta until an exit rule fires, and a
choppy market that whipsaws around the 200-day SMA will produce a string of
small-to-medium losses. The 30% cap bounds the damage; nothing guarantees
profit. "Set and forget" applies to the rules, not the risk.
