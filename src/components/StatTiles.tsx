import { fmtMoney, fmtNum, fmtPct } from '../lib/format'
import type { Analysis, TradeInputs } from '../lib/types'

interface Props {
  t: TradeInputs
  a: Analysis
}

export function StatTiles({ t, a }: Props) {
  const otm = t.type === 'call' ? t.K > t.S : t.K < t.S
  return (
    <div className="tiles">
      <div className="tile hero">
        <div className="label">Probability of profit</div>
        <div className="value">{fmtPct(a.pop, 1)}</div>
        <div className="sub">at expiration, model-implied</div>
      </div>
      <div className="tile">
        <div className="label">P50</div>
        <div className="value">{fmtPct(a.p50, 1)}</div>
        <div className="sub">
          {t.side === 'short' ? 'hits 50% of max profit early' : 'hits +50% on debit early'}
        </div>
      </div>
      <div className="tile">
        <div className="label">Prob. of touching strike</div>
        <div className="value">{fmtPct(a.probTouchStrike, 1)}</div>
        <div className="sub">{otm ? 'before expiration' : 'strike is already ITM side'}</div>
      </div>
      <div className="tile">
        <div className="label">Prob. of touching breakeven</div>
        <div className="value">{fmtPct(a.probTouchBreakeven, 1)}</div>
        <div className="sub">BE {fmtNum(a.breakeven)}</div>
      </div>
      <div className="tile">
        <div className="label">Max profit</div>
        <div className="value pos">{fmtMoney(a.maxProfit)}</div>
        <div className="sub">
          {t.side === 'short' ? 'the credit received' : 'at expiration'}
        </div>
      </div>
      <div className="tile">
        <div className="label">Max loss</div>
        <div className="value neg">{fmtMoney(a.maxLoss)}</div>
        <div className="sub">
          {t.side === 'short' && t.type === 'call' ? 'unlimited upside risk' : 'at expiration'}
        </div>
      </div>
      <div className="tile">
        <div className="label">Expected move (1σ)</div>
        <div className="value">±{fmtNum(a.expectedMove)}</div>
        <div className="sub">
          {fmtNum(t.S - a.expectedMove)} – {fmtNum(t.S + a.expectedMove)} by expiry
        </div>
      </div>
      <div className="tile">
        <div className="label">Reward / risk</div>
        <div className="value">
          {Number.isFinite(a.riskReward) ? fmtNum(a.riskReward) : '∞'}
        </div>
        <div className="sub">max profit per $1 of max risk</div>
      </div>
    </div>
  )
}
