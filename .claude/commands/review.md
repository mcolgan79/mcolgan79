---
description: Review wheel-trader performance and tune parameters within bounds
---

Run the weekly performance review for the wheel trader. Rules: see
`wheel-trader/STRATEGY.md` §7. You may adjust ONLY the parameters listed in
`adjustment_bounds` in `wheel-trader/config/params.json`, only within their
bounds, and only one parameter family per review. Sizing limits and safety
rails are never adjustable here.

1. Run `python3 wheel-trader/scripts/report.py` for the journal statistics.
   Cross-check realized P&L against `get_option_orders` /
   `get_option_positions` for the configured account — the broker is the
   source of truth; fix the journal if they disagree.
2. Analyze: win rate, average credit / collateral, annualized return on
   collateral, max single-trade loss, and how losses happened (gap risk vs.
   slow bleed vs. early entries). Day trades (small-account mode) are
   reported separately: win rate, total P&L, and P&L by exit reason
   (target/stop/time) — only `daytrade.target_pct` and `daytrade.stop_pct`
   are tunable, within bounds. Fewer than 10 closed trades in a category →
   report stats but make NO parameter changes for that category
   (insufficient sample).
3. If the evidence clearly supports it, make at most one bounded adjustment
   (e.g. persistent losers at high delta → lower delta_target one step;
   profit targets rarely hit before manage_at_dte → lower profit_target_pct).
   Append the change, evidence, and bounds check to
   `wheel-trader/journal/parameter_changes.md`.
4. Write the review to `wheel-trader/journal/runs/YYYY-MM-DD-review.md`,
   commit (`review: YYYY-MM-DD`), push, and give the user a plain-language
   summary: how the strategy is doing, what changed and why, or why nothing
   changed.
