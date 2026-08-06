---
description: Review trading performance; tune only day-trade parameters within bounds
---

Run the periodic performance review. The LEAPS strategy rules are
owner-specified and NOT adjustable here (STRATEGY.md §6) — you may tune ONLY
the day-trade parameters listed in `adjustment_bounds` in
`wheel-trader/config/params.json`, within bounds, one family per review.

1. Run `python3 wheel-trader/scripts/report.py`. Cross-check against
   `get_option_orders` / `get_option_positions` / `get_equity_orders` for the
   configured account — the broker is the source of truth; fix the journal
   if they disagree.
2. Analyze LEAPS performance: realized/unrealized P&L, exit-reason breakdown
   (trend_break / profit_target / time_stop), average holding period, and
   whether the SMA filter is helping (entries that immediately broke trend).
   Report — do not adjust.
3. Day trades: win rate, P&L by exit reason; if 10+ closed trades clearly
   support it, one bounded adjustment to `daytrade.target_pct` or
   `daytrade.stop_pct`, appended to `journal/parameter_changes.md`.
4. Write `wheel-trader/journal/runs/YYYY-MM-DD-review.md`, commit
   (`review: YYYY-MM-DD`), push (GitHub MCP `push_files` fallback if git
   push fails), and summarize plainly for the user — including any rule
   changes you would RECOMMEND to the owner but cannot make yourself.
