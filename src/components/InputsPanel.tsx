import { useEffect, useState } from 'react'
import { dteFrom, type Chain } from '../lib/tradier'
import type { Leg, OptionType, Side } from '../lib/types'

export interface LegForm {
  type: OptionType
  side: Side
  K: number
  dte: number
  ivPct: number
  /** null = use the Black–Scholes model price */
  premium: number | null
  qty: number
  /** ISO expiration date when the leg is linked to a live chain */
  expiration: string | null
}

export interface FormState {
  S: number
  rPct: number
  qPct: number
  contracts: number
  legs: LegForm[]
}

/** Live-chain data the leg pickers draw from (null = manual mode). */
export interface MarketView {
  expirations: string[]
  chains: Record<string, Chain>
  ensureChain: (expiration: string) => void
}

/** Round a strike to an increment that suits the underlying's price. */
function roundStrike(x: number): number {
  const step = x >= 500 ? 10 : x >= 250 ? 5 : x >= 25 ? 1 : 0.5
  return Math.round(x / step) * step
}

const baseLeg = (over: Partial<LegForm>): LegForm => ({
  type: 'put',
  side: 'short',
  K: 100,
  dte: 45,
  ivPct: 30,
  premium: null,
  qty: 1,
  expiration: null,
  ...over,
})

export const TEMPLATES: Record<string, (S: number) => LegForm[]> = {
  'Single option': (S) => [baseLeg({ K: roundStrike(S * 0.95) })],
  'Put credit spread': (S) => [
    baseLeg({ side: 'short', K: roundStrike(S * 0.95) }),
    baseLeg({ side: 'long', K: roundStrike(S * 0.9) }),
  ],
  'Call debit spread': (S) => [
    baseLeg({ type: 'call', side: 'long', K: roundStrike(S) }),
    baseLeg({ type: 'call', side: 'short', K: roundStrike(S * 1.05) }),
  ],
  'Iron condor': (S) => [
    baseLeg({ side: 'long', K: roundStrike(S * 0.9) }),
    baseLeg({ side: 'short', K: roundStrike(S * 0.95) }),
    baseLeg({ type: 'call', side: 'short', K: roundStrike(S * 1.05) }),
    baseLeg({ type: 'call', side: 'long', K: roundStrike(S * 1.1) }),
  ],
  Calendar: (S) => [
    baseLeg({ type: 'call', side: 'short', K: roundStrike(S), dte: 30 }),
    baseLeg({ type: 'call', side: 'long', K: roundStrike(S), dte: 60 }),
  ],
  Diagonal: (S) => [
    baseLeg({ type: 'call', side: 'long', K: roundStrike(S * 0.95), dte: 75 }),
    baseLeg({ type: 'call', side: 'short', K: roundStrike(S * 1.05), dte: 30 }),
  ],
}

interface NumFieldProps {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  disabled?: boolean
}

/** Numeric input that tolerates in-progress typing ("1.", "") without snapping. */
function NumField({ label, value, onChange, min, max, step, disabled }: NumFieldProps) {
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
    </div>
  )
}

interface Props {
  form: FormState
  /** Legs with premiums resolved (model price where the form says auto) */
  resolvedLegs: Leg[]
  market: MarketView | null
  onGlobal: (patch: Partial<Omit<FormState, 'legs'>>) => void
  onLeg: (index: number, patch: Partial<LegForm>) => void
  onAddLeg: () => void
  onRemoveLeg: (index: number) => void
  onTemplate: (name: keyof typeof TEMPLATES) => void
}

export function InputsPanel({
  form,
  resolvedLegs,
  market,
  onGlobal,
  onLeg,
  onAddLeg,
  onRemoveLeg,
  onTemplate,
}: Props) {
  return (
    <div className="card inputs-card">
      <h2>Position</h2>
      <div className="inputs">
        <div className="field">
          <label>
            Strategy template
            <select
              className="template-select"
              value=""
              onChange={(e) => {
                if (e.target.value) onTemplate(e.target.value as keyof typeof TEMPLATES)
              }}
            >
              <option value="">Load a template…</option>
              {Object.keys(TEMPLATES).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid-2">
          <NumField label="Underlying price" value={form.S} min={0.01} onChange={(S) => onGlobal({ S })} />
          <NumField
            label="Contracts"
            value={form.contracts}
            min={1}
            step={1}
            onChange={(contracts) => onGlobal({ contracts })}
          />
        </div>

        {form.legs.map((legForm, i) => {
          const resolved = resolvedLegs[i]
          const auto = legForm.premium === null
          const chain = legForm.expiration ? market?.chains[legForm.expiration] : undefined
          const chainRows = chain?.options.filter((o) => o.type === legForm.type) ?? []
          const strikeInChain = chainRows.some((o) => o.strike === legForm.K)
          return (
            <div className="leg-card" key={i}>
              <div className="leg-head">
                <span className="leg-title">Leg {i + 1}</span>
                <div className="seg seg-sm" role="group" aria-label={`Leg ${i + 1} direction`}>
                  <button aria-pressed={legForm.side === 'long'} onClick={() => onLeg(i, { side: 'long' })}>
                    Long
                  </button>
                  <button aria-pressed={legForm.side === 'short'} onClick={() => onLeg(i, { side: 'short' })}>
                    Short
                  </button>
                </div>
                <div className="seg seg-sm" role="group" aria-label={`Leg ${i + 1} type`}>
                  <button aria-pressed={legForm.type === 'call'} onClick={() => onLeg(i, { type: 'call' })}>
                    Call
                  </button>
                  <button aria-pressed={legForm.type === 'put'} onClick={() => onLeg(i, { type: 'put' })}>
                    Put
                  </button>
                </div>
                {form.legs.length > 1 ? (
                  <button
                    className="leg-remove"
                    aria-label={`Remove leg ${i + 1}`}
                    onClick={() => onRemoveLeg(i)}
                  >
                    ✕
                  </button>
                ) : null}
              </div>

              {market ? (
                <div className="grid-2">
                  <div className="field">
                    <label>
                      Expiration
                      <select
                        className="template-select"
                        value={legForm.expiration ?? ''}
                        onChange={(e) => {
                          const exp = e.target.value || null
                          onLeg(i, {
                            expiration: exp,
                            ...(exp ? { dte: dteFrom(exp) } : {}),
                          })
                          if (exp) market.ensureChain(exp)
                        }}
                      >
                        <option value="">manual DTE</option>
                        {market.expirations.map((d) => (
                          <option key={d} value={d}>
                            {d} ({dteFrom(d)}d)
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="field">
                    <label>
                      Chain strike
                      <select
                        className="template-select"
                        value={strikeInChain ? String(legForm.K) : ''}
                        disabled={!legForm.expiration || !chain}
                        onChange={(e) => {
                          const row = chainRows.find((o) => String(o.strike) === e.target.value)
                          if (!row) return
                          onLeg(i, {
                            K: row.strike,
                            premium: row.mid,
                            ...(row.iv ? { ivPct: Math.round(row.iv * 1000) / 10 } : {}),
                          })
                        }}
                      >
                        <option value="">
                          {!legForm.expiration
                            ? 'pick expiration'
                            : !chain
                              ? 'loading chain…'
                              : 'pick strike'}
                        </option>
                        {chainRows.map((o) => (
                          <option key={o.strike} value={o.strike}>
                            {o.strike} · mid {o.mid?.toFixed(2) ?? '—'}
                            {o.iv ? ` · IV ${(o.iv * 100).toFixed(0)}%` : ''}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                </div>
              ) : null}

              <div className="grid-2">
                <NumField label="Strike" value={legForm.K} min={0.01} onChange={(K) => onLeg(i, { K })} />
                <NumField
                  label="DTE"
                  value={legForm.dte}
                  min={1}
                  max={1500}
                  step={1}
                  onChange={(dte) => onLeg(i, { dte, expiration: null })}
                />
              </div>
              <div className="grid-2">
                <NumField
                  label="IV %"
                  value={legForm.ivPct}
                  min={1}
                  max={400}
                  onChange={(ivPct) => onLeg(i, { ivPct })}
                />
                <NumField
                  label="Premium $"
                  value={auto ? Math.round((resolved?.premium ?? 0) * 100) / 100 : legForm.premium!}
                  min={0.01}
                  onChange={(premium) => onLeg(i, { premium })}
                />
              </div>
              <div className="leg-foot">
                {auto ? (
                  <span className="derived">premium = model price</span>
                ) : (
                  <button className="link-btn" onClick={() => onLeg(i, { premium: null })}>
                    ↺ use model price
                  </button>
                )}
                <NumField
                  label="Qty"
                  value={legForm.qty}
                  min={1}
                  max={99}
                  step={1}
                  onChange={(qty) => onLeg(i, { qty })}
                />
              </div>
            </div>
          )
        })}

        {form.legs.length < 6 ? (
          <button className="add-leg" onClick={onAddLeg}>
            + Add leg
          </button>
        ) : null}

        <details className="advanced">
          <summary>Rates &amp; dividends</summary>
          <div className="grid-2">
            <NumField label="Risk-free rate %" value={form.rPct} min={0} max={25} onChange={(rPct) => onGlobal({ rPct })} />
            <NumField label="Dividend yield %" value={form.qPct} min={0} max={25} onChange={(qPct) => onGlobal({ qPct })} />
          </div>
        </details>
        <p className="derived">
          Premiums default to the Black–Scholes price for each leg's IV — type a market
          price (or pick from a live chain) to override; “↺ use model price” reverts.
        </p>
      </div>
    </div>
  )
}
