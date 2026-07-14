import type { Analysis, TradeInputs } from './types'

export type Severity = 'warning' | 'suggestion' | 'info'

export interface Recommendation {
  severity: Severity
  title: string
  detail: string
}

const fmtPct = (x: number) => `${Math.round(x * 100)}%`

/**
 * Heuristic trade-improvement engine. Rules encode widely used
 * premium-selling / debit-buying guidelines (DTE window, delta bands,
 * defined-risk conversion, profit-taking at 50%). Educational, not advice.
 */
export function recommend(t: TradeInputs, a: Analysis): Recommendation[] {
  const recs: Recommendation[] = []
  const otm = t.type === 'call' ? t.K > t.S : t.K < t.S
  const absDelta = Math.abs(a.greeks.delta)

  // --- Risk shape ---
  if (t.side === 'short' && t.type === 'call') {
    recs.push({
      severity: 'warning',
      title: 'Undefined risk: naked short call',
      detail:
        'Loss is unlimited if the underlying rallies. Buying a further-OTM call against it (a call credit spread) caps the loss at the width of the strikes minus the credit, usually giving up only a small part of the premium.',
    })
  } else if (t.side === 'short' && t.type === 'put') {
    recs.push({
      severity: 'info',
      title: 'Short put risk extends to zero',
      detail: `Max loss is ${'$'}${Math.abs(a.maxLoss).toLocaleString(undefined, { maximumFractionDigits: 0 })} if the underlying goes to zero. A put credit spread (buy a lower-strike put) defines the risk and cuts buying-power use.`,
    })
  }

  // --- DTE window ---
  if (t.side === 'short') {
    if (t.dte < 21) {
      recs.push({
        severity: 'warning',
        title: 'Short premium inside 21 DTE',
        detail:
          'Gamma risk grows quickly in the final weeks: small moves in the underlying swing the P&L hard. The commonly used window for opening short premium is 30–45 DTE, managing or rolling at ~21 DTE.',
      })
    } else if (t.dte > 60) {
      recs.push({
        severity: 'suggestion',
        title: 'Long-dated short premium decays slowly',
        detail:
          'Theta is small this far out; most of the decay happens in the last 45 days. Consider 30–45 DTE for a better decay-per-day profile.',
      })
    }
  } else {
    if (t.dte < 21) {
      recs.push({
        severity: 'warning',
        title: 'Long option with little time',
        detail: `Theta is costing about $${Math.abs(a.greeks.theta * t.multiplier * t.contracts).toFixed(0)}/day and accelerates into expiration. Buying more time (60–90+ DTE) or going deeper ITM reduces the decay drag.`,
      })
    }
  }

  // --- Probabilities ---
  if (t.side === 'short' && a.pop < 0.6) {
    recs.push({
      severity: 'suggestion',
      title: `POP is only ${fmtPct(a.pop)} for a short option`,
      detail:
        'Short premium usually targets a high probability of profit. Moving the strike further out-of-the-money (roughly the 16–30 delta area) raises POP, in exchange for less credit.',
    })
  }
  if (t.side === 'long' && a.pop < 0.35) {
    recs.push({
      severity: 'suggestion',
      title: `Low odds: POP is ${fmtPct(a.pop)}`,
      detail: `Breakeven is ${a.breakeven.toFixed(2)}, ${(
        (Math.abs(a.breakeven - t.S) / t.S) * 100
      ).toFixed(1)}% away. A strike closer to (or in) the money, or a debit spread that sells a further-OTM option against this one, lowers the breakeven and raises POP — at the cost of capping the upside.`,
    })
  }
  if (t.side === 'short' && otm && a.probTouchStrike > 0.5) {
    recs.push({
      severity: 'info',
      title: `The strike will likely be tested (${fmtPct(a.probTouchStrike)} touch)`,
      detail:
        'Probability of touch is roughly twice the probability of expiring ITM, so expect the position to show a loss at some point even if it wins at expiration. Size so a test of the strike is tolerable.',
    })
  }

  // --- Delta band for short premium ---
  if (t.side === 'short' && absDelta > 0.35) {
    recs.push({
      severity: 'suggestion',
      title: `Strike is aggressive at ${absDelta.toFixed(2)} delta`,
      detail:
        'Premium sellers typically work the 16–30 delta band: meaningfully lower touch/ITM odds while still collecting worthwhile credit.',
    })
  }

  // --- Volatility regime ---
  if (t.iv >= 0.45 && t.side === 'long') {
    recs.push({
      severity: 'suggestion',
      title: `Buying a rich IV (${(t.iv * 100).toFixed(0)}%)`,
      detail:
        'High IV inflates the debit and exposes the trade to IV contraction (vega loss) even if direction is right. A debit spread neutralizes much of the vega, or consider whether short premium fits the thesis instead.',
    })
  }
  if (t.iv <= 0.18 && t.side === 'short') {
    recs.push({
      severity: 'suggestion',
      title: `Selling a thin IV (${(t.iv * 100).toFixed(0)}%)`,
      detail:
        'Low IV means little premium relative to the risk, and IV expansion works against the position. Long premium or spreads are usually favored in low-IV regimes. (Check IV rank against the past year to confirm.)',
    })
  }

  // --- Risk/reward ---
  if (Number.isFinite(a.riskReward) && a.riskReward < 0.25 && a.pop < 0.85) {
    recs.push({
      severity: 'warning',
      title: `Thin reward for the risk (${a.riskReward.toFixed(2)} : 1)`,
      detail: `Max profit $${a.maxProfit.toLocaleString(undefined, { maximumFractionDigits: 0 })} vs. max loss $${Math.abs(
        a.maxLoss,
      ).toLocaleString(undefined, { maximumFractionDigits: 0 })}. Risking several times the potential reward needs a high POP to carry positive expectancy — tighten the risk with a spread or take a strike with more credit.`,
    })
  }

  // --- Management ---
  if (t.side === 'short' && a.p50 > 0) {
    recs.push({
      severity: 'info',
      title: `P50 ${fmtPct(a.p50)}: plan the exit before entry`,
      detail:
        'The position reaches half its max profit before expiration on that share of simulated paths. Taking profits at 50% of max and redeploying typically raises win rate and smooths returns versus holding to expiration.',
    })
  }
  if (t.side === 'long') {
    recs.push({
      severity: 'info',
      title: 'Set a profit target and a time stop',
      detail: `P50 here is the chance of a 50% gain on the debit at some point before expiry (${fmtPct(a.p50)}). Long options bleed theta, so pair a profit target with a date to exit if the move hasn't happened.`,
    })
  }

  const order: Record<Severity, number> = { warning: 0, suggestion: 1, info: 2 }
  return recs.sort((x, y) => order[x.severity] - order[y.severity])
}
