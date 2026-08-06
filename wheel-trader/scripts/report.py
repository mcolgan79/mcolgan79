#!/usr/bin/env python3
"""Performance report from the trading journals (stdlib only)."""
import csv
import sys
from datetime import date
from pathlib import Path

JOURNAL_DIR = Path(__file__).resolve().parent.parent / "journal"
LEAPS_JOURNAL = JOURNAL_DIR / "leaps.csv"
DAYTRADE_JOURNAL = JOURNAL_DIR / "daytrades.csv"


def f(row, key):
    v = (row.get(key) or "").strip()
    return float(v) if v else 0.0


def leaps_report():
    if not LEAPS_JOURNAL.exists():
        return
    with open(LEAPS_JOURNAL, newline="") as fh:
        trades = list(csv.DictReader(fh))
    print("== LEAPS ==")
    if not trades:
        print("No LEAPS trades in journal yet.")
        return

    open_t = [t for t in trades if t["status"] == "open"]
    closed = [t for t in trades if t["status"] == "closed" and (t.get("realized_pnl") or "").strip()]
    print(f"Positions: {len(open_t)} open, {len(closed)} closed")

    if closed:
        pnls = [f(t, "realized_pnl") for t in closed]
        wins = [p for p in pnls if p > 0]
        print(f"Realized P&L: ${sum(pnls):,.2f}")
        print(f"Win rate: {len(wins)}/{len(pnls)} ({100 * len(wins) / len(pnls):.0f}%)")
        print(f"Worst trade: ${min(pnls):,.2f}")
        by_reason = {}
        holds = []
        for t in closed:
            by_reason.setdefault(t.get("exit_reason") or "unknown", []).append(f(t, "realized_pnl"))
            if t.get("date_opened") and t.get("date_closed"):
                holds.append((date.fromisoformat(t["date_closed"]) - date.fromisoformat(t["date_opened"])).days)
        for reason, ps in sorted(by_reason.items()):
            print(f"  exit={reason}: {len(ps)} trades, ${sum(ps):,.2f}")
        if holds:
            print(f"Avg holding period: {sum(holds) / len(holds):.0f} days")

    for t in open_t:
        cost = f(t, "debit_paid")
        streak = t.get("consecutive_closes_below_sma") or "0"
        print(f"  OPEN: {t['symbol']} {t['expiration']} ${t['strike']}c x{t['contracts']}"
              f" cost ${cost:,.2f}, SMA-breach streak {streak}/3")


def daytrade_report():
    if not DAYTRADE_JOURNAL.exists():
        return
    with open(DAYTRADE_JOURNAL, newline="") as fh:
        trades = list(csv.DictReader(fh))
    if not trades:
        return

    print("\n== Day trades ==")
    closed = [t for t in trades if t["status"] == "closed" and (t.get("pnl") or "").strip()]
    open_t = [t for t in trades if t["status"] == "open"]
    print(f"Round trips: {len(closed)} closed, {len(open_t)} open")
    if closed:
        pnls = [f(t, "pnl") for t in closed]
        wins = [p for p in pnls if p > 0]
        print(f"Realized P&L: ${sum(pnls):,.2f}")
        print(f"Win rate: {len(wins)}/{len(pnls)} ({100 * len(wins) / len(pnls):.0f}%)")
        print(f"Worst trade: ${min(pnls):,.2f}")
        by_reason = {}
        for t in closed:
            by_reason.setdefault(t.get("exit_reason") or "unknown", []).append(f(t, "pnl"))
        for reason, ps in sorted(by_reason.items()):
            print(f"  exit={reason}: {len(ps)} trades, ${sum(ps):,.2f}")
    for t in open_t:
        print(f"  OPEN: {t['symbol']} x{t['quantity']} @ {t['entry_price']} ({t['date']})")


def main():
    leaps_report()
    daytrade_report()


if __name__ == "__main__":
    sys.exit(main())
