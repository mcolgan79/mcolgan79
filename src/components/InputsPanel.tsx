import { useEffect, useState } from 'react'
import type { OptionType, Side } from '../lib/types'

export interface FormState {
  S: number
  K: number
  dte: number
  ivPct: number
  premium: number
  type: OptionType
  side: Side
  contracts: number
  rPct: number
  qPct: number
  solve: 'premium' | 'iv'
}

interface NumFieldProps {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  derived?: string
}

/** Numeric input that tolerates in-progress typing ("1.", "") without snapping. */
function NumField({ label, value, onChange, min, max, step, disabled, derived }: NumFieldProps) {
  const [text, setText] = useState(String(value))
  const [focused, setFocused] = useState(false)
  useEffect(() => {
    if (!focused) setText(String(value))
  }, [value, focused])
  return (
    <div className="field">
      <label>
        {label}
        <input
          type="number"
          inputMode="decimal"
          value={text}
          min={min}
          max={max}
          step={step ?? 'any'}
          disabled={disabled}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false)
            setText(String(value))
          }}
          onChange={(e) => {
            setText(e.target.value)
            const v = parseFloat(e.target.value)
            if (Number.isFinite(v) && (min === undefined || v >= min) && (max === undefined || v <= max)) {
              onChange(v)
            }
          }}
        />
      </label>
      {derived ? <div className="derived">{derived}</div> : null}
    </div>
  )
}

interface Props {
  form: FormState
  onChange: (patch: Partial<FormState>) => void
  /** Model fair value when solving for premium */
  fairValue: number
  /** Solved IV (%) when solving for IV; NaN when unsolvable */
  solvedIvPct: number
}

export function InputsPanel({ form, onChange, fairValue, solvedIvPct }: Props) {
  const solvingIv = form.solve === 'iv'
  // Disabled fields display the derived value, not the last typed one
  const shownPremium = solvingIv ? form.premium : Math.round(fairValue * 100) / 100
  const shownIvPct =
    solvingIv && Number.isFinite(solvedIvPct)
      ? Math.round(solvedIvPct * 10) / 10
      : form.ivPct
  return (
    <div className="card inputs-card">
      <h2>Position</h2>
      <div className="inputs">
        <div className="seg" role="group" aria-label="Option type">
          <button aria-pressed={form.type === 'call'} onClick={() => onChange({ type: 'call' })}>
            Call
          </button>
          <button aria-pressed={form.type === 'put'} onClick={() => onChange({ type: 'put' })}>
            Put
          </button>
        </div>
        <div className="seg" role="group" aria-label="Direction">
          <button aria-pressed={form.side === 'long'} onClick={() => onChange({ side: 'long' })}>
            Long (buy)
          </button>
          <button aria-pressed={form.side === 'short'} onClick={() => onChange({ side: 'short' })}>
            Short (sell)
          </button>
        </div>

        <div className="grid-2">
          <NumField label="Underlying price" value={form.S} min={0.01} onChange={(S) => onChange({ S })} />
          <NumField label="Strike" value={form.K} min={0.01} onChange={(K) => onChange({ K })} />
          <NumField label="Days to expiration" value={form.dte} min={1} max={1500} step={1} onChange={(dte) => onChange({ dte })} />
          <NumField label="Contracts" value={form.contracts} min={1} step={1} onChange={(contracts) => onChange({ contracts })} />
        </div>

        <div className="solve-row" role="radiogroup" aria-label="Pricing input mode">
          Solve for:
          <label>
            <input
              type="radio"
              name="solve"
              checked={!solvingIv}
              onChange={() => onChange({ solve: 'premium' })}
            />
            premium from IV
          </label>
          <label>
            <input
              type="radio"
              name="solve"
              checked={solvingIv}
              onChange={() => onChange({ solve: 'iv' })}
            />
            IV from premium
          </label>
        </div>

        <div className="grid-2">
          <NumField
            label="Implied volatility %"
            value={shownIvPct}
            min={1}
            max={400}
            disabled={solvingIv}
            onChange={(ivPct) => onChange({ ivPct })}
            derived={solvingIv ? 'implied from premium' : undefined}
          />
          <NumField
            label="Premium / share $"
            value={shownPremium}
            min={0.01}
            disabled={!solvingIv}
            onChange={(premium) => onChange({ premium })}
            derived={!solvingIv ? `Black–Scholes fair value` : undefined}
          />
        </div>
        {solvingIv && !Number.isFinite(solvedIvPct) ? (
          <div className="input-error">
            That premium is outside no-arbitrage bounds for these inputs — IV can’t be
            solved. Using the last valid IV.
          </div>
        ) : null}

        <details className="advanced">
          <summary>Rates &amp; dividends</summary>
          <div className="grid-2">
            <NumField label="Risk-free rate %" value={form.rPct} min={0} max={25} onChange={(rPct) => onChange({ rPct })} />
            <NumField label="Dividend yield %" value={form.qPct} min={0} max={25} onChange={(qPct) => onChange({ qPct })} />
          </div>
        </details>
      </div>
    </div>
  )
}
