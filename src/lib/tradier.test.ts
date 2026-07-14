import { describe, expect, it } from 'vitest'
import { dteFrom, midPrice, parseChain, parseExpirations, parseQuote, toArray } from './tradier'

describe('tradier response normalization', () => {
  it('toArray handles Tradier single-object collapse and nulls', () => {
    expect(toArray(null)).toEqual([])
    expect(toArray(undefined)).toEqual([])
    expect(toArray({ a: 1 })).toEqual([{ a: 1 }])
    expect(toArray([1, 2])).toEqual([1, 2])
  })

  it('midPrice prefers bid/ask midpoint, falls back to last', () => {
    expect(midPrice(1.2, 1.3, 5)).toBeCloseTo(1.25, 10)
    expect(midPrice(0, 0, 2.4)).toBe(2.4)
    expect(midPrice(0, 0, null)).toBeNull()
    expect(midPrice(0, 0, 0)).toBeNull()
  })

  it('dteFrom counts calendar days with a floor of 1', () => {
    const now = new Date('2026-07-14T14:00:00Z')
    expect(dteFrom('2026-08-21', now)).toBe(38)
    expect(dteFrom('2026-07-14', now)).toBe(1)
  })

  it('parseQuote reads the quote object (single-element collapse)', () => {
    const json = {
      quotes: { quote: { symbol: 'AAPL', description: 'Apple Inc', last: 213.45 } },
    }
    expect(parseQuote(json)).toEqual({ symbol: 'AAPL', description: 'Apple Inc', last: 213.45 })
    expect(() => parseQuote({ quotes: { quote: null } })).toThrow('Symbol not found')
  })

  it('parseExpirations reads single and multiple dates', () => {
    expect(parseExpirations({ expirations: { date: '2026-08-21' } })).toEqual(['2026-08-21'])
    expect(
      parseExpirations({ expirations: { date: ['2026-08-21', '2026-09-18'] } }),
    ).toEqual(['2026-08-21', '2026-09-18'])
    expect(parseExpirations({ expirations: null })).toEqual([])
  })

  it('parseChain maps, filters, sorts, and extracts IV', () => {
    const json = {
      options: {
        option: [
          {
            option_type: 'put',
            strike: 210,
            bid: 3.1,
            ask: 3.3,
            last: 3.15,
            greeks: { mid_iv: 0.284 },
          },
          {
            option_type: 'call',
            strike: 205,
            bid: 0,
            ask: 0,
            last: 11.2,
            greeks: { mid_iv: 0 , smv_vol: 0.31 },
          },
          { option_type: 'bogus', strike: 1 },
        ],
      },
    }
    const chain = parseChain(json, '2026-08-21')
    expect(chain.options).toHaveLength(2)
    expect(chain.options[0]).toMatchObject({ type: 'call', strike: 205, mid: 11.2, iv: 0.31 })
    expect(chain.options[1]).toMatchObject({ type: 'put', strike: 210, mid: 3.2, iv: 0.284 })
  })
})
