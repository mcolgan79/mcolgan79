import { normCdf, normPdf } from './black-scholes'
import type { TradeInputs } from './types'

/**
 * All probabilities assume the underlying follows geometric Brownian motion
 * with risk-neutral drift (r − q) and the entered IV — the same lognormal
 * world Black–Scholes prices in. They are model estimates, not guarantees.
 */

export interface GbmParams {
  S: number
  T: number
  sigma: number
  r: number
  q: number
}

/** P(S_T > x) under GBM. */
export function probAbove(x: number, { S, T, sigma, r, q }: GbmParams): number {
  if (x <= 0) return 1
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
 * before expiration (first-passage of GBM through a barrier).
 */
export function probTouch(B: number, { S, T, sigma, r, q }: GbmParams): number {
  if (B <= 0) return 0
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

export function gbmFromInputs(t: TradeInputs): GbmParams {
  return { S: t.S, T: yearsToExpiry(t.dte), sigma: t.iv, r: t.r, q: t.q }
}

/** Breakeven price at expiration (per the entered premium). */
export function breakeven(t: TradeInputs): number {
  return t.type === 'call' ? t.K + t.premium : t.K - t.premium
}

/** P&L at expiration for one underlying price, in total position dollars. */
export function payoffAtExpiry(sT: number, t: TradeInputs): number {
  const intrinsic = t.type === 'call' ? Math.max(sT - t.K, 0) : Math.max(t.K - sT, 0)
  const perShare = t.side === 'long' ? intrinsic - t.premium : t.premium - intrinsic
  return perShare * t.multiplier * t.contracts
}

/** Max profit in total dollars (Infinity for a long call). */
export function maxProfit(t: TradeInputs): number {
  const scale = t.multiplier * t.contracts
  if (t.side === 'short') return t.premium * scale
  if (t.type === 'call') return Infinity
  return Math.max(t.K - t.premium, 0) * scale // long put: stock to zero
}

/** Max loss in total dollars, ≤ 0 (−Infinity for a naked short call). */
export function maxLoss(t: TradeInputs): number {
  const scale = t.multiplier * t.contracts
  if (t.side === 'long') return -t.premium * scale
  if (t.type === 'call') return -Infinity
  return -Math.max(t.K - t.premium, 0) * scale // short put: stock to zero
}

/** Probability the position is profitable at expiration. */
export function pop(t: TradeInputs): number {
  const p = gbmFromInputs(t)
  const be = breakeven(t)
  const winsAbove =
    (t.type === 'call' && t.side === 'long') || (t.type === 'put' && t.side === 'short')
  return winsAbove ? probAbove(be, p) : probBelow(be, p)
}

/** Probability the option finishes in the money. */
export function probItm(t: TradeInputs): number {
  const p = gbmFromInputs(t)
  return t.type === 'call' ? probAbove(t.K, p) : probBelow(t.K, p)
}
