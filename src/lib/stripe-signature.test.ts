import { describe, expect, it } from 'vitest'
import { parseSignatureHeader, signPayload, verifyStripeSignature } from './stripe-signature'

const SECRET = 'whsec_test_0123456789abcdef'
const BODY = JSON.stringify({ id: 'evt_1', type: 'checkout.session.completed' })
const NOW = 1_700_000_000_000 // fixed ms
const TS = Math.floor(NOW / 1000)

describe('parseSignatureHeader', () => {
  it('reads t and one or more v1 values', () => {
    expect(parseSignatureHeader('t=123,v1=abc')).toEqual({ t: '123', v1: ['abc'] })
    expect(parseSignatureHeader('t=123,v1=abc,v1=def').v1).toEqual(['abc', 'def'])
    expect(parseSignatureHeader('garbage')).toEqual({ v1: [] })
  })
})

describe('verifyStripeSignature', () => {
  it('accepts a correctly signed payload within tolerance', async () => {
    const header = await signPayload(BODY, SECRET, TS)
    expect(await verifyStripeSignature(BODY, header, SECRET, 300, NOW)).toBe(true)
  })

  it('rejects a tampered body', async () => {
    const header = await signPayload(BODY, SECRET, TS)
    expect(await verifyStripeSignature(BODY + ' ', header, SECRET, 300, NOW)).toBe(false)
  })

  it('rejects the wrong secret', async () => {
    const header = await signPayload(BODY, SECRET, TS)
    expect(await verifyStripeSignature(BODY, header, 'whsec_wrong', 300, NOW)).toBe(false)
  })

  it('rejects a stale timestamp (replay)', async () => {
    const header = await signPayload(BODY, SECRET, TS - 10_000)
    expect(await verifyStripeSignature(BODY, header, SECRET, 300, NOW)).toBe(false)
  })

  it('accepts when any rotated v1 matches', async () => {
    const good = await signPayload(BODY, SECRET, TS)
    const v1 = good.split('v1=')[1]
    const header = `t=${TS},v1=deadbeef,v1=${v1}`
    expect(await verifyStripeSignature(BODY, header, SECRET, 300, NOW)).toBe(true)
  })

  it('rejects empty inputs', async () => {
    expect(await verifyStripeSignature(BODY, '', SECRET, 300, NOW)).toBe(false)
    expect(await verifyStripeSignature(BODY, 't=1,v1=ab', '', 300, NOW)).toBe(false)
  })
})
