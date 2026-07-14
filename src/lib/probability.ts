import { normCdf, normPdf } from './black-scholes'

/**
 * All probabilities assume the underlying follows geometric Brownian motion
 * with risk-neutral drift (r − q) and the given vol — the same lognormal
 * world Black–Scholes prices in. They are model estimates, not guarantees.
 */

export interface GbmParams {
  S: number
  T: number
  sigma: number
  r: number
  q: number
}

/** P(S_T > x) under GBM. Handles x = 0 (→1) and x = ∞ (→0). */
export function probAbove(x: number, { S, T, sigma, r, q }: GbmParams): number {
  if (x <= 0) return 1
  if (!Number.isFinite(x)) return 0
  if (T <= 0 || sigma <= 0) return S > x ? 1 : 0
  const nu = r - q - 0.5 * sigma * sigma
  return normCdf((Math.log(S / x) + nu * T) / (sigma * Math.sqrt(T)))
}

/** P(S_T < x) under GBM. */
export function probBelow(x: number, p: GbmParams): number {
  return 1 - probAbove(x, p)
}

/**
 * Probability the underlying trades AT OR THROUGH level B at any time
 * before T (first-passage of GBM through a barrier).
 */
export function probTouch(B: number, { S, T, sigma, r, q }: GbmParams): number {
  if (B <= 0 || !Number.isFinite(B)) return 0
  if (S === B) return 1
  if (T <= 0 || sigma <= 0) return 0
  const nu = r - q - 0.5 * sigma * sigma
  const b = Math.log(B / S)
  const volT = sigma * Math.sqrt(T)
  if (b > 0) {
    // upper barrier: P(max ≥ B)
    return normCdf((nu * T - b) / volT) + Math.exp((2 * nu * b) / (sigma * sigma)) * normCdf((-b - nu * T) / volT)
  }
  // lower barrier: P(min ≤ B)
  return normCdf((b - nu * T) / volT) + Math.exp((2 * nu * b) / (sigma * sigma)) * normCdf((b + nu * T) / volT)
}

/** Lognormal density of S_T evaluated at x. */
export function terminalPdf(x: number, { S, T, sigma, r, q }: GbmParams): number {
  if (x <= 0 || T <= 0 || sigma <= 0) return 0
  const volT = sigma * Math.sqrt(T)
  const m = Math.log(S) + (r - q - 0.5 * sigma * sigma) * T
  const z = (Math.log(x) - m) / volT
  return normPdf(z) / (x * volT)
}

/** 1σ expected move in underlying points. */
export function expectedMove(S: number, sigma: number, T: number): number {
  return S * sigma * Math.sqrt(Math.max(T, 0))
}

export function yearsToExpiry(dte: number): number {
  return Math.max(dte, 0) / 365
}
