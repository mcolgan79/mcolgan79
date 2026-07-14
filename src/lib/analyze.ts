import { p50MonteCarlo } from './monte-carlo'
import { expectedMove, probTouch } from './probability'
import {
  chartDomain,
  classify,
  extremes,
  frontDte,
  netCost,
  netGreeks,
  popStrategy,
  profitRegions,
  strategyValue,
  underlyingVol,
} from './strategy'
import type { Strategy, StrategyAnalysis } from './types'

export function analyze(st: Strategy): StrategyAnalysis {
  const horizonDte = frontDte(st)
  const T = horizonDte / 365
  const sigma = underlyingVol(st)
  const scale = st.multiplier * st.contracts
  const cost = netCost(st)

  const regions = profitRegions(st, sigma)
  const { maxProfit, maxLoss } = extremes(st, sigma)
  const pop = popStrategy(st, sigma, regions)

  // P50 target: half of max profit when it's defined; otherwise (unbounded
  // upside) a 50% return on the net debit.
  let targetDollars: number
  let p50TargetLabel: string
  if (Number.isFinite(maxProfit) && maxProfit > 0) {
    targetDollars = 0.5 * maxProfit
    p50TargetLabel = '50% of max profit'
  } else {
    targetDollars = 0.5 * Math.max(Math.abs(cost), 0.01) * scale
    p50TargetLabel = '50% return on the debit'
  }
  const paths = st.legs.length > 2 ? 2500 : 4000
  const { p50 } = p50MonteCarlo(st, sigma, targetDollars, paths)

  const gbm = { S: st.S, T, sigma, r: st.r, q: st.q }
  const touch = regions.breakevens
    .filter((b) => b > 0 && Number.isFinite(b))
    .slice(0, 3)
    .map((level) => ({ level, prob: probTouch(level, gbm) }))

  const riskReward =
    maxLoss === 0 ? Infinity : maxProfit === 0 ? 0 : maxProfit / Math.abs(maxLoss)

  return {
    kind: classify(st),
    horizonDte,
    T,
    sigma,
    netCost: cost,
    fairValue: strategyValue(st, st.S, 0),
    breakevens: regions.breakevens,
    profitIntervals: regions.intervals,
    maxProfit,
    maxLoss,
    pop,
    p50,
    p50TargetLabel,
    probTouch: touch,
    expectedMove: expectedMove(st.S, sigma, T),
    riskReward,
    greeks: netGreeks(st),
    domain: chartDomain(st, sigma, regions.breakevens),
  }
}
