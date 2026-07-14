export type OptionType = 'call' | 'put'
export type Side = 'long' | 'short'

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

/** One option leg. Prices are per share; `qty` is the leg ratio (usually 1). */
export interface Leg {
  type: OptionType
  side: Side
  K: number
  /** Calendar days to this leg's expiration */
  dte: number
  /** This leg's implied volatility, decimal */
  iv: number
  /** Premium per share */
  premium: number
  qty: number
}

export interface Strategy {
  /** Underlying price */
  S: number
  /** Risk-free rate, decimal */
  r: number
  /** Continuous dividend yield, decimal */
  q: number
  /** Number of spreads (multiplies every leg) */
  contracts: number
  multiplier: number
  legs: Leg[]
}

export type StrategyKind =
  | 'single'
  | 'vertical-credit'
  | 'vertical-debit'
  | 'iron-condor'
  | 'calendar'
  | 'diagonal'
  | 'straddle'
  | 'strangle'
  | 'custom'

export interface TouchProb {
  level: number
  prob: number
}

export interface StrategyAnalysis {
  kind: StrategyKind
  /** Days to the nearest expiration — the evaluation horizon */
  horizonDte: number
  /** Years to the horizon */
  T: number
  /** Single vol used for underlying dynamics (vega-weighted across legs) */
  sigma: number
  /** Net cost per share: positive = debit paid, negative = credit received */
  netCost: number
  /** Model net value per share, same sign convention as netCost */
  fairValue: number
  breakevens: number[]
  /** Price intervals profitable at the horizon; 0 / Infinity mark open ends */
  profitIntervals: Array<[number, number]>
  /** Total dollars; Infinity when unbounded */
  maxProfit: number
  /** Total dollars, ≤ 0; -Infinity when unbounded */
  maxLoss: number
  pop: number
  p50: number
  p50TargetLabel: string
  /** Touch probabilities for each breakeven before the horizon */
  probTouch: TouchProb[]
  /** 1σ expected move in underlying points, to the horizon */
  expectedMove: number
  riskReward: number
  /** Net position Greeks per share (per single spread) */
  greeks: Greeks
  /** Suggested price domain for charts */
  domain: [number, number]
}
