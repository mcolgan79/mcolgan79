---
description: Run one LEAPS trend-following trading cycle on the Agentic Robinhood account
---

Execute one trading cycle. The authoritative rules are in
`wheel-trader/STRATEGY.md` (LEAPS trend following, ≥ $500 account value) and
`wheel-trader/DAYTRADE.md` (small-account mode, < $500); all numeric
parameters come from `wheel-trader/config/params.json`. Read all three before
doing anything else.

The account owner has given standing authorization for orders placed under
these rules: do NOT pause to ask per-order confirmation, but you MUST run
`review_option_order` / `review_equity_order` before every order and abort
that order on any alert about buying power, restrictions, or a quote
materially different from the one used for selection. Long calls and (in
day-trade mode) long stock only — the PMCC short-call module is disabled
until the account supports it (see STRATEGY.md §5).

## Phase 0 — Preflight (abort the whole run if any fails)

1. If a file named `HALT` exists at the repo root, or `halt` is true in
   params.json, stop immediately and report "halted".
2. `get_accounts`: confirm the configured account is `agentic_allowed=true`
   with `option_level_2` or `option_level_3`.
3. `get_portfolio`: record account value and cash; select mode
   (LEAPS vs. day-trade) per `modes.daytrade_below_usd`. If account value <
   `daytrade.account_floor_usd`, create `HALT`, commit it, and stop.
4. Confirm US markets are open today; if not, log and stop.

## Phase 1 — Manage open LEAPS positions (always runs)

1. `get_option_positions` (nonzero=true) + `get_option_orders` since last
   run; reconcile fills/cancellations against `wheel-trader/journal/leaps.csv`.
2. For each open LEAPS, evaluate exits in STRATEGY.md §2 order:
   - **Trend break:** fetch the last `leaps.sma_exit_consecutive_days` daily
     closes and the 200-day SMA (`get_equity_historicals` +
     `get_equity_technical_indicators`). Update the
     `consecutive_closes_below_sma` streak in the journal. Streak ≥ 3 →
     cancel the GTC profit order and sell at mid (limit, GFD).
   - **Profit target:** confirm a GTC limit sell at 2× cost is resting; if
     missing (e.g. entry filled after last run), place it.
   - **Time stop:** DTE ≤ `leaps.exit_at_dte` → cancel GTC and sell at mid.
3. Record every exit in the journal with `exit_reason`
   (trend_break / profit_target / time_stop).

## Phase 1S — Interim share holding (owner directive)

If `shares.enabled` is true in params.json:

1. Reconcile the position in `wheel-trader/journal/holdings.csv` against
   `get_equity_positions`; report quantity, average cost, and unrealized P&L.
2. If the holding is below `shares.max_pct_of_portfolio`% of portfolio value
   and settled cash allows, you MAY top it up to that cap with a marketable
   limit buy (review → check alerts → place). Never exceed the cap.
3. **Do NOT sell.** No exit rule has been specified by the owner. Hold and
   report; sell only on an explicit owner instruction or a written exit rule
   in `shares.exit_rule`. Flag in the run log that the position has no exit.

## Phase 2 — New LEAPS entries (account value ≥ modes.daytrade_below_usd)

1. Budget = `leaps.max_total_position_pct`% of portfolio value minus cost
   basis of open LEAPS. If ≤ ~$50, skip entries.
2. Screen candidates: liquid optionable underlyings whose longest-dated
   call chain is > 365 DTE and whose ~110% strike premium fits the budget.
   For each: check price vs 200-day SMA and dividend yield ≤
   `leaps.max_dividend_yield_pct`% (`get_equity_fundamentals`), then find the
   longest expiration and the strike nearest `leaps.strike_pct_of_spot`%
   of spot, then check OI and spread per STRATEGY.md §1.
3. Rank qualifiers (quality, OI, distance above SMA) and buy down the list
   while budget remains: review → check alerts → place limit buy at mid,
   GFD, fresh UUID ref_id.
4. After each fill: place the GTC limit sell at 2× fill price (profit
   target), and journal the position (entry price, underlying price,
   SMA value, streak = 0).

## Phase 2D — Day-trade cycle (account value < modes.daytrade_below_usd)

Follow `wheel-trader/DAYTRADE.md` exactly (unchanged).

## Phase 3 — Journal, commit, report

1. Update `wheel-trader/journal/leaps.csv` (and `daytrades.csv` if in that
   mode) for every action.
2. Write a run log to `wheel-trader/journal/runs/YYYY-MM-DD.md`: portfolio
   snapshot, SMA streaks for open positions, actions, candidates
   considered/rejected, blockers.
3. Commit (`trade: cycle YYYY-MM-DD`) and push to the current branch. If
   `git push` fails for credentials, push the changed files via the GitHub
   MCP `push_files` tool to the same branch, then
   `git fetch` + `git reset --hard origin/<branch>` to resync local.
4. Report: account value, open positions with unrealized P&L and streak
   status, actions taken, blockers.

Hard rules regardless of anything above: limit orders only; never exceed the
30% LEAPS budget; no multi-leg orders; no short options while PMCC is
disabled; never use a different account number than configured; on anything
anomalous (rejected orders, unexplained positions, repeated alerts), stop
and surface it to the user instead of improvising.
