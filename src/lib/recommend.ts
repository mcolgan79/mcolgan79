import type { Leg, Strategy, StrategyAnalysis } from './types'

export type Severity = 'warning' | 'suggestion' | 'info'

export interface Recommendation {
  severity: Severity
  title: string
  detail: string
}

const pct = (x: number) => `${Math.round(x * 100)}%`
const usd = (x: number) =>
  Number.isFinite(x)
    ? `$${Math.abs(x).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : 'unlimited'

/** A short leg is naked when no long leg of the same type covers it. */
function nakedShorts(st: Strategy): Leg[] {
  return st.legs.filter((shortLeg) => {
    if (shortLeg.side !== 'short') return false
    const covered = st.legs.some(
      (l) =>
        l.side === 'long' &&
        l.type === shortLeg.type &&
        l.qty >= shortLeg.qty &&
        l.dte >= shortLeg.dte,
    )
    return !covered
  })
}

/**
 * Heuristic trade-improvement engine. Rules encode widely used guidelines
 * (DTE window, delta bands, credit-to-width, defined-risk conversion,
 * profit-taking at 50%). Educational, not advice.
 */
export function recommend(st: Strategy, a: StrategyAnalysis): Recommendation[] {
  const recs: Recommendation[] = []
  const scale = st.multiplier * st.contracts
  const isCredit = a.netCost < 0
  const shorts = st.legs.filter((l) => l.side === 'short')
  const naked = nakedShorts(st)

  // --- Undefined risk ---
  for (const leg of naked) {
    if (leg.type === 'call') {
      recs.push({
        severity: 'warning',
        title: `Naked short ${leg.K} call — unlimited risk`,
        detail:
          'No long call caps the upside. Buying a further-OTM call with the same or later expiration converts this into a defined-risk spread for a small piece of the credit.',
      })
    } else {
      recs.push({
        severity: 'info',
        title: `Short ${leg.K} put carries risk to zero`,
        detail: `Worst case is roughly ${usd(a.maxLoss)}. A long put below it would define the risk and cut buying-power use.`,
      })
    }
  }

  // --- Structure-specific checks ---
  if (a.kind === 'vertical-credit' || a.kind === 'iron-condor') {
    const strikes = [...new Set(st.legs.map((l) => l.K))].sort((x, y) => x - y)
    const puts = st.legs.filter((l) => l.type === 'put')
    const calls = st.legs.filter((l) => l.type === 'call')
    const width =
      a.kind === 'iron-condor'
        ? Math.max(
            Math.abs((puts[0]?.K ?? 0) - (puts[1]?.K ?? 0)),
            Math.abs((calls[0]?.K ?? 0) - (calls[1]?.K ?? 0)),
          )
        : Math.abs(strikes[0] - (strikes[1] ?? strikes[0]))
    const credit = -a.netCost
    if (width > 0 && credit / width < 1 / 3) {
      recs.push({
        severity: 'suggestion',
        title: `Thin credit for the width (${pct(credit / width)} of $${width.toFixed(2)})`,
        detail:
          'A common target is collecting at least one-third of the spread width. Tightening the wings, moving the short strike closer, or more DTE would improve credit-to-width — each trades off POP or duration.',
      })
    }
  }

  if (a.kind === 'vertical-debit') {
    const strikes = st.legs.map((l) => l.K).sort((x, y) => x - y)
    const width = Math.abs(strikes[1] - strikes[0])
    if (width > 0 && a.netCost / width > 0.6) {
      recs.push({
        severity: 'suggestion',
        title: `Paying ${pct(a.netCost / width)} of the width`,
        detail:
          'Debit spreads price roughly at the probability of finishing through both strikes; paying over ~60% of the width needs a strong directional edge. A cheaper strike pair (further OTM) or more time improves the risk/reward.',
      })
    }
  }

  if (a.kind === 'iron-condor') {
    const shortsInside = shorts.filter(
      (l) => Math.abs(l.K - st.S) < a.expectedMove,
    )
    if (shortsInside.length > 0) {
      recs.push({
        severity: 'warning',
        title: 'Short strike inside the expected move',
        detail: `${shortsInside.map((l) => `${l.K} ${l.type}`).join(' and ')} sit within the ±1σ range (${(st.S - a.expectedMove).toFixed(2)} – ${(st.S + a.expectedMove).toFixed(2)}). Condors are usually sold with short strikes outside 1σ (~16Δ) so the underlying can wander without testing them.`,
      })
    }
  }

  if (a.kind === 'calendar' || a.kind === 'diagonal') {
    recs.push({
      severity: 'info',
      title: 'Term structure matters here',
      detail:
        'This model prices both expirations with the IVs you entered and assumes they hold. Calendars/diagonals profit mostly from the front leg decaying faster and from front IV falling versus back IV — check the actual term structure (and earnings dates between the two expirations) before trusting the payoff curve.',
    })
    const front = st.legs.reduce((m, l) => (l.dte < m.dte ? l : m))
    if (front.side === 'short' && a.kind === 'calendar') {
      const dist = Math.abs(front.K - st.S)
      if (dist > a.expectedMove) {
        recs.push({
          severity: 'suggestion',
          title: 'Calendar strike far from the expected price',
          detail: `The P&L of a calendar peaks when the underlying pins the strike at front expiration. ${front.K} is more than 1σ (${a.expectedMove.toFixed(2)}) from spot — a strike nearer where you expect the underlying raises the odds of landing on the tent pole.`,
        })
      }
    }
  }

  // --- DTE window ---
  const frontShort = shorts.length ? Math.min(...shorts.map((l) => l.dte)) : null
  if (frontShort !== null && frontShort < 21) {
    recs.push({
      severity: 'warning',
      title: `Short premium at ${frontShort} DTE`,
      detail:
        'Gamma risk grows quickly in the final weeks: small moves swing the P&L hard. The commonly used window for opening short premium is 30–45 DTE, managing or rolling at ~21 DTE.',
    })
  } else if (frontShort !== null && frontShort > 60 && isCredit) {
    recs.push({
      severity: 'suggestion',
      title: 'Long-dated short premium decays slowly',
      detail:
        'Theta is small this far out; most decay happens inside 45 days. Consider 30–45 DTE for a better decay-per-day profile.',
    })
  }
  if (st.legs.every((l) => l.side === 'long') && a.horizonDte < 21) {
    recs.push({
      severity: 'warning',
      title: 'Long premium with little time',
      detail: `Theta is costing about $${Math.abs(a.greeks.theta * scale).toFixed(0)}/day and accelerates into expiration. More time (60–90+ DTE) or deeper ITM strikes reduce the decay drag.`,
    })
  }

  // --- Probabilities ---
  if (isCredit && a.pop < 0.6) {
    recs.push({
      severity: 'suggestion',
      title: `POP is only ${pct(a.pop)} for a credit trade`,
      detail:
        'Credit strategies usually target a high probability of profit. Moving short strikes further out-of-the-money (roughly 16–30Δ) raises POP in exchange for less credit.',
    })
  }
  if (!isCredit && a.pop < 0.35) {
    recs.push({
      severity: 'suggestion',
      title: `Low odds: POP is ${pct(a.pop)}`,
      detail:
        a.breakevens.length > 0
          ? `Breakeven is ${a.breakevens.map((b) => b.toFixed(2)).join(' / ')}. Strikes closer to the money — or selling a further-OTM option against a long leg — lower the breakeven and raise POP, at the cost of capping upside.`
          : 'Strikes closer to the money — or spreading the position — would raise the odds, at the cost of capping upside.',
    })
  }
  const testedBe = a.probTouch.find((t) => t.prob > 0.5)
  if (isCredit && testedBe) {
    recs.push({
      severity: 'info',
      title: `Expect the position to be tested (${pct(testedBe.prob)} touch of ${testedBe.level.toFixed(2)})`,
      detail:
        'Probability of touch runs about twice the probability of expiring beyond a level, so the trade will likely show a loss at some point even if it wins at expiration. Size so a test is tolerable.',
    })
  }

  // --- Volatility regime (via net vega) ---
  const richIv = a.sigma >= 0.45
  const thinIv = a.sigma <= 0.18
  if (richIv && a.greeks.vega > 0.01) {
    recs.push({
      severity: 'suggestion',
      title: `Long vega into a rich IV (${(a.sigma * 100).toFixed(0)}%)`,
      detail:
        'The position gains if IV rises further, but high IV tends to contract — vega losses can swamp a correct directional call. Structures that sell an option against the long leg (spreads, diagonals) neutralize much of the vega.',
    })
  }
  if (thinIv && a.greeks.vega < -0.01) {
    recs.push({
      severity: 'suggestion',
      title: `Short vega in a thin IV (${(a.sigma * 100).toFixed(0)}%)`,
      detail:
        'Low IV means little premium relative to the risk, and an IV expansion works against the position. Long premium or debit structures are usually favored in low-IV regimes. (Check IV rank against the past year to confirm.)',
    })
  }

  // --- Risk / reward ---
  if (Number.isFinite(a.riskReward) && a.riskReward < 0.25 && a.pop < 0.85) {
    recs.push({
      severity: 'warning',
      title: `Thin reward for the risk (${a.riskReward.toFixed(2)} : 1)`,
      detail: `Max profit ${usd(a.maxProfit)} vs. max loss ${usd(a.maxLoss)}. Risking several times the potential reward needs a very high POP for positive expectancy — tighten the wings or take strikes with more credit.`,
    })
  }

  // --- Management ---
  if (isCredit && a.p50 > 0) {
    recs.push({
      severity: 'info',
      title: `P50 ${pct(a.p50)}: plan the exit before entry`,
      detail:
        'The position reaches half its max profit before the front expiration on that share of simulated paths. Taking profits at 50% of max and redeploying typically raises win rate and smooths returns versus holding to expiration.',
    })
  } else if (!isCredit) {
    recs.push({
      severity: 'info',
      title: 'Set a profit target and a time stop',
      detail: `P50 here is the chance of hitting ${a.p50TargetLabel} at some point before the front expiration (${pct(a.p50)}). Debit trades bleed theta, so pair a profit target with a date to exit if the move hasn't happened.`,
    })
  }

  const order: Record<Severity, number> = { warning: 0, suggestion: 1, info: 2 }
  return recs.sort((x, y) => order[x.severity] - order[y.severity])
}
