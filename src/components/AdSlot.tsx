import { adsVisible } from '../config/monetization'
import { useEntitlement } from '../lib/entitlement'

export type AdFormat = 'banner' | 'rectangle'

interface Props {
  /** Stable id for the placement (maps to an ad unit once a network is wired). */
  placement: string
  format?: AdFormat
  onUpgrade: () => void
}

/**
 * An ad placement. Renders nothing for Pro users. For free users it shows a
 * labeled placeholder today; to serve real ads, replace the placeholder markup
 * with the network's unit (AdSense `<ins class="adsbygoogle">` on web, or the
 * AdMob native SDK view on iOS/Android) keyed by `placement`. The "Remove ads"
 * link and the Pro gate around it stay exactly as they are.
 */
export function AdSlot({ placement, format = 'banner', onUpgrade }: Props) {
  const { isPro } = useEntitlement()
  if (!adsVisible(isPro)) return null
  return (
    <aside
      className={`ad-slot ad-${format}`}
      data-placement={placement}
      aria-label="Advertisement"
    >
      <span className="ad-badge">Ad</span>
      <div className="ad-body">
        <span className="ad-placeholder-text">Your ad could be here</span>
      </div>
      <button className="ad-remove" onClick={onUpgrade}>
        Remove ads
      </button>
    </aside>
  )
}
