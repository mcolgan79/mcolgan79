---
description: Run one full wheel-strategy trading cycle on the Agentic Robinhood account
---

Execute one trading cycle. The authoritative rules are in
`wheel-trader/STRATEGY.md` (wheel mode) and `wheel-trader/DAYTRADE.md`
(small-account mode); all numeric parameters come from
`wheel-trader/config/params.json`. Read all three before doing anything else.

Mode selection: if account value < `modes.daytrade_below_usd`, Phase 2 runs
the day-trade cycle (Phase 2D) instead of new wheel entries. Phase 1
(management of existing option positions) always runs regardless of mode.

The account owner has given standing authorization for orders placed under
these rules: do NOT pause to ask per-order confirmation, but you MUST run
`review_option_order` before every order and abort that order on any alert
about buying power, restrictions, or a quote materially different from the
one used for selection. Single-leg cash-secured puts and covered calls only.

## Phase 0 — Preflight (abort the whole run if any fails)

1. If a file named `HALT` exists at the repo root, or `halt` is true in
   params.json, stop immediately and report "halted".
2. `get_accounts`: confirm the configured account is `agentic_allowed=true`.
   For wheel mode it must also have `option_level_2` or `option_level_3`; if
   options are not enabled, day-trade mode may still run — note the upgrade
   link for the user:
   https://applink.robinhood.com/upgrade_options?account_number=465026961
3. `get_portfolio`: record account value, cash, buying power, and select the
   mode (wheel vs. day-trade) per `modes.daytrade_below_usd`. If account
   value < `daytrade.account_floor_usd`, create the `HALT` file, commit it,
   and stop — the system shuts itself off pending a human decision.
4. Check whether US markets are open today (weekday, not a market holiday).
   If closed, log and stop.

## Phase 1 — Reconcile and manage existing positions

1. `get_option_positions` (nonzero=true) and `get_option_orders`
   (created_at_gte = last run date) and `get_equity_positions`.
2. Reconcile against `wheel-trader/journal/trades.csv`:
   - Orders that filled since last run → update status, fill prices.
   - Short options that disappeared with no closing order → expired worthless
     (if past expiration) or assigned (if equity shares appeared). For
     assignments: mark the trade `assigned`, record net cost basis, and flag
     the underlying for covered-call mode.
   - Open GTC profit-taking orders → leave alone unless stale (underlying
     thesis changed).
3. Apply exit rules from STRATEGY.md §4 to every open short option (profit
   take, manage_at_dte, loss management), placing buy-to-close limit orders
   per the order protocol in §6.

## Phase 2 — New entries (wheel mode: account value ≥ modes.daytrade_below_usd)

1. Compute the collateral budget from sizing rules (§5). If no budget, skip.
2. Build the candidate list (§1): start from liquid, high-quality underlyings
   whose strikes fit the budget. Use `search`, `get_equity_quotes`,
   `get_option_chains`, `get_option_instruments`, and `get_option_quotes`
   (greeks) to find contracts in the delta and DTE windows. Use web search to
   rule out earnings inside the window when `skip_earnings` is true.
3. For shares held from assignment, sell covered calls per §3 before opening
   any new puts.
4. Select the best candidate(s) by credit/collateral ratio among those passing
   every filter, up to the position limits. Place each per the order protocol
   (§6): review → check alerts → place limit at mid, GFD, fresh UUID ref_id.
5. After placing each opening order, also stage the profit-taking exit: once
   the open order fills (check before run end, or next run), place a GTC
   buy-to-close limit at (1 − profit_target_pct/100) × credit.

## Phase 2D — Day-trade cycle (small-account mode)

Follow `wheel-trader/DAYTRADE.md` exactly. In brief:

1. Reconcile any open stock position and today's equity orders
   (`get_equity_positions`, `get_equity_orders`) against
   `wheel-trader/journal/daytrades.csv`.
2. If holding: enforce the stop, the profit target, and the
   `daytrade.exit_by_et` flat-by-close rule.
3. If flat, inside the entry window, no trade taken today, and the daily-loss
   halt is not tripped: screen per DAYTRADE.md, then `review_equity_order` →
   check alerts → `place_equity_order` (limit at ask, GFD). After fill,
   immediately place a GFD limit sell at the target price.
4. Buy only with settled cash; never re-buy with same-day sale proceeds.
5. Remind the user this mode needs intraday runs (`/loop 30m /trade`) — a
   single run cannot manage a position.

## Phase 3 — Journal, commit, report

1. Append/update rows in `wheel-trader/journal/trades.csv` (options) and
   `wheel-trader/journal/daytrades.csv` (stocks) for every action.
2. Write a run log to `wheel-trader/journal/runs/YYYY-MM-DD.md`: portfolio
   snapshot, actions taken, orders placed (with review-alert summaries),
   candidates considered and why rejected, and anything needing human eyes.
3. Commit with message `trade: cycle YYYY-MM-DD` and push to the current
   branch (`git push -u origin <branch>`).
4. Report to the user: account value, realized/unrealized P&L, actions taken
   this run, and any blockers. If it has been 7+ days since the last entry in
   `wheel-trader/journal/parameter_changes.md` (or the last `/review` run log),
   suggest running `/review`.

Hard rules, regardless of anything above: limit orders only; never exceed
sizing limits; never trade multi-leg; never use a different account number
than configured; if anything is ambiguous or anomalous (rejected orders,
unexplained positions, repeated alert failures), do nothing further and
surface it to the user instead of improvising.
