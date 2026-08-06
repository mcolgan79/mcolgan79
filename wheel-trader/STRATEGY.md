# Strategy: LEAPS Trend Following (long calls + optional PMCC overlay)

Owner-defined rules (2026-08-06). `/trade` executes these mechanically.
Numbers in `{braces}` come from `config/params.json` at run time.

## Core idea

Buy long-dated out-of-the-money LEAPS calls on stocks in confirmed uptrends;
ride the trend with a mechanical exit. Optionally sell shorter-dated calls
against them (poor man's covered call) to reduce cost basis — see §5 for why
this module is currently disabled.

## 1. Entry rules

A position may be opened only if ALL hold:

- **Trend filter:** underlying trades above its 200-day SMA
  (`get_equity_technical_indicators`, period 200, daily bars).
- **Dividend filter:** trailing dividend yield ≤
  `{leaps.max_dividend_yield_pct}`% — the intent is to exclude names whose
  return comes as yield rather than price appreciation, since long calls
  capture only the latter (owner amendment 2026-08-06, revised to 3%).
- **Expiration:** the LAST (longest-dated) expiration listed on the chain,
  and it must be more than 365 days out — otherwise the underlying is
  ineligible (exit rule 3 would trigger at entry).
- **Strike:** the listed strike nearest to
  `{leaps.strike_pct_of_spot}`% of the current underlying price.
- **Liquidity sanity:** open interest ≥ `{leaps.min_open_interest}` and
  bid–ask spread ≤ `{leaps.max_spread_pct_of_mid}`% of mid.
- **Budget:** total cost basis of ALL open LEAPS (including this one) ≤
  `{leaps.max_total_position_pct}`% of portfolio value.
- Order: **limit buy at the mid**, GFD. If unfilled by next run, cancel and
  re-evaluate; never chase more than one re-quote.

When several candidates qualify, prefer (in order): larger/higher-quality
underlying, higher OI, distance above the SMA.

Sizing rule of thumb (measured 2026-08-06): a ~110% strike LEAPS costs about
9–11% of share price on low-IV underlyings (16–20% IV) and ~27% on high-IV
ones (60%+ IV). Use this to pre-filter candidates by share price before
pulling chains.

## 2. Exit rules — first one hit wins

1. **Trend break:** underlying CLOSES below its 200-day SMA for
   `{leaps.sma_exit_consecutive_days}` consecutive trading days → sell at mid
   next run.
2. **Profit target:** option value reaches
   `{leaps.profit_target_pct}`% gain over cost (i.e. 2× cost at 100%).
   After entry fills, immediately place a GTC limit sell at 2× the fill
   price so this can trigger between runs.
3. **Time stop:** `{leaps.exit_at_dte}` days or less to expiration → sell at
   mid next run, regardless of P&L.

Track the SMA-breach streak in the journal on every run (consecutive_closes_below).

## 3. Position sizing

- Total LEAPS cost basis ≤ `{leaps.max_total_position_pct}`% of portfolio
  value at time of entry. No other per-position cap — the budget is the cap.
- Long calls only. No margin, no shorting.

## 4. Order placement protocol (every order, no exceptions)

1. `review_option_order` first with `chain_symbol` + `underlying_type`.
2. Abort on any alert about buying power, restrictions, or a quote moved
   > 10% from the price used for selection.
3. `place_option_order` with a fresh UUID `ref_id` (reuse only on transport
   retries).
4. Log to `journal/leaps.csv` immediately, whatever the outcome.

## 5. PMCC overlay (DISABLED — account limitation)

Selling a call against a LEAPS (a diagonal spread) requires **options
Level 3**, and the agentic order API does not support multi-leg orders on
**cash** accounts at all. The Agentic account is cash + Level 2, so a short
call would be treated as naked and rejected. This module stays off until the
account supports it (`{pmcc.enabled}` = false).

Rules when enabled: sell 1 call per LEAPS contract, strike above the LEAPS
strike and above current spot, 30–45 DTE, delta ≤ 0.30; close or roll at
50% profit or 21 DTE; never let the short strike drop below the LEAPS
break-even.

## 6. Self-adjustment policy

The LEAPS rules above are owner-specified and are NOT adjustable by
`/review` — any change requires the owner. `/review` reports performance
(win rate, avg gain, time-in-trade, exit-reason breakdown) and may only tune
day-trade-mode parameters within `adjustment_bounds`.
