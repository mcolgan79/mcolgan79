import { bsGreeks, bsPrice } from './black-scholes'
import { probAbove, yearsToExpiry, type GbmParams } from './probability'
import type { Greeks, Leg, Strategy, StrategyKind } from './types'

const DAY = 1 / 365

export const legSign = (leg: Leg): number => (leg.side === 'long' ? 1 : -1)

/** Days to the nearest expiration — the horizon everything is evaluated at. */
export function frontDte(st: Strategy): number {
  return Math.min(...st.legs.map((l) => l.dte))
}

/** Net cost per share: positive = debit paid, negative = credit received. */
export function netCost(st: Strategy): number {
  return st.legs.reduce((sum, l) => sum + legSign(l) * l.premium * l.qty, 0)
}

/** Model value of one leg per share, `tYears` from now. */
export function legValueAt(leg: Leg, S: number, tYears: number, r: number, q: number): number {
  const rem = leg.dte * DAY - tYears
  if (rem <= 1e-9) {
    return leg.type === 'call' ? Math.max(S - leg.K, 0) : Math.max(leg.K - S, 0)
  }
  return bsPrice(leg.type, { S, K: leg.K, T: rem, sigma: leg.iv, r, q })
}

/** Signed model value of the whole position per share, `tYears` from now. */
export function strategyValue(st: Strategy, S: number, tYears: number): number {
  return st.legs.reduce((sum, l) => sum + legSign(l) * l.qty * legValueAt(l, S, tYears, st.r, st.q), 0)
}

/** Total-dollar P&L if the underlying is at `S`, `tYears` from now. */
export function pnl(st: Strategy, S: number, tYears: number): number {
  return (strategyValue(st, S, tYears) - netCost(st)) * st.multiplier * st.contracts
}

export function pnlAtHorizon(st: Strategy, S: number): number {
  return pnl(st, S, frontDte(st) * DAY)
}

export function pnlToday(st: Strategy, S: number): number {
  return pnl(st, S, 0)
}

/**
 * One vol for the underlying's dynamics: legs can carry different IVs
 * (skew/term structure), so weight them by vega — the ATM-ish legs that
 * dominate the position's pricing dominate the estimate too.
 */
export function underlyingVol(st: Strategy): number {
  let wSum = 0
  let ivSum = 0
  for (const l of st.legs) {
    const T = yearsToExpiry(l.dte)
    const vega = Math.abs(
      bsGreeks(l.type, { S: st.S, K: l.K, T, sigma: l.iv, r: st.r, q: st.q }).vega,
    )
    const w = Math.max(vega, 1e-6) * l.qty
    wSum += w
    ivSum += w * l.iv
  }
  return wSum > 0 ? ivSum / wSum : st.legs[0]?.iv ?? 0.3
}

/** Net position Greeks per share (each leg at its own tenor and IV). */
export function netGreeks(st: Strategy): Greeks {
  const out = { delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0 }
  for (const l of st.legs) {
    const g = bsGreeks(l.type, {
      S: st.S,
      K: l.K,
      T: yearsToExpiry(l.dte),
      sigma: l.iv,
      r: st.r,
      q: st.q,
    })
    const s = legSign(l) * l.qty
    out.delta += s * g.delta
    out.gamma += s * g.gamma
    out.theta += s * g.theta
    out.vega += s * g.vega
    out.rho += s * g.rho
  }
  return out
}

/** Net linear exposure to calls for S → ∞ (per-share payoff slope). */
function callSlope(st: Strategy): number {
  return st.legs
    .filter((l) => l.type === 'call')
    .reduce((sum, l) => sum + legSign(l) * l.qty, 0)
}

export interface ProfitRegions {
  /** [a, b] price intervals profitable at the horizon; 0/Infinity = open end */
  intervals: Array<[number, number]>
  /** Finite interval edges — the breakeven prices */
  breakevens: number[]
}

function bisectZero(f: (s: number) => number, lo: number, hi: number): number {
  let fLo = f(lo)
  for (let i = 0; i < 80; i++) {
    const mid = (lo + hi) / 2
    const fMid = f(mid)
    if (fMid === 0) return mid
    if ((fLo > 0) === (fMid > 0)) {
      lo = mid
      fLo = fMid
    } else {
      hi = mid
    }
  }
  return (lo + hi) / 2
}

/**
 * Profit intervals of the horizon payoff, found on a log-spaced grid with
 * bisection-refined crossings. Handles open tails: below the lowest strike
 * and above the highest the payoff is (asymptotically) linear in S.
 */
export function profitRegions(st: Strategy, sigma: number): ProfitRegions {
  const T = Math.max(frontDte(st) * DAY, 1e-6)
  const vol = Math.max(sigma * Math.sqrt(T), 0.02)
  const Ks = st.legs.map((l) => l.K)
  const lo = Math.min(st.S * Math.exp(-5 * vol), Math.min(...Ks) * 0.5)
  const hi = Math.max(st.S * Math.exp(5 * vol), Math.max(...Ks) * 2)
  const f = (s: number) => pnlAtHorizon(st, s)

  const n = 1201
  const logLo = Math.log(Math.max(lo, 1e-4))
  const logHi = Math.log(hi)
  const xs: number[] = []
  const ys: number[] = []
  for (let i = 0; i < n; i++) {
    const s = Math.exp(logLo + ((logHi - logLo) * i) / (n - 1))
    xs.push(s)
    ys.push(f(s))
  }

  // crossings inside the grid
  const edges: number[] = []
  for (let i = 1; i < n; i++) {
    if (ys[i - 1] === 0) edges.push(xs[i - 1])
    else if ((ys[i - 1] > 0) !== (ys[i] > 0)) edges.push(bisectZero(f, xs[i - 1], xs[i]))
  }

  // left tail: payoff is ~linear below the lowest strike; check S → 0
  const pnlAtZero = f(1e-6)
  if ((pnlAtZero > 0) !== (ys[0] > 0) && ys[0] !== 0) {
    edges.unshift(bisectZero(f, 1e-6, xs[0]))
  }

  // right tail: asymptotic sign comes from net call exposure
  const slope = callSlope(st)
  const asymptoticPositive = slope !== 0 ? slope > 0 : f(hi * 1e4) > 0
  if (asymptoticPositive !== ys[n - 1] > 0 && ys[n - 1] !== 0) {
    let far = hi * 2
    let guard = 0
    while ((f(far) > 0) === ys[n - 1] > 0 && guard++ < 40) far *= 2
    edges.push(bisectZero(f, far / 2, far))
  }

  const sorted = [...new Set(edges)].sort((a, b) => a - b)

  // build intervals by walking the sign between edges
  const intervals: Array<[number, number]> = []
  const bounds = [0, ...sorted, Infinity]
  for (let i = 0; i < bounds.length - 1; i++) {
    const a = bounds[i]
    const b = bounds[i + 1]
    const probe = Number.isFinite(b) ? (Math.max(a, 1e-6) + b) / 2 : Math.max(a * 2, hi * 1e3)
    if (f(probe) > 0) {
      // merge adjacent intervals sharing an edge (touching zero without crossing)
      const prev = intervals[intervals.length - 1]
      if (prev && prev[1] === a) prev[1] = b
      else intervals.push([a, b])
    }
  }

  return { intervals, breakevens: sorted }
}

/** POP: total probability mass of the profit intervals at the horizon. */
export function popStrategy(st: Strategy, sigma: number, regions?: ProfitRegions): number {
  const gbm: GbmParams = { S: st.S, T: frontDte(st) * DAY, sigma, r: st.r, q: st.q }
  const { intervals } = regions ?? profitRegions(st, sigma)
  let p = 0
  for (const [a, b] of intervals) p += probAbove(a, gbm) - probAbove(b, gbm)
  return Math.min(Math.max(p, 0), 1)
}

export interface Extremes {
  maxProfit: number
  maxLoss: number
}

/** Max profit / max loss of the horizon payoff in total dollars. */
export function extremes(st: Strategy, sigma: number): Extremes {
  const T = Math.max(frontDte(st) * DAY, 1e-6)
  const vol = Math.max(sigma * Math.sqrt(T), 0.02)
  const Ks = st.legs.map((l) => l.K)
  const lo = Math.max(Math.min(st.S * Math.exp(-5 * vol), Math.min(...Ks) * 0.5), 1e-4)
  const hi = Math.max(st.S * Math.exp(5 * vol), Math.max(...Ks) * 2)
  let mx = -Infinity
  let mn = Infinity
  const n = 1201
  for (let i = 0; i < n; i++) {
    const s = Math.exp(Math.log(lo) + ((Math.log(hi) - Math.log(lo)) * i) / (n - 1))
    const v = pnlAtHorizon(st, s)
    if (v > mx) mx = v
    if (v < mn) mn = v
  }
  const atZero = pnlAtHorizon(st, 1e-6)
  mx = Math.max(mx, atZero)
  mn = Math.min(mn, atZero)
  const slope = callSlope(st)
  if (slope > 0) mx = Infinity
  if (slope < 0) mn = -Infinity
  return { maxProfit: mx, maxLoss: Math.min(mn, 0) }
}

/** Price domain for charts: covers strikes, breakevens and ±3.2σ. */
export function chartDomain(st: Strategy, sigma: number, breakevens: number[]): [number, number] {
  const T = frontDte(st) * DAY
  const em = Math.max(st.S * sigma * Math.sqrt(Math.max(T, 0)), st.S * 0.02)
  const Ks = st.legs.map((l) => l.K)
  const bes = breakevens.filter((b) => Number.isFinite(b) && b > 0)
  const lo = Math.max(
    Math.min(st.S - 3.2 * em, Math.min(...Ks) * 0.94, ...bes.map((b) => b * 0.97)),
    0.01,
  )
  const hi = Math.max(st.S + 3.2 * em, Math.max(...Ks) * 1.06, ...bes.map((b) => b * 1.03))
  return [lo, hi]
}

/** Recognize the common structures so recommendations can be specific. */
export function classify(st: Strategy): StrategyKind {
  const L = st.legs
  if (L.length === 1) return 'single'
  if (L.length === 2) {
    const [a, b] = L
    if (a.type === b.type && a.side !== b.side && a.qty === b.qty) {
      if (a.dte === b.dte && a.K !== b.K) {
        return netCost(st) < 0 ? 'vertical-credit' : 'vertical-debit'
      }
      if (a.K === b.K && a.dte !== b.dte) return 'calendar'
      if (a.dte !== b.dte) return 'diagonal'
    }
    if (a.type !== b.type && a.side === b.side && a.dte === b.dte) {
      return a.K === b.K ? 'straddle' : 'strangle'
    }
  }
  if (L.length === 4) {
    const dte = L[0].dte
    if (L.every((l) => l.dte === dte && l.qty === L[0].qty)) {
      const sp = L.find((l) => l.type === 'put' && l.side === 'short')
      const lp = L.find((l) => l.type === 'put' && l.side === 'long')
      const sc = L.find((l) => l.type === 'call' && l.side === 'short')
      const lc = L.find((l) => l.type === 'call' && l.side === 'long')
      if (sp && lp && sc && lc && lp.K < sp.K && sp.K <= sc.K && sc.K < lc.K) {
        return 'iron-condor'
      }
    }
  }
  return 'custom'
}

/** True when every leg expires on the same date. */
export function singleExpiry(st: Strategy): boolean {
  return st.legs.every((l) => l.dte === st.legs[0].dte)
}
