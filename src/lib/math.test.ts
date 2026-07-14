import { describe, expect, it } from 'vitest'
import { bsGreeks, bsPrice, impliedVol, normCdf } from './black-scholes'
import { mcProbAboveAtExpiry, mcProbTouch, p50MonteCarlo } from './monte-carlo'
import {
  breakeven,
  maxLoss,
  maxProfit,
  payoffAtExpiry,
  pop,
  probAbove,
  probItm,
  probTouch,
  terminalPdf,
} from './probability'
import type { TradeInputs } from './types'

const base: TradeInputs = {
  S: 100,
  K: 100,
  dte: 365,
  iv: 0.2,
  premium: 10.45,
  type: 'call',
  side: 'long',
  r: 0.05,
  q: 0,
  contracts: 1,
  multiplier: 100,
}

describe('normCdf', () => {
  it('matches known values', () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 7)
    expect(normCdf(1.96)).toBeCloseTo(0.975, 3)
    expect(normCdf(-1.96)).toBeCloseTo(0.025, 3)
    expect(normCdf(3)).toBeCloseTo(0.99865, 4)
  })
})

describe('bsPrice', () => {
  // Textbook value: S=100 K=100 T=1 σ=20% r=5% q=0 → call ≈ 10.4506, put ≈ 5.5735
  it('matches the textbook ATM call/put', () => {
    const p = { S: 100, K: 100, T: 1, sigma: 0.2, r: 0.05, q: 0 }
    expect(bsPrice('call', p)).toBeCloseTo(10.4506, 3)
    expect(bsPrice('put', p)).toBeCloseTo(5.5735, 3)
  })

  it('satisfies put–call parity', () => {
    const p = { S: 105, K: 95, T: 0.35, sigma: 0.42, r: 0.03, q: 0.01 }
    const lhs = bsPrice('call', p) - bsPrice('put', p)
    const rhs = p.S * Math.exp(-p.q * p.T) - p.K * Math.exp(-p.r * p.T)
    expect(lhs).toBeCloseTo(rhs, 8)
  })

  it('degrades to intrinsic at expiry', () => {
    expect(bsPrice('call', { S: 110, K: 100, T: 0, sigma: 0.2, r: 0.05, q: 0 })).toBe(10)
    expect(bsPrice('put', { S: 110, K: 100, T: 0, sigma: 0.2, r: 0.05, q: 0 })).toBe(0)
  })
})

describe('bsGreeks', () => {
  const p = { S: 100, K: 100, T: 1, sigma: 0.2, r: 0.05, q: 0 }

  it('delta matches finite difference', () => {
    const g = bsGreeks('call', p)
    const h = 0.001
    const fd = (bsPrice('call', { ...p, S: p.S + h }) - bsPrice('call', { ...p, S: p.S - h })) / (2 * h)
    expect(g.delta).toBeCloseTo(fd, 5)
  })

  it('vega matches finite difference (per 1 vol point)', () => {
    const g = bsGreeks('call', p)
    const h = 0.0001
    const fd = (bsPrice('call', { ...p, sigma: p.sigma + h }) - bsPrice('call', { ...p, sigma: p.sigma - h })) / (2 * h)
    expect(g.vega).toBeCloseTo(fd / 100, 5)
  })

  it('call/put deltas differ by e^{-qT}', () => {
    const c = bsGreeks('call', p).delta
    const pt = bsGreeks('put', p).delta
    expect(c - pt).toBeCloseTo(Math.exp(-p.q * p.T), 8)
  })
})

describe('impliedVol', () => {
  it('round-trips the price', () => {
    const p = { S: 100, K: 105, T: 45 / 365, r: 0.05, q: 0 }
    const price = bsPrice('call', { ...p, sigma: 0.33 })
    expect(impliedVol('call', price, p)).toBeCloseTo(0.33, 5)
  })

  it('rejects prices outside no-arbitrage bounds', () => {
    const p = { S: 100, K: 100, T: 0.25, r: 0.05, q: 0 }
    expect(impliedVol('call', 0, p)).toBeNaN()
    expect(impliedVol('call', 200, p)).toBeNaN()
  })
})

describe('probabilities', () => {
  it('probAbove agrees with Monte Carlo at expiry', () => {
    const t = { ...base, dte: 45, iv: 0.3 }
    const closed = probAbove(105, { S: t.S, T: 45 / 365, sigma: t.iv, r: t.r, q: t.q })
    const mc = mcProbAboveAtExpiry(t, 105, 40000)
    expect(closed).toBeGreaterThan(0.1)
    expect(Math.abs(closed - mc)).toBeLessThan(0.01)
  })

  it('probTouch agrees with Monte Carlo (upper and lower barriers)', () => {
    const t = { ...base, dte: 45, iv: 0.3 }
    const gbm = { S: t.S, T: 45 / 365, sigma: t.iv, r: t.r, q: t.q }
    for (const level of [108, 92]) {
      const closed = probTouch(level, gbm)
      const mc = mcProbTouch(t, level, 12000)
      // MC monitors discretely so it slightly undershoots the continuous formula
      expect(mc).toBeLessThanOrEqual(closed + 0.01)
      expect(Math.abs(closed - mc)).toBeLessThan(0.035)
    }
  })

  it('probTouch is roughly twice prob ITM for OTM options', () => {
    const t: TradeInputs = { ...base, K: 110, dte: 30, iv: 0.25, r: 0, premium: 1 }
    const gbm = { S: t.S, T: 30 / 365, sigma: t.iv, r: 0, q: 0 }
    const touch = probTouch(t.K, gbm)
    const itm = probItm(t)
    expect(touch / itm).toBeGreaterThan(1.8)
    expect(touch / itm).toBeLessThan(2.2)
  })

  it('probTouch of the current price is 1 and far barriers approach 0', () => {
    const gbm = { S: 100, T: 0.1, sigma: 0.2, r: 0, q: 0 }
    expect(probTouch(100, gbm)).toBe(1)
    expect(probTouch(1000, gbm)).toBeLessThan(1e-6)
  })

  it('terminal pdf integrates to ~1', () => {
    const gbm = { S: 100, T: 0.25, sigma: 0.3, r: 0.02, q: 0 }
    let sum = 0
    const dx = 0.25
    for (let x = dx; x < 400; x += dx) sum += terminalPdf(x, gbm) * dx
    expect(sum).toBeCloseTo(1, 2)
  })
})

describe('position math', () => {
  it('long call breakeven/max/payoff', () => {
    const t: TradeInputs = { ...base, K: 100, premium: 5, side: 'long', type: 'call' }
    expect(breakeven(t)).toBe(105)
    expect(maxProfit(t)).toBe(Infinity)
    expect(maxLoss(t)).toBe(-500)
    expect(payoffAtExpiry(120, t)).toBe(1500)
    expect(payoffAtExpiry(90, t)).toBe(-500)
    expect(payoffAtExpiry(105, t)).toBe(0)
  })

  it('short put breakeven/max/payoff', () => {
    const t: TradeInputs = { ...base, K: 95, premium: 2.5, side: 'short', type: 'put' }
    expect(breakeven(t)).toBe(92.5)
    expect(maxProfit(t)).toBe(250)
    expect(maxLoss(t)).toBe(-9250)
    expect(payoffAtExpiry(100, t)).toBe(250)
    expect(payoffAtExpiry(92.5, t)).toBeCloseTo(0, 8)
    expect(payoffAtExpiry(80, t)).toBe(-1250)
  })

  it('long and short POP are complementary', () => {
    const long = pop({ ...base, side: 'long' })
    const short = pop({ ...base, side: 'short' })
    expect(long + short).toBeCloseTo(1, 8)
  })

  it('deep-ITM short put has high POP, far-OTM long call has low POP', () => {
    expect(pop({ ...base, type: 'put', side: 'short', K: 60, premium: 0.2, dte: 30 })).toBeGreaterThan(0.95)
    expect(pop({ ...base, type: 'call', side: 'long', K: 140, premium: 0.2, dte: 30 })).toBeLessThan(0.05)
  })
})

describe('p50 Monte Carlo', () => {
  it('is a sane probability and beats POP for typical short premium', () => {
    const t: TradeInputs = {
      ...base,
      type: 'put',
      side: 'short',
      K: 90,
      dte: 45,
      iv: 0.3,
      premium: 1.5,
    }
    const { p50 } = p50MonteCarlo(t, 3000)
    const popNow = pop(t)
    expect(p50).toBeGreaterThan(0)
    expect(p50).toBeLessThanOrEqual(1)
    // reaching 50% of max profit early is easier than holding a win to expiry
    expect(p50).toBeGreaterThan(popNow - 0.05)
  })

  it('is deterministic for a fixed seed', () => {
    const t: TradeInputs = { ...base, side: 'short', premium: 4, dte: 30 }
    expect(p50MonteCarlo(t, 1000).p50).toBe(p50MonteCarlo(t, 1000).p50)
  })
})
