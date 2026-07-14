import type { GbmParams } from './probability'
import { frontDte, pnl } from './strategy'
import type { Strategy } from './types'

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
  /** Probability of hitting the profit target before the horizon */
  p50: number
  /** The total-dollar P&L target used */
  targetDollars: number
  paths: number
}

/**
 * P50 via Monte Carlo: simulate daily GBM steps to the front expiration,
 * mark every leg to model each day, and count the paths whose open P&L
 * reaches `targetDollars` at any close.
 */
export function p50MonteCarlo(
  st: Strategy,
  sigma: number,
  targetDollars: number,
  paths = 3000,
  seed = 42,
): P50Result {
  const days = Math.max(Math.round(frontDte(st)), 1)
  const T = days / 365
  const dt = T / days
  const drift = (st.r - st.q - 0.5 * sigma * sigma) * dt
  const volStep = sigma * Math.sqrt(dt)
  const rng = mulberry32(seed)

  let hits = 0
  const zs: [number, number] = [0, 0]
  for (let i = 0; i < paths; i++) {
    let s = st.S
    for (let step = 1; step <= days; step++) {
      if (step % 2 === 1) {
        const pair = gaussianPair(rng)
        zs[0] = pair[0]
        zs[1] = pair[1]
      }
      s *= Math.exp(drift + volStep * zs[(step - 1) % 2])
      if (pnl(st, s, step * dt) >= targetDollars) {
        hits++
        break
      }
    }
  }
  return { p50: hits / paths, targetDollars, paths }
}

/** MC estimate of P(S_T > level) — used to cross-check closed forms in tests. */
export function mcProbAboveAtExpiry(
  { S, T, sigma, r, q }: GbmParams,
  level: number,
  paths = 20000,
  seed = 7,
): number {
  const rng = mulberry32(seed)
  let above = 0
  const total = paths % 2 === 0 ? paths : paths + 1
  for (let i = 0; i < total; i += 2) {
    const [z1, z2] = gaussianPair(rng)
    for (const z of [z1, z2]) {
      const sT = S * Math.exp((r - q - 0.5 * sigma * sigma) * T + sigma * Math.sqrt(T) * z)
      if (sT > level) above++
    }
  }
  return above / total
}

/** MC estimate of touch probability with intraday monitoring — for tests. */
export function mcProbTouch(
  { S, T, sigma, r, q }: GbmParams,
  level: number,
  paths = 8000,
  seed = 11,
): number {
  const steps = Math.max(Math.round(T * 365) * 8, 8)
  const dt = T / steps
  const drift = (r - q - 0.5 * sigma * sigma) * dt
  const volStep = sigma * Math.sqrt(dt)
  const rng = mulberry32(seed)
  const up = level > S
  let hits = 0
  for (let i = 0; i < paths; i++) {
    let s = S
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
