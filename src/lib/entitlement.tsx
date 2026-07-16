import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getPurchaseProvider, MockPurchaseProvider, type PurchaseProvider } from './purchases'

export interface Entitlement {
  /** Ad-free subscriber. */
  isPro: boolean
  /** Entitlement still being resolved (first load / purchase in flight). */
  loading: boolean
  /** Run the purchase flow; returns whether Pro was granted. */
  upgrade: () => Promise<boolean>
  /** Restore a previous purchase. */
  restore: () => Promise<boolean>
  /** Dev/QA only: drop the local entitlement (mock provider). */
  resetForTesting: () => Promise<void>
}

const Ctx = createContext<Entitlement | null>(null)

export function EntitlementProvider({
  children,
  provider = getPurchaseProvider(),
}: {
  children: ReactNode
  provider?: PurchaseProvider
}) {
  const [isPro, setIsPro] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    provider
      .checkEntitlement()
      .then((v) => alive && setIsPro(v))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [provider])

  const upgrade = useCallback(async () => {
    setLoading(true)
    try {
      const ok = await provider.purchase()
      if (ok) setIsPro(true)
      return ok
    } finally {
      setLoading(false)
    }
  }, [provider])

  const restore = useCallback(async () => {
    setLoading(true)
    try {
      const ok = await provider.restore()
      setIsPro(ok)
      return ok
    } finally {
      setLoading(false)
    }
  }, [provider])

  const resetForTesting = useCallback(async () => {
    if (provider instanceof MockPurchaseProvider) await provider.clear()
    setIsPro(false)
  }, [provider])

  const value = useMemo(
    () => ({ isPro, loading, upgrade, restore, resetForTesting }),
    [isPro, loading, upgrade, restore, resetForTesting],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useEntitlement(): Entitlement {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useEntitlement must be used within EntitlementProvider')
  return ctx
}
