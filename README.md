# OptPoP

**Options probability & risk analyzer** — enter an underlying price, strike, days to
expiration, and either an implied volatility or a market premium, and OptPoP shows
you what a long or short call/put position really looks like:

- **Risk & reward** — interactive payoff diagram with the at-expiration curve, the
  T+0 (today) mark-to-model curve, profit/loss shading, breakeven, strike, spot, and
  the ±1σ expected-move band.
- **POP** — probability the position is profitable at expiration.
- **P50** — probability of reaching 50% of max profit (short) or a 50% return on the
  debit (long) *at any point before expiration*, estimated with a seeded 4,000-path
  Monte Carlo that marks the option to model daily.
- **Probability of touch** — chance the underlying trades through the strike or the
  breakeven before expiration (closed-form first-passage under GBM).
- **Probability distribution** — the lognormal terminal distribution implied by your
  IV, with the profitable slice shaded (its area *is* the POP).
- **Greeks** — position delta, gamma, theta, vega, rho, per share and in dollars.
- **Trade check** — a heuristics engine that flags undefined risk, gamma-heavy DTE,
  aggressive deltas, thin reward-for-risk, rich/thin IV regimes, and suggests
  concrete improvements (defined-risk spreads, strike/DTE adjustments, profit
  targets).

Every chart has a hover/keyboard crosshair with tooltips, a table view, and full
light/dark theming. All math is dependency-free TypeScript with a Vitest suite that
cross-checks the closed forms against Monte Carlo.

> ⚠️ Educational tool. Probabilities assume Black–Scholes (lognormal) dynamics at
> the IV you enter — real markets have skew, jumps, and events. Not financial advice.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # math test suite
npm run build      # production web build in dist/
```

## On your phone

OptPoP is an installable PWA (works offline):

1. Deploy `dist/` to any static host (GitHub Pages, Netlify, …) — or run
   `npm run preview` on your LAN.
2. Open it in Safari (iOS) or Chrome (Android) and choose **Add to Home Screen /
   Install app**. It launches full-screen like a native app.

For fully native mobile binaries, Tauri 2 can wrap the same code:
`npx tauri android init && npx tauri android build` (or `ios` on a Mac with Xcode).

## Windows .exe / macOS .app

The desktop shell is [Tauri 2](https://v2.tauri.app) (`src-tauri/`). With
[Rust installed](https://rustup.rs):

```bash
npx tauri icon public/icon-512.png   # one-time: generate bundle icons
npx tauri dev                        # run as a desktop app
npx tauri build                      # installer for the OS you're on
```

- On **Windows** this produces an `.exe`/`.msi` installer under
  `src-tauri/target/release/bundle/`.
- On **macOS** it produces an `.app` and `.dmg`.

No local toolchain? Push a tag like `v0.1.0` (or run the **Desktop builds** workflow
manually) and GitHub Actions builds Windows, macOS (Intel + Apple Silicon), and
Linux installers via `tauri-action` and attaches them to a draft release.

## How the numbers are computed

| Quantity | Method |
|---|---|
| Fair value / Greeks | Black–Scholes–Merton with continuous rate `r` and dividend yield `q` |
| Implied vol | Newton–Raphson on vega with bisection fallback, no-arbitrage bounds checked |
| POP | `P(S_T beyond breakeven)` under GBM with risk-neutral drift |
| Probability of touch | Closed-form first-passage (reflection principle with drift) |
| P50 | Monte Carlo: daily GBM steps, option repriced with BS at each day's remaining tenor, path counts a hit when open P&L reaches the target |
| Expected move | `S · σ · √T` |

The test suite (`src/lib/math.test.ts`) pins the textbook BS values, put–call
parity, finite-difference Greeks, and agreement between the closed-form
probabilities and Monte Carlo simulation.

## Stack

React 18 + TypeScript + Vite. Charts are hand-rolled responsive SVG (no chart
library). PWA via a small service worker; desktop/mobile shells via Tauri 2.
