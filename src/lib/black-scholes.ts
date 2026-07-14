import type { Greeks, OptionType } from './types'

/**
 * Complementary error function, Numerical Recipes 6.2 rational Chebyshev
 * approximation. Fractional error < 1.2e-7 everywhere.
 */
function erfc(x: number): number {
  const z = Math.abs(x)
  const t = 1 / (1 + z / 2)
  const ans =
    t *
    Math.exp(
      -z * z -
        1.26551223 +
        t *
          (1.00002368 +
            t *
              (0.37409196 +
                t *
                  (0.09678418 +
                    t *
                      (-0.18628806 +
                        t *
                          (0.27886807 +
                            t *
                              (-1.13520398 +
                                t *
                                  (1.48851587 +
                                    t * (-0.82215223 + t * 0.17087277)))))))),
    )
  return x >= 0 ? ans : 2 - ans
}

/** Standard normal CDF */
export function normCdf(x: number): number {
  return 0.5 * erfc(-x / Math.SQRT2)
}

/** Standard normal PDF */
export function normPdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI)
}

export interface BsParams {
  S: number
  K: number
  /** Time in years */
  T: number
  /** Vol, decimal */
  sigma: number
  r: number
  q: number
}

function d1d2({ S, K, T, sigma, r, q }: BsParams): [number, number] {
  const sqrtT = Math.sqrt(T)
  const d1 =
    (Math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
  return [d1, d1 - sigma * sqrtT]
}

/** Black–Scholes–Merton price per share. Handles T→0 and σ→0 as intrinsic. */
export function bsPrice(type: OptionType, p: BsParams): number {
  const { S, K, T, sigma, r, q } = p
  if (T <= 0 || sigma <= 0) {
    const fwd = S * Math.exp((r - q) * Math.max(T, 0))
    const disc = Math.exp(-r * Math.max(T, 0))
    const intrinsic = type === 'call' ? fwd - K : K - fwd
    return Math.max(disc * intrinsic, 0)
  }
  const [d1, d2] = d1d2(p)
  if (type === 'call') {
    return S * Math.exp(-q * T) * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2)
  }
  return K * Math.exp(-r * T) * normCdf(-d2) - S * Math.exp(-q * T) * normCdf(-d1)
}

/** Greeks per share (theta per calendar day, vega/rho per 1%). */
export function bsGreeks(type: OptionType, p: BsParams): Greeks {
  const { S, K, T, sigma, r, q } = p
  if (T <= 0 || sigma <= 0) {
    const itm = type === 'call' ? S > K : S < K
    return {
      delta: itm ? (type === 'call' ? 1 : -1) : 0,
      gamma: 0,
      theta: 0,
      vega: 0,
      rho: 0,
    }
  }
  const [d1, d2] = d1d2(p)
  const sqrtT = Math.sqrt(T)
  const pdf = normPdf(d1)
  const eqT = Math.exp(-q * T)
  const erT = Math.exp(-r * T)

  const delta = type === 'call' ? eqT * normCdf(d1) : -eqT * normCdf(-d1)
  const gamma = (eqT * pdf) / (S * sigma * sqrtT)
  const vega = (S * eqT * pdf * sqrtT) / 100

  const thetaCommon = -(S * eqT * pdf * sigma) / (2 * sqrtT)
  const thetaAnnual =
    type === 'call'
      ? thetaCommon - r * K * erT * normCdf(d2) + q * S * eqT * normCdf(d1)
      : thetaCommon + r * K * erT * normCdf(-d2) - q * S * eqT * normCdf(-d1)
  const theta = thetaAnnual / 365

  const rho =
    type === 'call'
      ? (K * T * erT * normCdf(d2)) / 100
      : (-K * T * erT * normCdf(-d2)) / 100

  return { delta, gamma, theta, vega, rho }
}

/**
 * Implied volatility from a market price. Newton–Raphson with a
 * bisection fallback; returns NaN when the price is outside no-arbitrage
 * bounds or the solver cannot converge.
 */
export function impliedVol(
  type: OptionType,
  price: number,
  p: Omit<BsParams, 'sigma'>,
): number {
  const { S, K, T, r, q } = p
  if (!(price > 0) || T <= 0) return NaN
  const fwd = S * Math.exp((r - q) * T)
  const disc = Math.exp(-r * T)
  const intrinsic = Math.max(disc * (type === 'call' ? fwd - K : K - fwd), 0)
  const upper = type === 'call' ? S * Math.exp(-q * T) : K * disc
  if (price <= intrinsic || price >= upper) return NaN

  let sigma = Math.sqrt((2 * Math.PI) / T) * (price / S) // Brenner–Subrahmanyam seed
  sigma = Math.min(Math.max(sigma, 0.01), 3)
  for (let i = 0; i < 20; i++) {
    const diff = bsPrice(type, { ...p, sigma }) - price
    const vega = bsGreeks(type, { ...p, sigma }).vega * 100
    if (Math.abs(diff) < 1e-8) return sigma
    if (vega < 1e-10) break
    const next = sigma - diff / vega
    if (!Number.isFinite(next) || next <= 0 || next > 10) break
    sigma = next
  }
  // Bisection fallback over [1e-4, 10]
  let lo = 1e-4
  let hi = 10
  for (let i = 0; i < 100; i++) {
    const mid = (lo + hi) / 2
    if (bsPrice(type, { ...p, sigma: mid }) > price) hi = mid
    else lo = mid
  }
  const out = (lo + hi) / 2
  return Math.abs(bsPrice(type, { ...p, sigma: out }) - price) < 1e-4 * price + 1e-6
    ? out
    : NaN
}
