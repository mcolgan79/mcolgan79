/**
 * Central monetization config. OptPoP is free with ads; a "Pro" subscription
 * removes them. Ads are the ONLY difference between tiers — every analytical
 * feature stays available to free users.
 *
 * Web (AdSense + Stripe) is wired here and driven by build-time env vars
 * (VITE_*, set in your host's build settings). When they're absent everything
 * degrades gracefully: ads fall back to placeholders and checkout falls back to
 * the local mock, so the app always builds and runs.
 *
 * Native iOS/Android billing (StoreKit / Play Billing) is a separate provider.
 */

const env = import.meta.env

export const MONETIZATION = {
  productName: 'OptPoP Pro',
  /** Display price; keep in sync with the real Stripe/store price. */
  priceLabel: '$2.99/mo',
  benefits: ['Remove all ads', 'Support ongoing development'],
} as const

/* ---------------- AdSense (web ads) ---------------- */

export const ADSENSE = {
  /** Publisher id, e.g. "ca-pub-1234567890123456". */
  client: (env.VITE_ADSENSE_CLIENT as string | undefined) ?? '',
  /** data-ad-slot per placement id used in the app. */
  slots: {
    'content-top': (env.VITE_ADSENSE_SLOT_TOP as string | undefined) ?? '',
    'content-bottom': (env.VITE_ADSENSE_SLOT_BOTTOM as string | undefined) ?? '',
  } as Record<string, string>,
}

/** AdSense is usable only with a publisher id configured. */
export function adsenseConfigured(): boolean {
  return ADSENSE.client.startsWith('ca-pub-')
}

export function adSlotId(placement: string): string {
  return ADSENSE.slots[placement] ?? ''
}

/* ---------------- Stripe (web payments) ---------------- */

export const STRIPE = {
  /** Publishable key (pk_...); its presence flags Stripe as enabled. */
  publishableKey: (env.VITE_STRIPE_PUBLISHABLE_KEY as string | undefined) ?? '',
}

export function stripeConfigured(): boolean {
  return STRIPE.publishableKey.startsWith('pk_')
}

/* ---------------- Ad visibility rule ---------------- */

/**
 * The single rule for whether ads render. Pure so it is trivially testable and
 * has exactly one meaning across the whole app.
 */
export function adsVisible(isPro: boolean): boolean {
  return !isPro
}
