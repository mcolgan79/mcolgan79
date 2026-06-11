# Strategy: The Wheel (Cash-Secured Puts → Covered Calls)

This document is the authoritative rule set. `/trade` executes these rules
mechanically. Numbers in `{braces}` are read from `config/params.json` at run
time — never hardcode them.

## State machine

```
CASH ──sell CSP──▶ SHORT PUT ──expires worthless / closed at profit──▶ CASH
                       │
                   assigned
                       ▼
                  LONG 100 SHARES ──sell covered call──▶ SHORT CALL
                       ▲                                      │
                       │  expires worthless / closed at profit│
                       └──────────────────────────────────────┤
                                                          called away
                                                              ▼
                                                            CASH
```

## 1. Universe selection (which underlyings)

A symbol qualifies for new cash-secured puts only if ALL hold:

- US-listed stock or ETF the account can afford: `strike × 100 ≤` available
  collateral budget (see sizing).
- Liquid options: open interest ≥ `{entry.min_open_interest}` on the candidate
  contract, bid–ask spread ≤ `{entry.max_bid_ask_spread_pct}`% of mid.
- Quality screen: profitable large/mid-cap or broad ETF you would be
  comfortable owning at the strike. No biotechs awaiting binary events, no
  meme-of-the-week, nothing on `{universe.exclude}`.
- No earnings report between today and expiration when
  `{entry.skip_earnings}` is true (verify with a web search).
- Not already an open position in this system (max 1 position per underlying).

## 2. Entry rules — cash-secured put

- Expiration: `{entry.dte_min}`–`{entry.dte_max}` days out (target ~30–45).
- Strike: delta between `{entry.delta_min}` and `{entry.delta_max}`
  (absolute value; from `get_option_quotes` greeks). Prefer the strike nearest
  `{entry.delta_target}`.
- Minimum premium: credit ≥ `{entry.min_credit_pct_of_collateral}` of
  collateral (filters out junk yield).
- Order: **limit, sell-to-open, at the mid**, GFD. If unfilled by next run,
  cancel and re-evaluate — never chase by more than one re-quote.

## 3. Entry rules — covered call (after assignment)

- Only against lots of 100 shares acquired via assignment.
- Strike: at or above the **net cost basis** (assignment strike − total
  premium collected on that underlying), delta ≤ `{entry.delta_max}`.
  If no strike above basis offers acceptable premium, prefer waiting over
  locking in a loss.
- Same DTE window and order mechanics as puts.

## 4. Exit / management rules (checked every run, before any new entries)

- **Profit take:** buy-to-close any short option at
  `{exit.profit_target_pct}`% of the credit received (e.g. collected $1.00,
  close at $0.50 when target is 50). Use a GTC limit so it can fill between
  runs.
- **Time management:** at ≤ `{exit.manage_at_dte}` DTE, close the position at
  whatever the market gives if it's profitable; if it's a put that is in the
  money, either close or accept assignment per the wheel — never roll for a
  net debit.
- **Loss management:** if a short option's mark ≥
  `{exit.max_loss_pct_of_credit}`% of credit received (e.g. 200% = the loss is
  2× the credit), close it. Taking the small loss beats hoping.
- **Assignment handling:** if shares appear from an assigned put, record the
  net cost basis in the journal and switch that underlying to covered-call
  mode. If shares are called away, realize the cycle P&L and return the
  underlying to the CSP-eligible pool.

## 5. Position sizing

- Deploy at most `{sizing.max_deployed_pct}`% of account value as collateral;
  always keep ≥ `{sizing.min_cash_buffer_usd}` cash free.
- Max `{sizing.max_positions}` concurrent positions.
- Max `{sizing.max_collateral_per_underlying_pct}`% of account value in any
  one underlying.
- `{sizing.max_contracts_per_position}` contract(s) per position.

## 6. Order placement protocol (every order, no exceptions)

1. `review_option_order` first, with `chain_symbol` + `underlying_type` so
   fees and collateral come back.
2. Abort the order if the review surfaces any alert about buying power,
   account restrictions, pattern-day-trading, or a quote that moved > 10%
   from the price used for selection.
3. Place with `place_option_order` using a fresh UUID `ref_id`; reuse the same
   `ref_id` only when retrying a transport failure.
4. Log the order to the journal immediately, whatever the outcome.

## 7. Self-adjustment (executed by `/review`, never by `/trade`)

`/review` computes from `journal/trades.csv`: win rate, average credit,
realized P&L, annualized return on collateral, and max single-trade loss. It
may then move `entry.delta_target`, `entry.dte_min/max`,
`exit.profit_target_pct`, and `exit.max_loss_pct_of_credit` — **only within
`adjustment_bounds`**, only one step per review, and every change must be
appended to `journal/parameter_changes.md` with the evidence that motivated
it. Sizing limits and safety rails are not adjustable by `/review` under any
circumstances.
