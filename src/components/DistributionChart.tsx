import { useMemo, useState } from 'react'
import { fmtNum, fmtPct, ticks } from '../lib/format'
import { probAbove, terminalPdf } from '../lib/probability'
import { pnlAtHorizon, singleExpiry } from '../lib/strategy'
import type { Strategy, StrategyAnalysis } from '../lib/types'
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
  st: Strategy
  a: StrategyAnalysis
}

/** Model distribution of the underlying at the front expiration, profit region shaded. */
export function DistributionChart({ st, a }: Props) {
  const [wrapRef, width] = useMeasuredWidth<HTMLDivElement>()
  const [tableView, setTableView] = useState(false)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  const gbm = { S: st.S, T: a.T, sigma: a.sigma, r: st.r, q: st.q }
  const horizonWord = singleExpiry(st) ? 'expiration' : 'the front expiration'

  const data = useMemo(() => {
    const [lo, hi] = a.domain
    const n = 161
    const prices: number[] = []
    const dens: number[] = []
    const profit: boolean[] = []
    for (let i = 0; i < n; i++) {
      const s = lo + ((hi - lo) * i) / (n - 1)
      prices.push(s)
      dens.push(terminalPdf(s, gbm))
      profit.push(pnlAtHorizon(st, s) > 0)
    }
    return { prices, dens, profit, lo, hi }
  }, [st, a, gbm])

  const height = M.top + PLOT_H + M.bottom
  const plotW = Math.max(width - M.left - M.right, 80)
  const x = linearScale([data.lo, data.hi], [M.left, M.left + plotW])
  const dMax = Math.max(...data.dens) || 1
  const y = linearScale([0, dMax * 1.06], [M.top + PLOT_H, M.top])
  const y0 = M.top + PLOT_H

  const xs = data.prices.map((p) => x(p))
  const linePath = polylinePath(xs, data.dens.map((d) => y(d)))
  const areaPath = `${linePath}L${x(data.hi).toFixed(2)},${y0}L${x(data.lo).toFixed(2)},${y0}Z`

  // Contiguous profit intervals along the price axis (condors/calendars have a middle one)
  const profitRects: Array<[number, number]> = []
  let start: number | null = null
  for (let i = 0; i < data.prices.length; i++) {
    if (data.profit[i] && start === null) start = xs[i]
    if ((!data.profit[i] || i === data.prices.length - 1) && start !== null) {
      profitRects.push([start, xs[i]])
      start = null
    }
  }
  const widest = profitRects.reduce<[number, number] | null>(
    (best, r) => (best === null || r[1] - r[0] > best[1] - best[0] ? r : best),
    null,
  )

  const xTicks = ticks(data.lo, data.hi, Math.max(Math.floor(plotW / 90), 3))
  const breakevens = a.breakevens.filter((b) => b > data.lo && b < data.hi).slice(0, 3)

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
              label: 'chance of finishing above',
            },
            {
              value: data.profit[idx] ? 'profit' : 'loss',
              label: `outcome at ${horizonWord}`,
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
    { q: '−2σ', s: st.S - 2 * a.expectedMove },
    { q: '−1σ', s: st.S - a.expectedMove },
    { q: 'Spot', s: st.S },
    { q: '+1σ', s: st.S + a.expectedMove },
    { q: '+2σ', s: st.S + 2 * a.expectedMove },
  ]

  return (
    <div className="card chart-card">
      <div className="chart-head">
        <h2>Where the model expects the underlying at {horizonWord}</h2>
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
                <th scope="col">Chance of finishing above</th>
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
            aria-label="Probability distribution of the underlying price with the profit region shaded"
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
            <line x1={x(st.S)} x2={x(st.S)} y1={M.top} y2={y0} stroke="var(--baseline)" strokeWidth={1} />
            <text x={x(st.S)} y={M.top - 8} textAnchor="middle" className="marker-text">
              Spot
            </text>
            {breakevens.map((be) => (
              <g key={be}>
                <line x1={x(be)} x2={x(be)} y1={M.top} y2={y0} stroke="var(--text-muted)" strokeWidth={1} />
                <text
                  x={x(be)}
                  y={M.top - 8}
                  textAnchor="middle"
                  className="marker-text"
                  style={{
                    display: Math.abs(x(be) - x(st.S)) < 44 ? 'none' : undefined,
                  }}
                >
                  BE {fmtNum(be)}
                </text>
              </g>
            ))}

            {/* profit-region label on the widest region */}
            {widest ? (
              <text
                x={(widest[0] + widest[1]) / 2}
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
        Lognormal distribution implied by the position's vega-weighted IV (
        {fmtPct(a.sigma, 0)}). The shaded slices are where the trade profits at{' '}
        {horizonWord} — their combined area is the POP.
      </p>
    </div>
  )
}
