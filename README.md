# OptPoP

**Options probability & risk analyzer** — build a position from one to six legs
(templates for verticals, iron condors, calendars, and diagonals included), give
each leg a strike, DTE, and either an implied volatility or a market premium, and
OptPoP shows you what the strategy really looks like:

- **Multi-leg strategies** — single options, credit/debit verticals, iron condors,
  straddles/strangles, calendars, diagonals, or any custom combination. Positions
  with mixed expirations are evaluated at the *front* expiration, with longer-dated
  legs marked to model — so calendar/diagonal tents render properly.
- **Risk & reward** — interactive payoff diagram with the at-horizon curve, the
  T+0 (today) mark-to-model curve, profit/loss shading, every breakeven and strike,
  spot, and the ±1σ expected-move band.
- **POP** — probability the position is profitable at the horizon, integrated
  exactly over the (possibly multiple) profit intervals.
- **P50** — probability of reaching 50% of max profit (or a 50% return on the debit
  when profit is unbounded) *at any point before the front expiration*, estimated
  with a seeded Monte Carlo that marks every leg to model daily.
- **Probability of touch** — chance the underlying trades through each breakeven
  before the horizon (closed-form first-passage under GBM).
- **Probability distribution** — the lognormal terminal distribution implied by the
  position's vega-weighted IV, with the profitable slices shaded (their combined
  area *is* the POP).
- **Greeks** — net position delta, gamma, theta, vega, rho, per share and in
  dollars, each leg at its own tenor and IV.
- **Trade check** — a heuristics engine that recognizes the structure (vertical,
  condor, calendar, …) and flags naked shorts, thin credit-to-width, short strikes
  inside the expected move, gamma-heavy DTE, rich/thin IV regimes, and poor
  reward-for-risk, with concrete improvements.
- **Live market data (bring your own key)** — connect a free
  [Tradier](https://developer.tradier.com) token, type a symbol, and build legs
  straight from the real option chain: expiration and strike pickers auto-fill
  spot, DTE, IV, and the bid/ask-mid premium, with one-tap refresh. The token is
  stored only on the user's device and every request goes directly from their
  device to Tradier — OptPoP never proxies, stores, or redistributes market data.

Every chart has a hover/keyboard crosshair with tooltips, a table view, and full
light/dark theming. All math is dependency-free TypeScript with a Vitest suite that
cross-checks the closed forms against Monte Carlo.

> ⚠️ Educational tool. Probabilities assume Black–Scholes (lognormal) dynamics at
> the IV you enter — real markets have skew, jumps, and events. Not financial advice.

## Live data setup (optional)

1. Create a free account at [developer.tradier.com](https://developer.tradier.com)
   and copy the **sandbox access token** (15-minute-delayed data, no brokerage
   account needed). A Tradier brokerage account's production token gets real-time
   data instead.
2. In OptPoP, open **Live data (Tradier) → API key**, paste the token, and
   connect a symbol. Each leg then offers expiration and chain-strike pickers.

Without a key the app works fully in manual mode — you supply price, IV, and
premiums yourself.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # math test suite
npm run build      # production web build in dist/
```

## On your phone (iOS & Android)

### The easy way — install the PWA (no Mac, no App Store, no cost)

OptPoP is an installable PWA that runs full-screen and works offline.

1. Get it to an HTTPS URL: the **Deploy web (PWA)** workflow publishes it to
   GitHub Pages, or deploy `dist/` to Netlify / Cloudflare Pages. (To just try it
   on your own phone, run `npm run preview -- --host` and open the shown LAN
   address in the phone's browser.)
2. **iPhone:** open the URL in **Safari** → **Share** → **Add to Home Screen**.
   **Android:** open in **Chrome** → menu → **Install app / Add to Home Screen**.

It then launches from its own icon like a native app, including live Tradier
data. This is the recommended path for a public launch — no review, no fees.

### The native way — a real App Store app (Tauri, needs a Mac + Apple account)

Tauri 2 wraps the same code into a native binary. Building and installing on iOS
**requires a Mac with Xcode and an Apple Developer Program membership ($99/yr)**;
there is no way around Apple's signing requirement.

```bash
npx tauri ios init     # generates the Xcode project under src-tauri/gen/apple
npx tauri ios dev      # run in the iOS Simulator
npx tauri ios build    # build a signed .ipa (select your Apple team first)
```

The **Build iOS** GitHub Actions workflow can do a *simulator* build with no
Apple account (to confirm it compiles) and a *device* build once you add your
Apple signing secrets — see the comments at the top of
`.github/workflows/build-ios.yml`. Android is analogous:
`npx tauri android init && npx tauri android build`.

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
| Fair value / Greeks | Black–Scholes–Merton per leg (own tenor & IV), continuous rate `r` and dividend yield `q` |
| Horizon payoff | Evaluated at the front expiration; longer-dated legs marked to model with their remaining tenor |
| Breakevens / max P&L | Log-spaced grid + bisection-refined zero crossings, with analytic tail handling (net call exposure ⇒ unbounded sides) |
| Underlying vol | Vega-weighted average of the legs' IVs |
| Implied vol | Newton–Raphson on vega with bisection fallback, no-arbitrage bounds checked |
| POP | Lognormal probability mass of the profit intervals under GBM with risk-neutral drift |
| Probability of touch | Closed-form first-passage (reflection principle with drift) |
| P50 | Monte Carlo: daily GBM steps, every leg repriced with BS each day, path counts a hit when open P&L reaches the target |
| Expected move | `S · σ · √T` to the front expiration |

The test suite (`src/lib/math.test.ts`) pins the textbook BS values, put–call
parity, finite-difference Greeks, and agreement between the closed-form
probabilities and Monte Carlo simulation.

## Stack

React 18 + TypeScript + Vite. Charts are hand-rolled responsive SVG (no chart
library). PWA via a small service worker; desktop/mobile shells via Tauri 2.

## Monetization (free with ads · Pro removes them)

OptPoP is free with ads; an **OptPoP Pro** subscription removes them. Ads are the
*only* difference — every analytical feature stays free. The architecture is in
place and provider-agnostic; the placeholders are ready to swap for real
services:

| Piece | File | Status |
|---|---|---|
| Entitlement state (single "is Pro?" source) | `src/lib/entitlement.tsx` | ✅ working |
| Purchase abstraction (interface + mock) | `src/lib/purchases.ts` | ✅ mock; real providers slot in |
| Ad slot (placeholder → real ad unit) | `src/components/AdSlot.tsx` | ✅ placeholder |
| Paywall UI | `src/components/UpgradeDialog.tsx` | ✅ working (mock checkout) |
| Prices / product IDs | `src/config/monetization.ts` | ⚙️ placeholders to fill |

### Web (AdSense + Stripe) — wired, needs your keys

The web/PWA path is implemented end to end and activates from build-time env
vars (see [`.env.example`](./.env.example)). With none set, ads show
placeholders and checkout uses the local mock, so the app always builds.

**AdSense** — create a publisher account, add an ad unit per placement, then set
at build time:

```
VITE_ADSENSE_CLIENT=ca-pub-…          # your publisher id
VITE_ADSENSE_SLOT_TOP=…               # data-ad-slot for the top banner
VITE_ADSENSE_SLOT_BOTTOM=…            # data-ad-slot for the bottom banner
```

Also put your real `ads.txt` line (from the AdSense console) into
[`public/ads.txt`](./public/ads.txt), and approve your domain in AdSense. Ads
render only on the web — never in the Tauri app (its CSP blocks them by design).

**Stripe** — create a recurring Price for OptPoP Pro, then:

1. Set the client flag at build time: `VITE_STRIPE_PUBLISHABLE_KEY=pk_…`
2. Deploy the serverless backend in [`functions/api/`](./functions/api) (written
   as **Cloudflare Pages Functions**, zero-dependency Stripe REST calls). Set
   these **server-side secrets** (never `VITE_`): `STRIPE_SECRET_KEY`,
   `STRIPE_PRICE_ID`, and optionally `PUBLIC_BASE_URL`.
3. `StripePurchaseProvider` redirects to Stripe Checkout and verifies the
   subscription against Stripe on return and on every load — the client flag is
   never trusted. The functions port directly to Vercel/Netlify (same
   `/api/*` routes).

**Webhook + KV (production hardening).** `functions/api/stripe-webhook.ts`
verifies Stripe's signature (Web Crypto HMAC, replay-protected — see
`src/lib/stripe-signature.ts`, unit-tested) and records each customer's ad-free
state in Cloudflare KV. `subscription-status` then answers from that durable
cache and only falls back to a live Stripe query on a cache miss, so
cancellations/payment failures take effect immediately and most loads never
call Stripe. To enable:

1. Create a KV namespace and bind it to the Pages project as **`ENTITLEMENTS`**
   (Settings → Functions → KV namespace bindings).
2. Stripe → Developers → Webhooks → add endpoint
   `https://<your-site>/api/stripe-webhook`, subscribe to
   `checkout.session.completed`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.payment_failed`.
3. Set **`STRIPE_WEBHOOK_SECRET`** (`whsec_…`) as a server secret.

Without the binding/secret the webhook is a safe no-op and live verification
still works.

**Manage / cancel.** Pro users tap the **Pro ✓** badge → **Manage subscription**,
which opens the Stripe Billing Customer Portal (`functions/api/create-portal-session.ts`)
to update the card, view invoices, or cancel. Enable it once in Stripe →
Settings → Billing → Customer portal. (Same no-account caveat as above: it
trusts the client-supplied customer id — gate it behind user auth before a real
launch, since the portal can cancel a subscription.)

**Going live.** Flip Stripe to Live mode, create the live Product/Price, and
swap the test `pk_`/`sk_`/`price_`/`whsec_` values for live ones in the host's
env — then redeploy.

**Cross-device caveat:** entitlement is keyed to the Stripe customer id stored
on the device, a solid MVP that doesn't sync across a user's devices. True
multi-device requires user accounts (sign-in / magic link) so the customer id
binds to an identity.

### Native iOS/Android (later)

**iOS must use Apple in-app purchase (StoreKit)** for digital subscriptions —
Apple requires it and takes 15–30%; Android uses Google Play Billing.
[RevenueCat](https://www.revenuecat.com) wraps both behind one SDK. Implement
`PurchaseProvider` for the platform and return it from `getPurchaseProvider()`;
nothing else changes.

## License

**Proprietary — © 2026 Pera Pera, Inc. All rights reserved.** This is not
open-source software. No permission is granted to use, copy, modify, or
distribute the Software except under a separate written agreement. See
[`LICENSE`](./LICENSE) for the full terms. Third-party dependencies remain under
their own licenses. For licensing inquiries, contact michael.colgan@gmail.com.
