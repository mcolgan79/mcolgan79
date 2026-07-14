import { useMemo, useState } from 'react'
import { fmtNum, fmtPct, ticks } from '../lib/format'
import {
  gbmFromInputs,
  payoffAtExpiry,
  probAbove,
  terminalPdf,
} from '../lib/probability'
import type { Analysis, TradeInputs } from '../lib/types'
import {
  ChartTooltip,
  linearScale,
  polylinePath,
  useMeasuredWidth,
  type TooltipState,
} from './chart-utils'

const M = { top: 22, right: 24, bottom: 34, left: 24 }
const PLOT_H = 190

interface Props {
  t: TradeInputs
  a: Analysis
}

/** Model distribution of the underlying at expiration, profit region shaded. */
export function DistributionChart({ t, a }: Props) {
  const [wrapRef, width] = useMeasuredWidth<HTMLDivElement>()
  const [tableView, setTableView] = useState(false)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  const gbm = gbmFromInputs(t)
  const data = useMemo(() => {
    const em = Math.max(a.expectedMove, t.S * 0.02)
    const lo = Math.max(Math.min(t.S - 3.2 * em, a.breakeven * 0.97), 0.01)
    const hi = Math.max(t.S + 3.2 * em, a.breakeven * 1.03)
    const n = 161
    const prices: number[] = []
    const dens: number[] = []
    const profit: boolean[] = []
    for (let i = 0; i < n; i++) {
      const s = lo + ((hi - lo) * i) / (n - 1)
      prices.push(s)
      dens.push(terminalPdf(s, gbm))
      profit.push(payoffAtExpiry(s, t) > 0)
    }
    return { prices, dens, profit, lo, hi, em }
  }, [t, a, gbm])

  const height = M.top + PLOT_H + M.bottom
  const plotW = Math.max(width - M.left - M.right, 80)
  const x = linearScale([data.lo, data.hi], [M.left, M.left + plotW])
  const dMax = Math.max(...data.dens) || 1
  const y = linearScale([0, dMax * 1.06], [M.top + PLOT_H, M.top])
  const y0 = M.top + PLOT_H

  const xs = data.prices.map((p) => x(p))
  const linePath = polylinePath(xs, data.dens.map((d) => y(d)))
  const areaPath = `${linePath}L${x(data.hi).toFixed(2)},${y0}L${x(data.lo).toFixed(2)},${y0}Z`

  // Contiguous profit intervals along the price axis (one for a single leg)
  const profitRects: Array<[number, number]> = []
  let start: number | null = null
  for (let i = 0; i < data.prices.length; i++) {
    if (data.profit[i] && start === null) start = xs[i]
    if ((!data.profit[i] || i === data.prices.length - 1) && start !== null) {
      profitRects.push([start, xs[i]])
      start = null
    }
  }

  const xTicks = ticks(data.lo, data.hi, Math.max(Math.floor(plotW / 90), 3))

  const idx = hoverIdx
  const tip: TooltipState | null =
    idx === null
      ? null
      : {
          px: xs[idx],
          py: y(data.dens[idx]),
          title: `Underlying at ${fmtNum(data.prices[idx])}`,
          rows: [
            {
              value: fmtPct(probAbove(data.prices[idx], gbm)),
              label: 'chance of expiring above',
            },
            {
              value: data.profit[idx] ? 'profit' : 'loss',
              label: 'expiration outcome here',
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

  const quantiles = [
    { q: '−2σ', s: t.S - 2 * data.em },
    { q: '−1σ', s: t.S - data.em },
    { q: 'Spot', s: t.S },
    { q: '+1σ', s: t.S + data.em },
    { q: '+2σ', s: t.S + 2 * data.em },
  ]

  return (
    <div className="card chart-card">
      <div className="chart-head">
        <h2>Where the model expects the underlying at expiration</h2>
        <button className="view-toggle" onClick={() => setTableView((v) => !v)}>
          {tableView ? 'Chart' : 'Data'}
        </button>
      </div>

      {tableView ? (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Level</th>
                <th scope="col">Underlying</th>
                <th scope="col">Chance of expiring above</th>
              </tr>
            </thead>
            <tbody>
              {quantiles.map((r) => (
                <tr key={r.q}>
                  <td>{r.q}</td>
                  <td>{fmtNum(Math.max(r.s, 0))}</td>
                  <td>{fmtPct(probAbove(Math.max(r.s, 0.01), gbm))}</td>
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
            aria-label="Probability distribution of the underlying price at expiration with the profit region shaded"
          >
            <defs>
              <clipPath id="clip-dist-profit">
                {profitRects.map(([x0, x1], i) => (
                  <rect key={i} x={x0} y={M.top - 4} width={Math.max(x1 - x0, 0)} height={PLOT_H + 8} />
                ))}
              </clipPath>
            </defs>

            {/* density wash + profit-region emphasis */}
            <path d={areaPath} fill="var(--series-1)" opacity={0.1} />
            <path d={areaPath} fill="var(--good)" opacity={0.28} clipPath="url(#clip-dist-profit)" />
            <path d={linePath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

            {/* baseline */}
            <line x1={M.left} x2={M.left + plotW} y1={y0} y2={y0} stroke="var(--baseline)" strokeWidth={1} />

            {/* spot & breakeven hairlines */}
            <line x1={x(t.S)} x2={x(t.S)} y1={M.top} y2={y0} stroke="var(--baseline)" strokeWidth={1} />
            <text x={x(t.S)} y={M.top - 8} textAnchor="middle" className="marker-text">
              Spot
            </text>
            {a.breakeven > data.lo && a.breakeven < data.hi ? (
              <g>
                <line x1={x(a.breakeven)} x2={x(a.breakeven)} y1={M.top} y2={y0} stroke="var(--text-muted)" strokeWidth={1} />
                <text
                  x={x(a.breakeven)}
                  y={M.top - 8}
                  textAnchor="middle"
                  className="marker-text"
                  style={{
                    display: Math.abs(x(a.breakeven) - x(t.S)) < 44 ? 'none' : undefined,
                  }}
                >
                  BE {fmtNum(a.breakeven)}
                </text>
              </g>
            ) : null}

            {/* profit-region label */}
            {profitRects.length > 0 ? (
              <text
                x={(profitRects[0][0] + profitRects[0][1]) / 2}
                y={y0 - 8}
                textAnchor="middle"
                className="series-label"
              >
                profit {fmtPct(a.pop, 0)}
              </text>
            ) : null}

            {/* x axis */}
            {xTicks.map((v) => (
              <text key={v} x={x(v)} y={y0 + 17} textAnchor="middle" className="axis-text">
                {fmtNum(v, v % 1 === 0 ? 0 : 2)}
              </text>
            ))}

            {/* crosshair */}
            {idx !== null ? (
              <g>
                <line x1={xs[idx]} x2={xs[idx]} y1={M.top} y2={y0} stroke="var(--text-muted)" strokeWidth={1} />
                <circle cx={xs[idx]} cy={y(data.dens[idx])} r={6.5} fill="var(--surface-1)" />
                <circle cx={xs[idx]} cy={y(data.dens[idx])} r={4.5} fill="var(--series-1)" />
              </g>
            ) : null}

            <rect
              x={M.left}
              y={M.top}
              width={plotW}
              height={PLOT_H}
              fill="transparent"
              tabIndex={0}
              aria-label="Explore the distribution by price; use arrow keys"
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
        Lognormal distribution implied by the entered IV. The shaded slice is where the
        trade is profitable at expiration — its area is the POP.
      </p>
    </div>
  )
}
