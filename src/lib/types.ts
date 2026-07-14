export type OptionType = 'call' | 'put'
export type Side = 'long' | 'short'

/** All prices are per share; `multiplier` scales to contract dollars. */
export interface TradeInputs {
  /** Underlying price */
  S: number
  /** Strike */
  K: number
  /** Calendar days to expiration */
  dte: number
  /** Implied volatility as a decimal (0.30 = 30%) */
  iv: number
  /** Option premium per share (mid price) */
  premium: number
  type: OptionType
  side: Side
  /** Risk-free rate as a decimal */
  r: number
  /** Continuous dividend yield as a decimal */
  q: number
  contracts: number
  multiplier: number
}

export interface Greeks {
  delta: number
  gamma: number
  /** Per calendar day, per share */
  theta: number
  /** Per 1 vol point (1%), per share */
  vega: number
  /** Per 1% rate move, per share */
  rho: number
}

export interface Analysis {
  fairValue: number
  greeks: Greeks
  breakeven: number
  /** Total dollars for the whole position (contracts × multiplier) */
  maxProfit: number
  /** Total dollars, negative. -Infinity when unbounded (naked short call). */
  maxLoss: number
  pop: number
  p50: number
  probItm: number
  probTouchStrike: number
  probTouchBreakeven: number
  /** 1σ expected move in underlying points */
  expectedMove: number
  /** Reward per $1 risked; Infinity if risk-free, 0 if profit-free */
  riskReward: number
  yearsToExpiry: number
}
