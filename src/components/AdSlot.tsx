import { useEffect, useRef } from 'react'
import { ADSENSE, adSlotId, adsenseConfigured, adsVisible } from '../config/monetization'
import { loadAdSense, pushAd } from '../lib/adsense'
import { useEntitlement } from '../lib/entitlement'
import { isWebBrowser } from '../lib/platform'

export type AdFormat = 'banner' | 'rectangle'

interface Props {
  /** Stable id for the placement; maps to an AdSense data-ad-slot in config. */
  placement: string
  format?: AdFormat
  onUpgrade: () => void
}

/**
 * An ad placement. Renders nothing for Pro users. For free users it serves a
 * real Google AdSense unit when: we're on the web (not the Tauri shell), a
 * publisher id + slot id are configured, and the network isn't blocked. Until
 * then (dev, unconfigured, or ad-blocked) it shows a labeled placeholder so the
 * layout is always sound.
 */
export function AdSlot({ placement, format = 'banner', onUpgrade }: Props) {
  const { isPro } = useEntitlement()
  const slot = adSlotId(placement)
  const serveReal = adsVisible(isPro) && isWebBrowser() && adsenseConfigured() && !!slot
  const pushed = useRef(false)

  useEffect(() => {
    if (!serveReal || pushed.current) return
    pushed.current = true
    loadAdSense()
    pushAd()
  }, [serveReal])

  if (!adsVisible(isPro)) return null

  return (
    <aside className={`ad-slot ad-${format}`} data-placement={placement} aria-label="Advertisement">
      <span className="ad-badge">Ad</span>
      {serveReal ? (
        <ins
          className="adsbygoogle"
          style={{ display: 'block', width: '100%' }}
          data-ad-client={ADSENSE.client}
          data-ad-slot={slot}
          data-ad-format="auto"
          data-full-width-responsive="true"
        />
      ) : (
        <div className="ad-body">
          <span className="ad-placeholder-text">Your ad could be here</span>
        </div>
      )}
      <button className="ad-remove" onClick={onUpgrade}>
        Remove ads
      </button>
    </aside>
  )
}
