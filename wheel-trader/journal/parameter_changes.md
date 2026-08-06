# Parameter change log

Every change `/review` makes to `config/params.json` is recorded here with the
evidence that motivated it. Format:

```
## YYYY-MM-DD
- Changed: <param> <old> → <new>
- Evidence: <stats from journal that motivated the change>
- Bounds check: within adjustment_bounds [lo, hi]
```

_No changes yet._

## 2026-08-06 (human/builder change, not /review)
- Changed: added `sizing.small_account_cap_waiver_below_usd` = 1500
- Evidence: at $607 account value the 40% per-underlying cap limits strikes
  to $2.40, making wheel mode impossible at the very account size where it
  activates ($500). Below $1,500 one position is the diversification limit
  regardless; the deployment cap (90%) and cash buffer ($50) still bound risk.
- Bounds check: n/a (sizing is not /review-adjustable; this is a config fix)

## 2026-08-06 (owner strategy replacement)
- Changed: entire strategy replaced — wheel (CSP/covered calls) → LEAPS trend
  following, per owner instruction. New rules: buy longest-dated calls at
  strike ≈110% of spot when underlying > 200-day SMA; exit at first of
  3 consecutive closes below 200-day SMA / +100% profit / ≤365 DTE; total
  LEAPS cost ≤ 30% of portfolio. PMCC overlay specified but disabled
  (needs options L3 + margin; agentic account is cash L2, and the order API
  rejects multi-leg on cash accounts).
- Evidence: owner directive ("disregard the old rules"), 2026-08-06.
- Bounds check: n/a (owner change; LEAPS rules marked not_adjustable)

## 2026-08-06 (owner amendment)
- Changed: added `leaps.max_dividend_yield_pct` = 2.0 (entry filter)
- Evidence: owner directive — no heavy dividend stocks (>2% yield). Disqualified
  the pending VALE Jan-2028 $17c entry (VALE yields well above 2%).
- Bounds check: n/a (owner change)
