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
