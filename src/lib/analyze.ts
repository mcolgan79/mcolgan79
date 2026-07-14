import { bsGreeks, bsPrice } from './black-scholes'
import { p50MonteCarlo } from './monte-carlo'
import {
  breakeven,
  expectedMove,
  gbmFromInputs,
  maxLoss,
  maxProfit,
  pop,
  probItm,
  probTouch,
  yearsToExpiry,
} from './probability'
import type { Analysis, TradeInputs } from './types'

export function analyze(t: TradeInputs): Analysis {
  const T = yearsToExpiry(t.dte)
  const gbm = gbmFromInputs(t)
  const bs = { S: t.S, K: t.K, T, sigma: t.iv, r: t.r, q: t.q }
  const rawGreeks = bsGreeks(t.type, bs)
  const sign = t.side === 'long' ? 1 : -1
  const greeks = {
    delta: sign * rawGreeks.delta,
    gamma: sign * rawGreeks.gamma,
    theta: sign * rawGreeks.theta,
    vega: sign * rawGreeks.vega,
    rho: sign * rawGreeks.rho,
  }
  const mp = maxProfit(t)
  const ml = maxLoss(t)
  const riskReward =
    ml === 0 ? Infinity : mp === 0 ? 0 : mp / Math.abs(ml) // Infinity/-Infinity handled by callers

  return {
    fairValue: bsPrice(t.type, bs),
    greeks,
    breakeven: breakeven(t),
    maxProfit: mp,
    maxLoss: ml,
    pop: pop(t),
    p50: p50MonteCarlo(t).p50,
    probItm: probItm(t),
    probTouchStrike: probTouch(t.K, gbm),
    probTouchBreakeven: probTouch(breakeven(t), gbm),
    expectedMove: expectedMove(t.S, t.iv, T),
    riskReward,
    yearsToExpiry: T,
  }
}
