export function fmtMoney(x: number, digits = 0): string {
  if (!Number.isFinite(x)) return x > 0 ? 'Unlimited' : 'Unlimited'
  const sign = x < 0 ? '−' : ''
  return `${sign}$${Math.abs(x).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

export function fmtPct(x: number, digits = 1): string {
  if (!Number.isFinite(x)) return '—'
  return `${(x * 100).toFixed(digits)}%`
}

export function fmtNum(x: number, digits = 2): string {
  if (!Number.isFinite(x)) return '—'
  return x.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** Round an axis-friendly step: 1/2/2.5/5 × 10^k covering `span/maxTicks`. */
export function niceStep(span: number, maxTicks: number): number {
  const raw = span / Math.max(maxTicks, 1)
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (raw <= m * mag) return m * mag
  }
  return 10 * mag
}

export function ticks(min: number, max: number, maxTicks = 6): number[] {
  if (!(max > min)) return [min]
  const step = niceStep(max - min, maxTicks)
  const out: number[] = []
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) {
    out.push(Math.abs(v) < step * 1e-9 ? 0 : v)
  }
  return out
}
