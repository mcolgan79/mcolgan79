import { describe, expect, it } from 'vitest'
import { bsGreeks, bsPrice, impliedVol, normCdf } from './black-scholes'
import { mcProbAboveAtExpiry, mcProbTouch, p50MonteCarlo } from './monte-carlo'
import { probAbove, probTouch, terminalPdf } from './probability'
import {
  classify,
  extremes,
  netCost,
  netGreeks,
  pnlAtHorizon,
  popStrategy,
  profitRegions,
  underlyingVol,
} from './strategy'
import type { Leg, Strategy } from './types'

function leg(partial: Partial<Leg>): Leg {
  return { type: 'call', side: 'long', K: 100, dte: 45, iv: 0.3, premium: 1, qty: 1, ...partial }
}

function strat(legs: Leg[], S = 100): Strategy {
  return { S, r: 0.05, q: 0, contracts: 1, multiplier: 100, legs }
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

describe('probability primitives', () => {
  const gbm = { S: 100, T: 45 / 365, sigma: 0.3, r: 0.05, q: 0 }

  it('probAbove agrees with Monte Carlo at expiry', () => {
    const closed = probAbove(105, gbm)
    const mc = mcProbAboveAtExpiry(gbm, 105, 40000)
    expect(closed).toBeGreaterThan(0.1)
    expect(Math.abs(closed - mc)).toBeLessThan(0.01)
  })

  it('probTouch agrees with Monte Carlo (upper and lower barriers)', () => {
    for (const level of [108, 92]) {
      const closed = probTouch(level, gbm)
      const mc = mcProbTouch(gbm, level, 12000)
      // MC monitors discretely so it slightly undershoots the continuous formula
      expect(mc).toBeLessThanOrEqual(closed + 0.01)
      expect(Math.abs(closed - mc)).toBeLessThan(0.035)
    }
  })

  it('probTouch is roughly twice probAbove for an upper barrier (r=0)', () => {
    const p = { S: 100, T: 30 / 365, sigma: 0.25, r: 0, q: 0 }
    const ratio = probTouch(110, p) / probAbove(110, p)
    expect(ratio).toBeGreaterThan(1.8)
    expect(ratio).toBeLessThan(2.2)
  })

  it('terminal pdf integrates to ~1', () => {
    const p = { S: 100, T: 0.25, sigma: 0.3, r: 0.02, q: 0 }
    let sum = 0
    const dx = 0.25
    for (let x = dx; x < 400; x += dx) sum += terminalPdf(x, p) * dx
    expect(sum).toBeCloseTo(1, 2)
  })
})

describe('single-leg strategies', () => {
  it('long call: breakeven, unbounded profit, capped loss', () => {
    const st = strat([leg({ type: 'call', side: 'long', K: 100, premium: 5 })])
    const r = profitRegions(st, 0.3)
    expect(r.breakevens).toHaveLength(1)
    expect(r.breakevens[0]).toBeCloseTo(105, 6)
    expect(r.intervals[0][1]).toBe(Infinity)
    const e = extremes(st, 0.3)
    expect(e.maxProfit).toBe(Infinity)
    expect(e.maxLoss).toBeCloseTo(-500, 6)
    expect(pnlAtHorizon(st, 120)).toBeCloseTo(1500, 6)
    expect(pnlAtHorizon(st, 90)).toBeCloseTo(-500, 6)
  })

  it('short put: breakeven, credit cap, risk to zero', () => {
    const st = strat([leg({ type: 'put', side: 'short', K: 95, premium: 2.5 })])
    const r = profitRegions(st, 0.3)
    expect(r.breakevens[0]).toBeCloseTo(92.5, 5)
    expect(r.intervals[0][1]).toBe(Infinity)
    const e = extremes(st, 0.3)
    expect(e.maxProfit).toBeCloseTo(250, 6)
    expect(e.maxLoss).toBeCloseTo(-9250, 2)
  })

  it('long and short POP are complementary', () => {
    const longPut = strat([leg({ type: 'put', side: 'long', K: 100, premium: 5.57, dte: 365, iv: 0.2 })])
    const shortPut = strat([leg({ type: 'put', side: 'short', K: 100, premium: 5.57, dte: 365, iv: 0.2 })])
    expect(popStrategy(longPut, 0.2) + popStrategy(shortPut, 0.2)).toBeCloseTo(1, 6)
  })
})

describe('vertical spreads', () => {
  // put credit spread: short 95 @ 2.50, long 90 @ 1.20 → credit 1.30, width 5
  const st = strat([
    leg({ type: 'put', side: 'short', K: 95, premium: 2.5 }),
    leg({ type: 'put', side: 'long', K: 90, premium: 1.2 }),
  ])

  it('classifies as vertical credit', () => {
    expect(classify(st)).toBe('vertical-credit')
    expect(netCost(st)).toBeCloseTo(-1.3, 8)
  })

  it('max profit = credit, max loss = width − credit', () => {
    const e = extremes(st, 0.3)
    expect(e.maxProfit).toBeCloseTo(130, 6)
    expect(e.maxLoss).toBeCloseTo(-370, 6)
  })

  it('breakeven at short strike − credit', () => {
    const r = profitRegions(st, 0.3)
    expect(r.breakevens).toHaveLength(1)
    expect(r.breakevens[0]).toBeCloseTo(93.7, 5)
  })

  it('POP equals P(S_T above breakeven)', () => {
    const pop = popStrategy(st, 0.3)
    const direct = probAbove(93.7, { S: 100, T: 45 / 365, sigma: 0.3, r: 0.05, q: 0 })
    expect(pop).toBeCloseTo(direct, 4)
  })
})

describe('iron condor', () => {
  const st = strat([
    leg({ type: 'put', side: 'long', K: 90, premium: 0.8 }),
    leg({ type: 'put', side: 'short', K: 95, premium: 1.9 }),
    leg({ type: 'call', side: 'short', K: 105, premium: 1.7 }),
    leg({ type: 'call', side: 'long', K: 110, premium: 0.7 }),
  ])

  it('classifies and has two breakevens around the body', () => {
    expect(classify(st)).toBe('iron-condor')
    const credit = -netCost(st)
    expect(credit).toBeCloseTo(2.1, 8)
    const r = profitRegions(st, 0.25)
    expect(r.breakevens).toHaveLength(2)
    expect(r.breakevens[0]).toBeCloseTo(95 - credit, 4)
    expect(r.breakevens[1]).toBeCloseTo(105 + credit, 4)
    expect(r.intervals).toHaveLength(1)
  })

  it('max profit = credit, max loss = width − credit, both wings equal', () => {
    const e = extremes(st, 0.25)
    expect(e.maxProfit).toBeCloseTo(210, 5)
    expect(e.maxLoss).toBeCloseTo(-290, 5)
  })

  it('POP is the mass between the breakevens', () => {
    const gbm = { S: 100, T: 45 / 365, sigma: 0.25, r: 0.05, q: 0 }
    const expected = probAbove(92.9, gbm) - probAbove(107.1, gbm)
    expect(popStrategy(st, 0.25)).toBeCloseTo(expected, 4)
  })
})

describe('calendar spread', () => {
  // short 30d ATM call, long 60d ATM call — classic long calendar
  const st = strat([
    leg({ type: 'call', side: 'short', K: 100, dte: 30, premium: 3.4 }),
    leg({ type: 'call', side: 'long', K: 100, dte: 60, premium: 4.9 }),
  ])

  it('classifies as calendar with a net debit', () => {
    expect(classify(st)).toBe('calendar')
    expect(netCost(st)).toBeCloseTo(1.5, 8)
  })

  it('payoff peaks near the strike at front expiration (tent shape)', () => {
    const atStrike = pnlAtHorizon(st, 100)
    expect(atStrike).toBeGreaterThan(pnlAtHorizon(st, 85))
    expect(atStrike).toBeGreaterThan(pnlAtHorizon(st, 115))
    expect(atStrike).toBeGreaterThan(0)
  })

  it('has two breakevens bracketing the strike and finite extremes', () => {
    const r = profitRegions(st, 0.3)
    expect(r.breakevens).toHaveLength(2)
    expect(r.breakevens[0]).toBeLessThan(100)
    expect(r.breakevens[1]).toBeGreaterThan(100)
    const e = extremes(st, 0.3)
    expect(Number.isFinite(e.maxProfit)).toBe(true)
    // worst case: both legs worthless / offsetting → lose ~the debit
    expect(e.maxLoss).toBeGreaterThanOrEqual(-155)
    expect(e.maxLoss).toBeLessThan(0)
  })

  it('POP is sane and between 0 and 1', () => {
    const pop = popStrategy(st, 0.3)
    expect(pop).toBeGreaterThan(0.05)
    expect(pop).toBeLessThan(0.95)
  })
})

describe('diagonal spread', () => {
  const st = strat([
    leg({ type: 'call', side: 'long', K: 95, dte: 75, premium: 8.6 }),
    leg({ type: 'call', side: 'short', K: 105, dte: 30, premium: 1.8 }),
  ])

  it('classifies as diagonal', () => {
    expect(classify(st)).toBe('diagonal')
  })

  it('net greeks are long delta and the payoff is finite at the horizon top side', () => {
    const g = netGreeks(st)
    expect(g.delta).toBeGreaterThan(0.2)
    const e = extremes(st, 0.3)
    // net calls = 0 → bounded at horizon
    expect(Number.isFinite(e.maxProfit)).toBe(true)
    expect(Number.isFinite(e.maxLoss)).toBe(true)
  })
})

describe('underlyingVol & greeks', () => {
  it('vega-weighted vol lands between the leg IVs', () => {
    const st = strat([
      leg({ type: 'put', side: 'short', K: 95, iv: 0.35 }),
      leg({ type: 'put', side: 'long', K: 90, iv: 0.4 }),
    ])
    const v = underlyingVol(st)
    expect(v).toBeGreaterThan(0.35)
    expect(v).toBeLessThan(0.4)
  })

  it('a vertical is short vega when short the nearer strike', () => {
    const st = strat([
      leg({ type: 'put', side: 'short', K: 95, premium: 2.5 }),
      leg({ type: 'put', side: 'long', K: 90, premium: 1.2 }),
    ])
    expect(netGreeks(st).vega).toBeLessThan(0)
    expect(netGreeks(st).theta).toBeGreaterThan(0)
  })
})

describe('p50 Monte Carlo', () => {
  it('is a sane probability and beats POP for typical short premium', () => {
    const st = strat([leg({ type: 'put', side: 'short', K: 90, premium: 1.5 })])
    const { p50 } = p50MonteCarlo(st, 0.3, 0.5 * 150, 3000)
    const pop = popStrategy(st, 0.3)
    expect(p50).toBeGreaterThan(0)
    expect(p50).toBeLessThanOrEqual(1)
    expect(p50).toBeGreaterThan(pop - 0.05)
  })

  it('is deterministic for a fixed seed', () => {
    const st = strat([leg({ type: 'call', side: 'short', K: 105, premium: 2 })])
    expect(p50MonteCarlo(st, 0.3, 100, 1000).p50).toBe(p50MonteCarlo(st, 0.3, 100, 1000).p50)
  })
})
