import { beforeEach, describe, expect, it } from 'vitest'
import { adSlotId, adsenseConfigured, adsVisible, stripeConfigured } from '../config/monetization'
import { isTauri, isWebBrowser } from './platform'
import { getPurchaseProvider, MockPurchaseProvider, type KeyValueStore } from './purchases'

function memoryStore(): KeyValueStore {
  const map = new Map<string, string>()
  return {
    getItem: (k) => map.get(k) ?? null,
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
  }
}

describe('adsVisible', () => {
  it('shows ads only to non-Pro users', () => {
    expect(adsVisible(false)).toBe(true)
    expect(adsVisible(true)).toBe(false)
  })
})

describe('MockPurchaseProvider', () => {
  let provider: MockPurchaseProvider
  beforeEach(() => {
    provider = new MockPurchaseProvider(memoryStore())
  })

  it('starts without entitlement', async () => {
    expect(await provider.checkEntitlement()).toBe(false)
  })

  it('grants Pro on purchase and persists it', async () => {
    expect(await provider.purchase()).toBe(true)
    expect(await provider.checkEntitlement()).toBe(true)
  })

  it('restore reflects a prior purchase', async () => {
    expect(await provider.restore()).toBe(false)
    await provider.purchase()
    expect(await provider.restore()).toBe(true)
  })

  it('clear removes the entitlement', async () => {
    await provider.purchase()
    await provider.clear()
    expect(await provider.checkEntitlement()).toBe(false)
  })

  it('two providers over the same store share entitlement', async () => {
    const store = memoryStore()
    const a = new MockPurchaseProvider(store)
    const b = new MockPurchaseProvider(store)
    await a.purchase()
    expect(await b.checkEntitlement()).toBe(true)
  })
})

describe('config gating (unconfigured by default in tests)', () => {
  it('adsense and stripe are off without env vars', () => {
    expect(adsenseConfigured()).toBe(false)
    expect(stripeConfigured()).toBe(false)
    expect(adSlotId('content-top')).toBe('')
    expect(adSlotId('nonexistent')).toBe('')
  })
})

describe('platform detection (node/test env)', () => {
  it('is neither web nor Tauri without a window', () => {
    expect(isWebBrowser()).toBe(false)
    expect(isTauri()).toBe(false)
  })
})

describe('getPurchaseProvider', () => {
  it('falls back to the mock provider when Stripe is unconfigured', () => {
    expect(getPurchaseProvider().name).toBe('mock')
  })
})
