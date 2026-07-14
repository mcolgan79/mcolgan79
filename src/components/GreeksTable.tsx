import { fmtMoney, fmtNum } from '../lib/format'
import type { Strategy, StrategyAnalysis } from '../lib/types'

interface Props {
  st: Strategy
  a: StrategyAnalysis
}

export function GreeksTable({ st, a }: Props) {
  const scale = st.multiplier * st.contracts
  const rows = [
    { name: 'Delta', per: a.greeks.delta, pos: a.greeks.delta * scale, unit: 'Δ shares', money: false },
    { name: 'Gamma', per: a.greeks.gamma, pos: a.greeks.gamma * scale, unit: 'Δ per $1 move', money: false },
    { name: 'Theta', per: a.greeks.theta, pos: a.greeks.theta * scale, unit: '$ per day', money: true },
    { name: 'Vega', per: a.greeks.vega, pos: a.greeks.vega * scale, unit: '$ per IV pt', money: true },
    { name: 'Rho', per: a.greeks.rho, pos: a.greeks.rho * scale, unit: '$ per rate pt', money: true },
  ]
  const isCredit = a.netCost < 0
  const fairDiff = a.fairValue - a.netCost
  return (
    <div className="card">
      <h2>Net position Greeks</h2>
      <div className="table-scroll">
        <table className="data-table greeks-table">
          <thead>
            <tr>
              <th scope="col">Greek</th>
              <th scope="col">Per share</th>
              <th scope="col">Position</th>
              <th scope="col" style={{ textAlign: 'left' }}>
                Position units
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <td>{r.name}</td>
                <td>{fmtNum(r.per, 4)}</td>
                <td>{r.money ? fmtMoney(r.pos, 2) : fmtNum(r.pos, 1)}</td>
                <td style={{ textAlign: 'left', color: 'var(--text-muted)' }}>{r.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="chart-note">
        Summed across all legs, each at its own expiration and IV. Entered net{' '}
        {isCredit ? 'credit' : 'debit'}: {fmtMoney(Math.abs(a.netCost) * st.multiplier, 2)} per
        spread
        {Math.abs(fairDiff) > 0.01
          ? ` — ${fmtMoney(Math.abs(fairDiff) * st.multiplier, 2)} ${fairDiff > 0 ? 'better' : 'worse'} than the model's value`
          : ' (matches the model value)'}
        .
      </p>
    </div>
  )
}
