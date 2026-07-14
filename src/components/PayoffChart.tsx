import { useMemo, useState } from 'react'
import { bsPrice } from '../lib/black-scholes'
import { fmtMoney, fmtNum, fmtPct, ticks } from '../lib/format'
import { gbmFromInputs, payoffAtExpiry, probAbove } from '../lib/probability'
import type { Analysis, TradeInputs } from '../lib/types'
import {
  ChartTooltip,
  linearScale,
  polylinePath,
  useMeasuredWidth,
  type TooltipState,
} from './chart-utils'

const M = { top: 20, right: 96, bottom: 34, left: 60 }
const PLOT_H = 280

interface Props {
  t: TradeInputs
  a: Analysis
}

export function PayoffChart({ t, a }: Props) {
  const [wrapRef, width] = useMeasuredWidth<HTMLDivElement>()
  const [tableView, setTableView] = useState(false)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  const data = useMemo(() => {
    const em = Math.max(a.expectedMove, t.S * 0.02)
    const lo = Math.max(Math.min(t.S - 3.2 * em, t.K * 0.97, a.breakeven * 0.97), 0.01)
    const hi = Math.max(t.S + 3.2 * em, t.K * 1.03, a.breakeven * 1.03)
    const n = 161
    const prices: number[] = []
    const expPnl: number[] = []
    const nowPnl: number[] = []
    const scale = t.multiplier * t.contracts
    const sign = t.side === 'long' ? 1 : -1
    for (let i = 0; i < n; i++) {
      const s = lo + ((hi - lo) * i) / (n - 1)
      prices.push(s)
      expPnl.push(payoffAtExpiry(s, t))
      const v = bsPrice(t.type, {
        S: s,
        K: t.K,
        T: a.yearsToExpiry,
        sigma: t.iv,
        r: t.r,
        q: t.q,
      })
      nowPnl.push(sign * (v - t.premium) * scale)
    }
    return { prices, expPnl, nowPnl, lo, hi, em }
  }, [t, a])

  const height = M.top + PLOT_H + M.bottom
  const plotW = Math.max(width - M.left - M.right, 80)

  const yMin = Math.min(...data.expPnl, ...data.nowPnl, 0)
  const yMax = Math.max(...data.expPnl, ...data.nowPnl, 0)
  const pad = (yMax - yMin || 1) * 0.08
  const x = linearScale([data.lo, data.hi], [M.left, M.left + plotW])
  const y = linearScale([yMin - pad, yMax + pad], [M.top + PLOT_H, M.top])
  const y0 = y(0)

  const xs = data.prices.map((p) => x(p))
  const expPath = polylinePath(xs, data.expPnl.map((v) => y(v)))
  const nowPath = polylinePath(xs, data.nowPnl.map((v) => y(v)))
  const areaPath = `${expPath}L${x(data.hi).toFixed(2)},${y0.toFixed(2)}L${x(data.lo).toFixed(2)},${y0.toFixed(2)}Z`

  const xTicks = ticks(data.lo, data.hi, Math.max(Math.floor(plotW / 90), 3))
  const yTicks = ticks(y.domain[0], y.domain[1], 6)

  const idx =
    hoverIdx === null ? null : Math.min(Math.max(hoverIdx, 0), data.prices.length - 1)
  const tip: TooltipState | null =
    idx === null
      ? null
      : {
          px: xs[idx],
          py: Math.min(y(data.expPnl[idx]), y(data.nowPnl[idx])),
          title: `Underlying at ${fmtNum(data.prices[idx])}`,
          rows: [
            {
              color: 'var(--series-1)',
              value: fmtMoney(data.expPnl[idx]),
              label: 'at expiration',
            },
            {
              color: 'var(--series-2)',
              value: fmtMoney(data.nowPnl[idx]),
              label: 'today (T+0)',
            },
            {
              value: fmtPct(1 - probAbove(data.prices[idx], gbmFromInputs(t))),
              label: 'chance of expiring below',
            },
          ],
        }

  function onPointer(e: React.PointerEvent<SVGRectElement>) {
    const rect = e.currentTarget.closest('svg')!.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * width
    const s = x.invert(px)
    const i = Math.round(((s - data.lo) / (data.hi - data.lo)) * (data.prices.length - 1))
    setHoverIdx(Math.min(Math.max(i, 0), data.prices.length - 1))
  }
  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowRight') setHoverIdx((i) => Math.min((i ?? 80) + 4, 160))
    else if (e.key === 'ArrowLeft') setHoverIdx((i) => Math.max((i ?? 80) - 4, 0))
    else if (e.key === 'Escape') setHoverIdx(null)
  }

  // Direct end labels; nudge apart when the curves converge at the right edge
  const expEndY = y(data.expPnl[data.expPnl.length - 1])
  const nowEndY = y(data.nowPnl[data.nowPnl.length - 1])
  let expLabelY = expEndY
  let nowLabelY = nowEndY
  if (Math.abs(expEndY - nowEndY) < 16) {
    const mid = (expEndY + nowEndY) / 2
    expLabelY = mid + (expEndY <= nowEndY ? -9 : 9)
    nowLabelY = mid + (expEndY <= nowEndY ? 9 : -9)
  }

  const emLeft = Math.max(t.S - data.em, data.lo)
  const emRight = Math.min(t.S + data.em, data.hi)

  const tableRows = xTicks.map((p) => {
    const i = Math.round(((p - data.lo) / (data.hi - data.lo)) * (data.prices.length - 1))
    return { price: p, exp: data.expPnl[i], now: data.nowPnl[i] }
  })

  return (
    <div className="card chart-card">
      <div className="chart-head">
        <h2>P&amp;L vs. underlying price</h2>
        <div className="legend" aria-hidden={tableView}>
          <span className="key">
            <span className="swatch-line" style={{ color: 'var(--series-1)' }} />
            At expiration
          </span>
          <span className="key">
            <span className="swatch-line" style={{ color: 'var(--series-2)' }} />
            Today (T+0)
          </span>
        </div>
        <button className="view-toggle" onClick={() => setTableView((v) => !v)}>
          {tableView ? 'Chart' : 'Data'}
        </button>
      </div>

      {tableView ? (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Underlying</th>
                <th scope="col">P&amp;L at expiration</th>
                <th scope="col">P&amp;L today (T+0)</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((r) => (
                <tr key={r.price}>
                  <td>{fmtNum(r.price)}</td>
                  <td>{fmtMoney(r.exp)}</td>
                  <td>{fmtMoney(r.now)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart-wrap" ref={wrapRef}>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="Profit and loss versus underlying price, at expiration and today"
          >
            <defs>
              <clipPath id="clip-profit">
                <rect x={M.left} y={M.top - 2} width={plotW} height={Math.max(y0 - M.top + 2, 0)} />
              </clipPath>
              <clipPath id="clip-loss">
                <rect x={M.left} y={y0} width={plotW} height={Math.max(M.top + PLOT_H - y0 + 2, 0)} />
              </clipPath>
            </defs>

            {/* expected-move band (±1σ) */}
            <rect
              x={x(emLeft)}
              y={M.top}
              width={Math.max(x(emRight) - x(emLeft), 0)}
              height={PLOT_H}
              fill="var(--grid)"
              opacity={0.35}
            />
            <text x={x(t.S)} y={M.top - 7} textAnchor="middle" className="axis-text">
              ±1σ expected move
            </text>

            {/* gridlines */}
            {yTicks.map((v) => (
              <line
                key={v}
                x1={M.left}
                x2={M.left + plotW}
                y1={y(v)}
                y2={y(v)}
                stroke="var(--grid)"
                strokeWidth={1}
              />
            ))}

            {/* profit / loss washes under the expiration curve */}
            <path d={areaPath} fill="var(--good)" opacity={0.1} clipPath="url(#clip-profit)" />
            <path d={areaPath} fill="var(--critical)" opacity={0.1} clipPath="url(#clip-loss)" />

            {/* zero baseline */}
            <line x1={M.left} x2={M.left + plotW} y1={y0} y2={y0} stroke="var(--baseline)" strokeWidth={1} />

            {/* spot hairline */}
            <line x1={x(t.S)} x2={x(t.S)} y1={M.top} y2={M.top + PLOT_H} stroke="var(--baseline)" strokeWidth={1} />
            <text x={x(t.S) + 4} y={M.top + 12} className="marker-text">
              Spot {fmtNum(t.S)}
            </text>

            {/* series */}
            <path d={nowPath} fill="none" stroke="var(--series-2)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            <path d={expPath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

            {/* breakeven marker on the zero line */}
            {a.breakeven > data.lo && a.breakeven < data.hi ? (
              <g>
                <circle cx={x(a.breakeven)} cy={y0} r={6} fill="var(--surface-1)" />
                <circle cx={x(a.breakeven)} cy={y0} r={4} fill="var(--series-1)" />
                <text x={x(a.breakeven)} y={y0 - 10} textAnchor="middle" className="marker-text">
                  BE {fmtNum(a.breakeven)}
                </text>
              </g>
            ) : null}

            {/* strike tick on the x-axis */}
            <line x1={x(t.K)} x2={x(t.K)} y1={M.top + PLOT_H} y2={M.top + PLOT_H + 6} stroke="var(--text-muted)" strokeWidth={1.5} />
            <text x={x(t.K)} y={M.top + PLOT_H + 17} textAnchor="middle" className="axis-text">
              K {fmtNum(t.K, t.K % 1 === 0 ? 0 : 2)}
            </text>

            {/* direct series labels at the right edge */}
            <text x={M.left + plotW + 6} y={expLabelY + 4} className="series-label">
              Expiration
            </text>
            <text x={M.left + plotW + 6} y={nowLabelY + 4} className="series-label">
              Today
            </text>

            {/* axes */}
            {xTicks.map((v) =>
              Math.abs(x(v) - x(t.K)) < 24 ? null : (
                <text key={v} x={x(v)} y={M.top + PLOT_H + 17} textAnchor="middle" className="axis-text">
                  {fmtNum(v, v % 1 === 0 ? 0 : 2)}
                </text>
              ),
            )}
            {yTicks.map((v) => (
              <text key={v} x={M.left - 8} y={y(v) + 4} textAnchor="end" className="axis-text">
                {fmtMoney(v)}
              </text>
            ))}

            {/* crosshair */}
            {idx !== null ? (
              <g>
                <line x1={xs[idx]} x2={xs[idx]} y1={M.top} y2={M.top + PLOT_H} stroke="var(--text-muted)" strokeWidth={1} />
                <circle cx={xs[idx]} cy={y(data.expPnl[idx])} r={6.5} fill="var(--surface-1)" />
                <circle cx={xs[idx]} cy={y(data.expPnl[idx])} r={4.5} fill="var(--series-1)" />
                <circle cx={xs[idx]} cy={y(data.nowPnl[idx])} r={6.5} fill="var(--surface-1)" />
                <circle cx={xs[idx]} cy={y(data.nowPnl[idx])} r={4.5} fill="var(--series-2)" />
              </g>
            ) : null}

            {/* hover / focus layer */}
            <rect
              x={M.left}
              y={M.top}
              width={plotW}
              height={PLOT_H}
              fill="transparent"
              tabIndex={0}
              aria-label="Explore P&L by price; use arrow keys"
              onPointerMove={onPointer}
              onPointerDown={onPointer}
              onPointerLeave={() => setHoverIdx(null)}
              onKeyDown={onKey}
              onBlur={() => setHoverIdx(null)}
            />
          </svg>
          <ChartTooltip tip={tip} containerWidth={width} />
        </div>
      )}
      <p className="chart-note">
        Green wash = profit region at expiration, red = loss. The T+0 curve marks the
        position to model (Black–Scholes) if the underlying moved right now.
      </p>
    </div>
  )
}
