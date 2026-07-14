import { fmtMoney, fmtNum, fmtPct } from '../lib/format'
import type { Strategy, StrategyAnalysis } from '../lib/types'

interface Props {
  st: Strategy
  a: StrategyAnalysis
}

const KIND_LABEL: Record<StrategyAnalysis['kind'], string> = {
  single: 'single option',
  'vertical-credit': 'credit vertical',
  'vertical-debit': 'debit vertical',
  'iron-condor': 'iron condor',
  calendar: 'calendar',
  diagonal: 'diagonal',
  straddle: 'straddle',
  strangle: 'strangle',
  custom: 'custom spread',
}

export function StatTiles({ st, a }: Props) {
  const scale = st.multiplier * st.contracts
  const isCredit = a.netCost < 0
  return (
    <div className="tiles">
      <div className="tile hero">
        <div className="label">Probability of profit</div>
        <div className="value">{fmtPct(a.pop, 1)}</div>
        <div className="sub">{KIND_LABEL[a.kind]}, model-implied</div>
      </div>
      <div className="tile">
        <div className="label">P50</div>
        <div className="value">{fmtPct(a.p50, 1)}</div>
        <div className="sub">hits {a.p50TargetLabel} early</div>
      </div>
      <div className="tile">
        <div className="label">{isCredit ? 'Net credit' : 'Net debit'}</div>
        <div className="value">{fmtMoney(Math.abs(a.netCost) * scale)}</div>
        <div className="sub">
          {fmtNum(Math.abs(a.netCost), 2)}/share × {st.contracts} spread{st.contracts > 1 ? 's' : ''}
        </div>
      </div>
      <div className="tile">
        <div className="label">Max profit</div>
        <div className="value pos">{fmtMoney(a.maxProfit)}</div>
        <div className="sub">at {a.horizonDte} DTE horizon</div>
      </div>
      <div className="tile">
        <div className="label">Max loss</div>
        <div className="value neg">{fmtMoney(a.maxLoss)}</div>
        <div className="sub">
          {Number.isFinite(a.maxLoss) ? `at ${a.horizonDte} DTE horizon` : 'undefined risk'}
        </div>
      </div>
      {a.probTouch.slice(0, 2).map((t) => (
        <div className="tile" key={t.level}>
          <div className="label">Touch BE {fmtNum(t.level)}</div>
          <div className="value">{fmtPct(t.prob, 1)}</div>
          <div className="sub">before the front expiry</div>
        </div>
      ))}
      <div className="tile">
        <div className="label">Expected move (1σ)</div>
        <div className="value">±{fmtNum(a.expectedMove)}</div>
        <div className="sub">
          {fmtNum(st.S - a.expectedMove)} – {fmtNum(st.S + a.expectedMove)} by front expiry
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
