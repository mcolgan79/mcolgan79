/**
 * Purchase abstraction. The app talks to this interface, never to a specific
 * store, so real billing can be added per platform without touching the UI:
 *
 *   - Web / PWA  → Stripe Checkout + a tiny backend that verifies the session
 *   - iOS (Tauri)→ StoreKit 2 (Apple requires in-app purchase for digital goods)
 *   - Android    → Google Play Billing
 *   - Cross-platform shortcut → RevenueCat wraps StoreKit + Play behind one SDK
 *
 * Until one of those is wired, `MockPurchaseProvider` persists the entitlement
 * locally so the whole Free/Pro UX is testable end to end.
 *
 * SECURITY NOTE: local state is client-editable and must NOT be the source of
 * truth in production — a real provider verifies the receipt/subscription with
 * the store (or your backend) in `checkEntitlement()`.
 */
import { stripeConfigured } from '../config/monetization'
import { isWebBrowser } from './platform'

export interface PurchaseProvider {
  readonly name: string
  /** Resolve the current entitlement (verified, in a real provider). */
  checkEntitlement(): Promise<boolean>
  /** Start the purchase flow; resolves true when Pro is granted. */
  purchase(): Promise<boolean>
  /** Restore a prior purchase on this account/device. */
  restore(): Promise<boolean>
  /** Open subscription management (cancel / update card / invoices). */
  manage(): Promise<void>
}

export interface KeyValueStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const PRO_KEY = 'optpop-pro'

/**
 * Local-only provider for development and the pre-billing release. Storage is
 * injectable so it can be unit-tested without a browser.
 */
export class MockPurchaseProvider implements PurchaseProvider {
  readonly name = 'mock'
  constructor(private store: KeyValueStore) {}

  async checkEntitlement(): Promise<boolean> {
    return this.store.getItem(PRO_KEY) === 'true'
  }

  async purchase(): Promise<boolean> {
    this.store.setItem(PRO_KEY, 'true')
    return true
  }

  async restore(): Promise<boolean> {
    return this.checkEntitlement()
  }

  /** No real billing to manage locally; clearing lets you re-test the flow. */
  async manage(): Promise<void> {
    await this.clear()
  }

  /** Testing/support affordance — not part of the public flow. */
  async clear(): Promise<void> {
    this.store.removeItem(PRO_KEY)
  }
}

const STRIPE_CUSTOMER_KEY = 'optpop-stripe-customer'

/**
 * Web subscriptions via Stripe Checkout. `purchase()` asks the backend to
 * create a Checkout Session and redirects to it; Stripe returns the user to
 * `?checkout=success&session_id=…`, which `checkEntitlement()` verifies with
 * the backend and then remembers the Stripe customer id to re-verify on future
 * loads. All secret-key work happens server-side (see functions/api/*).
 */
export class StripePurchaseProvider implements PurchaseProvider {
  readonly name = 'stripe'
  constructor(
    private store: KeyValueStore,
    private api = '/api',
  ) {}

  async checkEntitlement(): Promise<boolean> {
    // Returning from Checkout?
    if (typeof location !== 'undefined') {
      const params = new URLSearchParams(location.search)
      const sessionId = params.get('session_id')
      if (params.get('checkout') === 'success' && sessionId) {
        const data = await this.status({ session_id: sessionId })
        if (data.customerId) this.store.setItem(STRIPE_CUSTOMER_KEY, data.customerId)
        this.stripQuery()
        return data.pro
      }
      if (params.get('checkout') === 'cancel') this.stripQuery()
    }
    const customer = this.store.getItem(STRIPE_CUSTOMER_KEY)
    if (!customer) return false
    const data = await this.status({ customer })
    if (!data.pro) this.store.removeItem(STRIPE_CUSTOMER_KEY)
    return data.pro
  }

  async purchase(): Promise<boolean> {
    const res = await fetch(`${this.api}/create-checkout-session`, { method: 'POST' })
    if (!res.ok) throw new Error('Could not start checkout. Please try again.')
    const { url } = (await res.json()) as { url?: string }
    if (!url) throw new Error('Checkout is unavailable right now.')
    location.assign(url) // leaves the app; entitlement is granted on return
    return false
  }

  async restore(): Promise<boolean> {
    return this.checkEntitlement()
  }

  async manage(): Promise<void> {
    const customer = this.store.getItem(STRIPE_CUSTOMER_KEY)
    if (!customer) return
    const res = await fetch(`${this.api}/create-portal-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer }),
    })
    if (!res.ok) throw new Error('Could not open the billing portal.')
    const { url } = (await res.json()) as { url?: string }
    if (url) location.assign(url)
  }

  private async status(query: Record<string, string>): Promise<{ pro: boolean; customerId?: string }> {
    try {
      const qs = new URLSearchParams(query).toString()
      const res = await fetch(`${this.api}/subscription-status?${qs}`)
      if (!res.ok) return { pro: false }
      return (await res.json()) as { pro: boolean; customerId?: string }
    } catch {
      return { pro: false }
    }
  }

  private stripQuery() {
    if (typeof history !== 'undefined' && typeof location !== 'undefined') {
      history.replaceState({}, '', location.pathname)
    }
  }
}

/**
 * Select the provider for the current platform:
 *   - web + Stripe configured → Stripe Checkout
 *   - otherwise → local mock (dev, unconfigured, or native shells until
 *     StoreKit / Play Billing providers are added)
 */
export function getPurchaseProvider(): PurchaseProvider {
  const store: KeyValueStore =
    typeof localStorage !== 'undefined'
      ? localStorage
      : { getItem: () => null, setItem: () => {}, removeItem: () => {} }

  if (isWebBrowser() && stripeConfigured()) return new StripePurchaseProvider(store)
  // if (isTauriIOS()) return new StoreKitPurchaseProvider()
  // if (isTauriAndroid()) return new PlayBillingPurchaseProvider()
  return new MockPurchaseProvider(store)
}
