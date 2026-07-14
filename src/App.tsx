import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { DistributionChart } from './components/DistributionChart'
import { GreeksTable } from './components/GreeksTable'
import {
  InputsPanel,
  TEMPLATES,
  type FormState,
  type LegForm,
} from './components/InputsPanel'
import { PayoffChart } from './components/PayoffChart'
import { Recommendations } from './components/Recommendations'
import { StatTiles } from './components/StatTiles'
import { analyze } from './lib/analyze'
import { bsPrice } from './lib/black-scholes'
import { recommend } from './lib/recommend'
import type { Leg, Strategy } from './lib/types'

const STORAGE_KEY = 'optpop-form-v2'

const DEFAULT_FORM: FormState = {
  S: 100,
  rPct: 4.5,
  qPct: 0,
  contracts: 1,
  legs: TEMPLATES['Put credit spread'](100),
}

/** Migrate a saved v1 (single-leg) form into a one-leg v2 strategy. */
function migrateV1(): FormState | null {
  try {
    const raw = localStorage.getItem('optpop-form')
    if (!raw) return null
    const v1 = JSON.parse(raw)
    if (typeof v1?.S !== 'number' || typeof v1?.K !== 'number') return null
    const leg: LegForm = {
      type: v1.type === 'call' ? 'call' : 'put',
      side: v1.side === 'long' ? 'long' : 'short',
      K: v1.K,
      dte: v1.dte ?? 45,
      ivPct: v1.ivPct ?? 30,
      premium: v1.solve === 'iv' && typeof v1.premium === 'number' ? v1.premium : null,
      qty: 1,
    }
    return {
      S: v1.S,
      rPct: v1.rPct ?? 4.5,
      qPct: v1.qPct ?? 0,
      contracts: v1.contracts ?? 1,
      legs: [leg],
    }
  } catch {
    return null
  }
}

function loadForm(): FormState {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved) as FormState
      if (Array.isArray(parsed.legs) && parsed.legs.length > 0) {
        return { ...DEFAULT_FORM, ...parsed }
      }
    }
  } catch {
    /* fall through */
  }
  return migrateV1() ?? DEFAULT_FORM
}

function useTheme(): ['light' | 'dark' | 'auto', () => void] {
  const [theme, setTheme] = useState<'light' | 'dark' | 'auto'>(
    () => (localStorage.getItem('optpop-theme') as 'light' | 'dark') || 'auto',
  )
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'auto') {
      root.removeAttribute('data-theme')
      localStorage.removeItem('optpop-theme')
    } else {
      root.setAttribute('data-theme', theme)
      localStorage.setItem('optpop-theme', theme)
    }
  }, [theme])
  const cycle = () => setTheme((t) => (t === 'auto' ? 'dark' : t === 'dark' ? 'light' : 'auto'))
  return [theme, cycle]
}

export default function App() {
  const [form, setForm] = useState<FormState>(loadForm)
  const [theme, cycleTheme] = useTheme()

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(form))
  }, [form])

  const strategy: Strategy = useMemo(() => {
    const r = form.rPct / 100
    const q = form.qPct / 100
    const legs: Leg[] = form.legs.map((lf) => {
      const iv = lf.ivPct / 100
      const premium =
        lf.premium ??
        bsPrice(lf.type, {
          S: form.S,
          K: lf.K,
          T: Math.max(lf.dte, 0) / 365,
          sigma: iv,
          r,
          q,
        })
      return {
        type: lf.type,
        side: lf.side,
        K: lf.K,
        dte: lf.dte,
        iv,
        premium: Math.max(premium, 0.0001),
        qty: lf.qty,
      }
    })
    return { S: form.S, r, q, contracts: form.contracts, multiplier: 100, legs }
  }, [form])

  // The Monte Carlo P50 makes analysis the heavy part — defer it so typing
  // in the inputs stays responsive.
  const deferredStrategy = useDeferredValue(strategy)
  const analysis = useMemo(() => analyze(deferredStrategy), [deferredStrategy])
  const recs = useMemo(() => recommend(deferredStrategy, analysis), [deferredStrategy, analysis])

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          Opt<span className="pop">PoP</span>
        </h1>
        <span className="tagline">
          Option strategy risk, reward &amp; probabilities — POP · P50 · touch
        </span>
        <button className="theme-toggle" onClick={cycleTheme} aria-label="Cycle color theme">
          Theme: {theme}
        </button>
      </header>

      <div className="layout">
        <InputsPanel
          form={form}
          resolvedLegs={strategy.legs}
          onGlobal={(patch) => setForm((f) => ({ ...f, ...patch }))}
          onLeg={(i, patch) =>
            setForm((f) => ({
              ...f,
              legs: f.legs.map((l, j) => (j === i ? { ...l, ...patch } : l)),
            }))
          }
          onAddLeg={() =>
            setForm((f) => ({
              ...f,
              legs: [
                ...f.legs,
                { ...f.legs[f.legs.length - 1], side: 'long' as const, premium: null },
              ],
            }))
          }
          onRemoveLeg={(i) =>
            setForm((f) => ({ ...f, legs: f.legs.filter((_, j) => j !== i) }))
          }
          onTemplate={(name) =>
            setForm((f) => ({ ...f, legs: TEMPLATES[name](f.S) }))
          }
        />
        <main className="content" style={{ opacity: deferredStrategy === strategy ? 1 : 0.6 }}>
          <StatTiles st={deferredStrategy} a={analysis} />
          <PayoffChart st={deferredStrategy} a={analysis} />
          <DistributionChart st={deferredStrategy} a={analysis} />
          <GreeksTable st={deferredStrategy} a={analysis} />
          <Recommendations recs={recs} />
          <p className="disclaimer">
            All probabilities assume lognormal (Black–Scholes) dynamics at the position's
            vega-weighted IV with risk-neutral drift; longer-dated legs are marked to model
            at the front expiration assuming their IVs hold; P50 uses a seeded Monte Carlo
            with daily marks. Models simplify reality — this tool is for education, not
            investment advice.
          </p>
        </main>
      </div>
    </div>
  )
}
