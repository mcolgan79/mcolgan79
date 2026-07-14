import { fmtMoney, fmtNum } from '../lib/format'
import type { Analysis, TradeInputs } from '../lib/types'

interface Props {
  t: TradeInputs
  a: Analysis
}

export function GreeksTable({ t, a }: Props) {
  const scale = t.multiplier * t.contracts
  const rows = [
    { name: 'Delta', per: a.greeks.delta, pos: a.greeks.delta * scale, unit: 'Δ shares', digits: 4 },
    { name: 'Gamma', per: a.greeks.gamma, pos: a.greeks.gamma * scale, unit: 'Δ per $1 move', digits: 4 },
    { name: 'Theta', per: a.greeks.theta, pos: a.greeks.theta * scale, unit: '$ per day', digits: 4 },
    { name: 'Vega', per: a.greeks.vega, pos: a.greeks.vega * scale, unit: '$ per IV pt', digits: 4 },
    { name: 'Rho', per: a.greeks.rho, pos: a.greeks.rho * scale, unit: '$ per rate pt', digits: 4 },
  ]
  return (
    <div className="card">
      <h2>Position Greeks</h2>
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
                <td>{fmtNum(r.per, r.digits)}</td>
                <td>
                  {r.name === 'Delta' || r.name === 'Gamma'
                    ? fmtNum(r.pos, 1)
                    : fmtMoney(r.pos, 2)}
                </td>
                <td style={{ textAlign: 'left', color: 'var(--text-muted)' }}>{r.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="chart-note">
        Model fair value: {fmtMoney(a.fairValue, 2)} per share
        {Math.abs(a.fairValue - t.premium) > 0.01
          ? ` — entered premium is ${t.premium > a.fairValue ? 'above' : 'below'} model by ${fmtMoney(Math.abs(t.premium - a.fairValue), 2)}`
          : ' (matches the entered premium)'}
        .
      </p>
    </div>
  )
}
