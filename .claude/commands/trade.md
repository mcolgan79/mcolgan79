---
description: Run one full wheel-strategy trading cycle on the Agentic Robinhood account
---

Execute one trading cycle of the wheel strategy. The authoritative rules are
in `wheel-trader/STRATEGY.md`; all numeric parameters come from
`wheel-trader/config/params.json`. Read both before doing anything else.

The account owner has given standing authorization for orders placed under
these rules: do NOT pause to ask per-order confirmation, but you MUST run
`review_option_order` before every order and abort that order on any alert
about buying power, restrictions, or a quote materially different from the
one used for selection. Single-leg cash-secured puts and covered calls only.

## Phase 0 — Preflight (abort the whole run if any fails)

1. If a file named `HALT` exists at the repo root, or `halt` is true in
   params.json, stop immediately and report "halted".
2. `get_accounts`: confirm the configured account is `agentic_allowed=true`
   and has `option_level_2` or `option_level_3`. If options are not enabled,
   stop and tell the user to apply at
   https://applink.robinhood.com/upgrade_options?account_number=465026961
3. `get_portfolio`: record account value, cash, buying power. If buying power
   < $500, note that no new entries are possible (management of existing
   positions still proceeds).
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

## Phase 2 — New entries

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

## Phase 3 — Journal, commit, report

1. Append/update rows in `wheel-trader/journal/trades.csv` for every action.
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
