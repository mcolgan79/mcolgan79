#!/usr/bin/env python3
"""Performance report from wheel-trader/journal/trades.csv (stdlib only)."""
import csv
import sys
from datetime import date
from pathlib import Path

JOURNAL = Path(__file__).resolve().parent.parent / "journal" / "trades.csv"


def f(row, key):
    v = (row.get(key) or "").strip()
    return float(v) if v else 0.0


def main():
    with open(JOURNAL, newline="") as fh:
        trades = list(csv.DictReader(fh))

    if not trades:
        print("No trades in journal yet.")
        return

    open_t = [t for t in trades if t["status"] == "open"]
    closed = [t for t in trades if t["status"] in ("closed", "expired", "assigned", "called_away")]
    realized = [t for t in closed if (t.get("realized_pnl") or "").strip()]

    print(f"Trades: {len(trades)} total, {len(open_t)} open, {len(closed)} closed")

    if realized:
        pnls = [f(t, "realized_pnl") for t in realized]
        wins = [p for p in pnls if p > 0]
        total = sum(pnls)
        print(f"Realized P&L: ${total:,.2f} over {len(pnls)} closed trades")
        print(f"Win rate: {len(wins)}/{len(pnls)} ({100 * len(wins) / len(pnls):.0f}%)")
        print(f"Avg win: ${sum(wins) / len(wins):,.2f}" if wins else "Avg win: n/a")
        losses = [p for p in pnls if p <= 0]
        print(f"Avg loss: ${sum(losses) / len(losses):,.2f}" if losses else "Avg loss: n/a")
        print(f"Worst trade: ${min(pnls):,.2f}")

        # Return on collateral, annualized per-trade then averaged
        rocs = []
        for t in realized:
            coll, pnl = f(t, "collateral"), f(t, "realized_pnl")
            if coll <= 0 or not t.get("date_opened") or not t.get("date_closed"):
                continue
            days = max(1, (date.fromisoformat(t["date_closed"]) - date.fromisoformat(t["date_opened"])).days)
            rocs.append((pnl / coll) * (365 / days))
        if rocs:
            print(f"Avg annualized return on collateral: {100 * sum(rocs) / len(rocs):.1f}%")

    if open_t:
        coll = sum(f(t, "collateral") for t in open_t)
        cred = sum(f(t, "credit_received") for t in open_t)
        print(f"Open: ${coll:,.2f} collateral deployed, ${cred:,.2f} credit collected")
        for t in open_t:
            print(f"  {t['symbol']} {t['strategy']} {t['strike']} exp {t['expiration']}")


if __name__ == "__main__":
    sys.exit(main())
