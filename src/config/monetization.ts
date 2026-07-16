/**
 * Central monetization config. OptPoP is free with ads; a "Pro" subscription
 * removes them. Ads are the ONLY difference between tiers — every analytical
 * feature stays available to free users.
 *
 * The product IDs below are placeholders. To go live you create the matching
 * products in each store/provider and drop the real IDs here:
 *   - iOS  : App Store Connect auto-renewable subscription (StoreKit)
 *   - Android: Google Play Console subscription (Play Billing)
 *   - Web  : a Stripe Price (Checkout / Billing)
 */
export const MONETIZATION = {
  productName: 'OptPoP Pro',
  /** Display price; keep in sync with the real store prices. */
  priceLabel: '$2.99/mo',
  benefits: ['Remove all ads', 'Support ongoing development'],
  productIds: {
    ios: 'com.perapera.optpop.pro.monthly',
    android: 'optpop_pro_monthly',
    stripePriceId: '', // fill when Stripe is wired
  },
} as const

/**
 * The single rule for whether ads render. Pure so it is trivially testable and
 * has exactly one meaning across the whole app.
 */
export function adsVisible(isPro: boolean): boolean {
  return !isPro
}
