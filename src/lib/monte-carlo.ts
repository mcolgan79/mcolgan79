import { bsPrice } from './black-scholes'
import { yearsToExpiry } from './probability'
import type { TradeInputs } from './types'

/** Deterministic RNG (mulberry32) so results are stable for a given input. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Standard normal via Box–Muller. */
function gaussianPair(rng: () => number): [number, number] {
  let u = 0
  while (u === 0) u = rng()
  const v = rng()
  const r = Math.sqrt(-2 * Math.log(u))
  return [r * Math.cos(2 * Math.PI * v), r * Math.sin(2 * Math.PI * v)]
}

export interface P50Result {
  /** Probability of hitting the profit target before expiration */
  p50: number
  /** The P&L target used, in per-share terms */
  targetPerShare: number
  /** Human description of the target */
  targetLabel: string
  paths: number
}

/**
 * P50 via Monte Carlo: simulate daily GBM steps, mark the option to model
 * (Black–Scholes at each day's remaining tenor), and count the paths whose
 * open P&L reaches the target at any close before expiration.
 *
 * Target convention:
 *  - short: 50% of max profit (half the credit) — the classic tastytrade P50
 *  - long:  a 50% return on the debit paid
 */
export function p50MonteCarlo(t: TradeInputs, paths = 4000, seed = 42): P50Result {
  const T = yearsToExpiry(t.dte)
  const steps = Math.max(Math.round(t.dte), 1)
  const dt = T / steps
  const drift = (t.r - t.q - 0.5 * t.iv * t.iv) * dt
  const volStep = t.iv * Math.sqrt(dt)
  const rng = mulberry32(seed)

  const isShort = t.side === 'short'
  const targetPerShare = 0.5 * t.premium
  const targetLabel = isShort ? '50% of max profit' : '50% return on debit'

  // Open P&L per share: short → premium − price; long → price − premium.
  // Hitting the target means price ≤ premium/2 (short) or ≥ 1.5×premium (long).
  const priceThreshold = isShort ? t.premium - targetPerShare : t.premium + targetPerShare

  let hits = 0
  const zs: [number, number] = [0, 0]
  for (let i = 0; i < paths; i++) {
    let s = t.S
    let hit = false
    for (let step = 1; step <= steps; step++) {
      if (step % 2 === 1) {
        const pair = gaussianPair(rng)
        zs[0] = pair[0]
        zs[1] = pair[1]
      }
      s *= Math.exp(drift + volStep * zs[(step - 1) % 2])
      const remaining = T - step * dt
      const value =
        remaining <= 0
          ? t.type === 'call'
            ? Math.max(s - t.K, 0)
            : Math.max(t.K - s, 0)
          : bsPrice(t.type, { S: s, K: t.K, T: remaining, sigma: t.iv, r: t.r, q: t.q })
      if (isShort ? value <= priceThreshold : value >= priceThreshold) {
        hit = true
        break
      }
    }
    if (hit) hits++
  }
  return { p50: hits / paths, targetPerShare, targetLabel, paths }
}

/** MC estimate of P(S_T beyond level) — used to cross-check closed forms in tests. */
export function mcProbAboveAtExpiry(
  t: TradeInputs,
  level: number,
  paths = 20000,
  seed = 7,
): number {
  const T = yearsToExpiry(t.dte)
  const rng = mulberry32(seed)
  let above = 0
  for (let i = 0; i < paths; i += 2) {
    const [z1, z2] = gaussianPair(rng)
    for (const z of [z1, z2]) {
      const sT = t.S * Math.exp((t.r - t.q - 0.5 * t.iv * t.iv) * T + t.iv * Math.sqrt(T) * z)
      if (sT > level) above++
    }
  }
  return above / (paths % 2 === 0 ? paths : paths + 1)
}

/** MC estimate of touch probability with daily monitoring — for tests. */
export function mcProbTouch(t: TradeInputs, level: number, paths = 8000, seed = 11): number {
  const T = yearsToExpiry(t.dte)
  const steps = Math.max(Math.round(t.dte) * 8, 8) // intraday steps to approximate continuity
  const dt = T / steps
  const drift = (t.r - t.q - 0.5 * t.iv * t.iv) * dt
  const volStep = t.iv * Math.sqrt(dt)
  const rng = mulberry32(seed)
  const up = level > t.S
  let hits = 0
  for (let i = 0; i < paths; i++) {
    let s = t.S
    for (let step = 0; step < steps; step++) {
      const [z] = gaussianPair(rng)
      s *= Math.exp(drift + volStep * z)
      if (up ? s >= level : s <= level) {
        hits++
        break
      }
    }
  }
  return hits / paths
}
