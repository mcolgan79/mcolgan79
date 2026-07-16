import { ADSENSE } from '../config/monetization'

/**
 * Loads the Google AdSense library once and pushes ad units. No-op unless a
 * publisher id is configured and we're in a browser — so it never runs in the
 * Tauri shell or in tests.
 */
let scriptLoading = false

export function loadAdSense(): void {
  if (scriptLoading || typeof document === 'undefined' || !ADSENSE.client) return
  if (document.querySelector('script[data-adsense]')) {
    scriptLoading = true
    return
  }
  scriptLoading = true
  const s = document.createElement('script')
  s.async = true
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE.client}`
  s.crossOrigin = 'anonymous'
  s.setAttribute('data-adsense', '1')
  document.head.appendChild(s)
}

/** Ask AdSense to fill the most recently rendered <ins> unit. */
export function pushAd(): void {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any
    ;(w.adsbygoogle = w.adsbygoogle || []).push({})
  } catch {
    /* AdSense not ready / blocked — placeholder stays */
  }
}
