# Small-Account Mode: Intraday Stock Trading

Active whenever account value < `{modes.daytrade_below_usd}` (see
`config/params.json`). Replaces **new wheel entries** only — management of any
existing option positions always runs first. No options approval is required
for this mode.

## Cash-account constraints (non-negotiable)

The Agentic account is a **cash** account: the PDT rule does not apply, but
settlement does.

- Buy only with **settled** cash. Sale proceeds settle T+1; never re-buy with
  same-day proceeds and sell again (good-faith violation).
- Consequence: at most `{daytrade.max_trades_per_day}` round trip per day,
  flat by end of day, full cash again the next morning.

## Daily cycle

In this mode `/trade` should be run on a loop during market hours
(`/loop 30m /trade`) — a single daily run can open a position but cannot
manage it intraday.

**Entry — only between {daytrade.entry_window_et} ET, only if flat and no
trade taken yet today:**

1. Screen liquid US large-caps/ETFs whose share price ≤
   `{daytrade.max_position_pct_of_settled_cash}`% of settled cash (whole
   shares preferred; fractional only if `review_equity_order` raises no
   alerts).
2. Candidate must be up `{daytrade.gap_up_min_pct}`–`{daytrade.gap_up_max_pct}`%
   vs. previous close (momentum continuation, not a parabolic spike), with
   bid–ask spread ≤ `{daytrade.max_spread_pct}`% of mid and heavy volume.
   Use `get_equity_quotes` plus a web check for news-driven moves; skip
   anything moving on binary news (halts, buyouts, FDA, earnings reactions).
3. Buy with a **limit at the ask**, GFD. If unfilled in 5 minutes, cancel; do
   not chase.

**After fill, immediately:**

- Place a GFD limit sell at entry × (1 + `{daytrade.target_pct}`/100).

**On every subsequent run while holding:**

- If last price ≤ entry × (1 − `{daytrade.stop_pct}`/100): cancel the target
  order and sell with a limit at the bid. The stop is enforced by these
  checks — never average down, never widen the stop.
- At/after `{daytrade.exit_by_et}` ET: cancel the target order and sell at the
  bid regardless of P&L. **Never hold overnight in this mode.**

## Risk rails (not adjustable by /review)

- Max `{daytrade.max_trades_per_day}` round trip per day. A losing day means
  done for the day.
- If realized P&L for the day ≤ −`{daytrade.daily_loss_halt_pct}`% of account
  value: stop trading until the next day.
- If account value < `{daytrade.account_floor_usd}`: create the `HALT` file,
  commit it, and tell the user the system has shut itself off pending a human
  decision.
- Limit orders only. One position at a time. No shorting, no leverage, no
  crypto, no sub-$1 stocks.

## Journaling

Every round trip goes in `journal/daytrades.csv`. `/review` reports day-trade
stats separately from wheel stats and may tune only `daytrade.target_pct` and
`daytrade.stop_pct`, within `adjustment_bounds`.

## Expectations

A single small momentum trade per day is near coin-flip odds minus the
spread; the purpose of this mode is to keep the account active and bounded in
risk while it grows toward wheel territory ($500+, realistically $3,000+) —
deposits, not day trades, are what will get it there. The rails exist so a
bad week costs a few percent, not the account.
