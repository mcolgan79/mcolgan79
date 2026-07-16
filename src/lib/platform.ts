/**
 * Where is the app running? Web ads (AdSense) and web payments (Stripe) must
 * run ONLY in a real browser / PWA — never inside the Tauri native shell, whose
 * strict CSP blocks third-party scripts and whose store rules (Apple IAP)
 * forbid external payment flows. Native billing uses StoreKit / Play Billing
 * instead (added separately).
 */

/** True inside the Tauri (desktop/iOS/Android) webview. */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && ('__TAURI_INTERNALS__' in window || '__TAURI__' in window)
}

/** True when running as an ordinary web page or installed PWA (not Tauri). */
export function isWebBrowser(): boolean {
  return typeof window !== 'undefined' && typeof document !== 'undefined' && !isTauri()
}
