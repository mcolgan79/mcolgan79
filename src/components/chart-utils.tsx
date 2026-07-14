import { useEffect, useRef, useState } from 'react'

/** Observe a container's rendered width so SVG charts stay responsive. */
export function useMeasuredWidth<T extends HTMLElement>(): [
  React.RefObject<T>,
  number,
] {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(640)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w) setWidth(w)
    })
    ro.observe(el)
    setWidth(el.getBoundingClientRect().width || 640)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

export interface Scale {
  (v: number): number
  invert: (px: number) => number
  domain: [number, number]
  range: [number, number]
}

export function linearScale(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain
  const [r0, r1] = range
  const m = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0)
  const fn = ((v: number) => r0 + (v - d0) * m) as Scale
  fn.invert = (px: number) => (m === 0 ? d0 : d0 + (px - r0) / m)
  fn.domain = domain
  fn.range = range
  return fn
}

export function polylinePath(xs: number[], ys: number[]): string {
  let d = ''
  for (let i = 0; i < xs.length; i++) {
    d += `${i === 0 ? 'M' : 'L'}${xs[i].toFixed(2)},${ys[i].toFixed(2)}`
  }
  return d
}

export interface TooltipRow {
  color?: string
  label: string
  value: string
}

export interface TooltipState {
  px: number
  py: number
  title: string
  rows: TooltipRow[]
}

/** Tooltip rendered from state; series/category names go in via textContent (JSX). */
export function ChartTooltip({
  tip,
  containerWidth,
}: {
  tip: TooltipState | null
  containerWidth: number
}) {
  if (!tip) return null
  const flip = tip.px > containerWidth - 190
  const style: React.CSSProperties = {
    left: flip ? undefined : tip.px + 14,
    right: flip ? containerWidth - tip.px + 14 : undefined,
    top: Math.max(tip.py - 20, 0),
  }
  return (
    <div className="tooltip" style={style} role="status">
      <div className="tt-title">{tip.title}</div>
      {tip.rows.map((r, i) => (
        <div className="tt-row" key={i}>
          {r.color ? <span className="tt-key" style={{ borderTopColor: r.color }} /> : null}
          <span className="tt-val">{r.value}</span>
          <span className="tt-label">{r.label}</span>
        </div>
      ))}
    </div>
  )
}
