import { useEffect, useState } from 'react'
import { MONETIZATION } from '../config/monetization'
import { useEntitlement } from '../lib/entitlement'

interface Props {
  open: boolean
  onClose: () => void
}

/**
 * Paywall. Today it drives the mock purchase provider (flips the local Pro
 * flag). When real billing is wired, `upgrade()`/`restore()` from the
 * entitlement context call StoreKit / Play Billing / Stripe instead — this UI
 * doesn't change.
 */
export function UpgradeDialog({ open, onClose }: Props) {
  const { isPro, loading, upgrade, restore, manage } = useEntitlement()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }
  const doUpgrade = () => run(upgrade)
  const doRestore = () => run(restore)
  const doManage = () => run(manage)

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upgrade-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="modal-close" aria-label="Close" onClick={onClose}>
          ✕
        </button>
        {isPro ? (
          <>
            <h2 id="upgrade-title">You’re on {MONETIZATION.productName} ✓</h2>
            <p className="modal-sub">Ads are off. Thanks for supporting OptPoP.</p>
            <button className="btn-primary" onClick={doManage} disabled={busy || loading}>
              {busy ? 'Opening…' : 'Manage subscription'}
            </button>
            {error ? <p className="input-error">{error}</p> : null}
            <button className="btn-link" onClick={onClose}>
              Done
            </button>
          </>
        ) : (
          <>
            <h2 id="upgrade-title">{MONETIZATION.productName}</h2>
            <p className="modal-sub">
              Remove ads for {MONETIZATION.priceLabel}. Every analysis feature is already
              free — this just clears the ads and supports development.
            </p>
            <ul className="benefits">
              {MONETIZATION.benefits.map((b) => (
                <li key={b}>
                  <span aria-hidden>✓</span> {b}
                </li>
              ))}
            </ul>
            <button className="btn-primary" onClick={doUpgrade} disabled={busy || loading}>
              {busy ? 'Processing…' : `Subscribe — ${MONETIZATION.priceLabel}`}
            </button>
            <button className="btn-link" onClick={doRestore} disabled={busy || loading}>
              Restore purchase
            </button>
            {error ? <p className="input-error">{error}</p> : null}
            <p className="modal-fineprint">
              Demo checkout — no real charge yet. Billing (App Store / Google Play /
              Stripe) is wired before public launch. Subscriptions renew until cancelled;
              cancel anytime in your store account.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
