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
export interface PurchaseProvider {
  readonly name: string
  /** Resolve the current entitlement (verified, in a real provider). */
  checkEntitlement(): Promise<boolean>
  /** Start the purchase flow; resolves true when Pro is granted. */
  purchase(): Promise<boolean>
  /** Restore a prior purchase on this account/device. */
  restore(): Promise<boolean>
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

  /** Testing/support affordance — not part of the public flow. */
  async clear(): Promise<void> {
    this.store.removeItem(PRO_KEY)
  }
}

/**
 * Select the provider for the current platform. Today always the mock; the
 * commented branches are where real providers slot in once their SDKs and
 * accounts exist.
 */
export function getPurchaseProvider(): PurchaseProvider {
  const store: KeyValueStore =
    typeof localStorage !== 'undefined'
      ? localStorage
      : { getItem: () => null, setItem: () => {}, removeItem: () => {} }

  // if (isTauriIOS()) return new StoreKitPurchaseProvider()
  // else if (isTauriAndroid()) return new PlayBillingPurchaseProvider()
  // else if (isWeb()) return new StripePurchaseProvider()
  return new MockPurchaseProvider(store)
}
