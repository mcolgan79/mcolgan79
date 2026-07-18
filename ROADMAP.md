# OptPoP Roadmap

Living plan for OptPoP — what's shipped, what's next, and how the bigger
features fit together. Effort is T-shirt sized (S / M / L / XL). Update this
file as items ship (move them to **Shipped** with the date).

Legend: ✅ done · 🚧 in progress · ⬜ planned · 💡 idea/backlog

---

## Shipped

- ✅ Options math engine — Black–Scholes pricing, Greeks, implied-vol solver
- ✅ Multi-leg strategies — single, verticals, iron condors, calendars, diagonals,
  straddles/strangles, custom (1–6 legs, mixed expirations)
- ✅ Analytics — POP, P50 (Monte Carlo), probability of touch, expected move,
  breakevens, max profit/loss, reward:risk
- ✅ Visualizations — payoff chart (expiration + T+0), terminal distribution,
  net Greeks table; hover/keyboard tooltips, table views, light/dark
- ✅ Recommendations — structure-aware trade-improvement heuristics
- ✅ Live market data — Tradier (bring-your-own-key): quotes, expirations,
  chain-driven strike/premium/IV
- ✅ Platforms — installable PWA (iOS/Android), Tauri desktop (Windows/macOS/Linux),
  native iOS build
- ✅ Monetization — free tier with ad slots (AdSense-ready), OptPoP Pro subscription
- ✅ Payments — Stripe Checkout, webhook → Cloudflare KV entitlement cache,
  Customer Portal (manage/cancel); live mode verified
- ✅ Legal — Terms / Privacy / Refund pages + footer; proprietary license (Pera Pera, Inc.)
- ✅ Infra — Cloudflare Pages deploy, serverless API functions, CI, test suite (56 tests)

---

## Now — launch hardening (S, mostly config)

- 🚧 **Custom domain** `optpop.com` — DNS on Cloudflare; attach to the Pages
  project via Custom domains, remove the registrar parking record. After it
  resolves: set `PUBLIC_BASE_URL=https://optpop.com`, update Stripe's checkout
  return/webhook URLs and AdSense site, and point the PWA canonical/manifest at
  the domain.
- ⬜ **Fill `[STATE]`** in the Terms "Governing law" clause.
- ⬜ **Apply to Google AdSense** (needs the live domain + privacy policy, both
  ready); then set `VITE_ADSENSE_CLIENT` + slot IDs and the real `ads.txt`.
- ⬜ **Error monitoring** — lightweight client + function error reporting
  (e.g., Sentry free tier) so production issues surface without console spelunking.

---

## Phase 1 — Foundations (the big enabler)

- ⬜ **User accounts / sign-in** — email + magic-link (passwordless). **L.**
  This is the pivot that unlocks most of what's below: it lets an entitlement,
  a journal, or a broker connection follow a *person* across devices instead of
  living on one device.
  - Unblocks: cross-device Pro, cloud-synced journal, saved backtests, portfolio.
  - Approach: a serverless auth (e.g., magic-link tokens signed server-side +
    session cookie) with Cloudflare D1/KV for the user table; or a managed
    provider (Clerk/Auth0/Supabase Auth) to move faster.
  - Ties off the existing caveat that Pro entitlement and the Stripe customer id
    are currently per-device.

---

## Phase 2 — More robust visualizations (M, no new infra)

Self-contained frontend work — high user value, no accounts or external
services required, so it can proceed in parallel with Phase 1.

- ⬜ **P&L heatmap** — price × time-to-expiration surface (profit/loss color map),
  the standard "at a glance" options view. **M.**
- ⬜ **Greeks curves** — delta/gamma/theta/vega vs. underlying price and vs. days,
  for the whole position. **M.**
- ⬜ **IV smile / skew** — plot the option chain's IV across strikes (needs the
  live chain, already available). **M.**
- ⬜ **Probability cone** — expected price range over time (±1σ/2σ) overlaid on the
  payoff/price axis. **S.**
- ⬜ **What-if scenario controls** — sliders for spot / IV / days that re-render the
  charts live (uses `useDeferredValue` we already have). **S–M.**
- ⬜ **Strategy comparison** — overlay two candidate structures' payoff/POP. **M.**
- 💡 Per-leg contribution breakdown; theta-decay animation.

---

## Phase 3 — Trade journal (M local-first, +M for cloud sync)

- ⬜ **Local-first journal** — log trades (underlying, legs, entry credit/debit,
  thesis, tags), mark closed with exit + realized P&L, and review stats
  (win rate, avg P&L, P&L by strategy/tag, expectancy). **M.**
  - Storage: IndexedDB (larger/structured than localStorage), export/import JSON
    and CSV so data is portable even before accounts exist.
- ⬜ **Cloud sync** — once Phase 1 lands, sync the journal to the account so it
  follows the user across devices. **M.**
- ⬜ **Analyze-from-journal** — one tap to reload a logged trade back into the
  analyzer. **S.**
- 💡 Auto-populate journal entries from broker fills (depends on Phase 4).

---

## Phase 4 — Broker portfolio connection (L–XL)

Import a user's real positions to analyze them in OptPoP. Sequenced easiest → hardest.

- ⬜ **Tradier account positions (first)** — the Tradier connection already exists;
  add the positions/account endpoints to pull the user's real option positions
  and load them into the analyzer. **M.** (Needs a Tradier *account* token, not
  just market-data.)
- ⬜ **Multi-broker via an aggregator** — use a brokerage-aggregation API
  (e.g., SnapTrade) to connect Schwab, Fidelity, Robinhood, Tastytrade, IBKR,
  etc. through one integration. **XL.**
  - Requires: Phase 1 accounts, a paid aggregator plan, secure server-side token
    storage, and read-only scopes.
  - Risks: each broker's options data/format differs; OAuth flows; ongoing cost;
    compliance/ToS review before handling customer brokerage data.
- ⬜ **Direct broker APIs (alternative/complement)** — Schwab (approved developer
  OAuth), Tastytrade, IBKR Client Portal. **XL**, and per-broker.
- Note: read-only positions first; **no order placement** until there's a strong
  reason and the added risk/liability is worth it.

---

## Phase 5 — Backtesting (L–XL, data-gated)

- ⬜ **Model-based backtest (first, feasible now)** — replay a strategy over
  historical *underlying* prices (available via Tradier/other), re-pricing the
  option legs each day with the existing Black–Scholes engine and a vol
  assumption (realized vol, or a simple IV model). **L.**
  - Honest framing: approximate — it does not use historical option quotes, so
    it can't capture real bid/ask, skew, or IV crush precisely. Label it clearly.
- ⬜ **Historical-options backtest (true)** — use real historical option chains
  (e.g., ORATS / Polygon options / CBOE DataShop). **XL.**
  - Gated by **paid historical options data** (the main cost/complexity), plus
    heavier compute and storage.
- 💡 Strategy screener: scan an underlying's history for setups meeting rules.

---

## Backlog / ideas (unsorted)

- 💡 IV rank / IV percentile vs. the past year (context for the rich/thin-IV recs)
- 💡 Saved positions & shareable read-only links
- 💡 Alerts (price/IV/probability thresholds) — needs accounts + a scheduler
- 💡 Earnings-date awareness in the chain picker and recommendations
- 💡 Assignment/early-exercise risk notes for American options
- 💡 Additional data providers behind the existing provider interface
- 💡 Native Android build (Tauri) + Google Play listing
- 💡 App Store listing (requires Apple Developer Program + StoreKit IAP)

---

## Cross-cutting / tech debt

- ⬜ Cross-device Pro entitlement (resolved by Phase 1 accounts)
- ⬜ Gate the Stripe Customer Portal behind auth (currently trusts client customer id)
- ⬜ Broaden automated tests as features land (keep the math + integration suite green)
- ⬜ Accessibility pass on new charts (keyboard, table-view twins) as they're added

---

_How this is tracked: this file is the source of truth. When something ships,
move it to **Shipped** with a date and check it off. Larger phases can graduate
to GitHub Issues/milestones if that becomes useful._
