import { useEffect, useMemo, useRef, useState } from 'react'
import { DistributionChart } from './components/DistributionChart'
import { GreeksTable } from './components/GreeksTable'
import { InputsPanel, type FormState } from './components/InputsPanel'
import { PayoffChart } from './components/PayoffChart'
import { Recommendations } from './components/Recommendations'
import { StatTiles } from './components/StatTiles'
import { analyze } from './lib/analyze'
import { bsPrice, impliedVol } from './lib/black-scholes'
import { recommend } from './lib/recommend'
import type { TradeInputs } from './lib/types'

const DEFAULT_FORM: FormState = {
  S: 100,
  K: 95,
  dte: 45,
  ivPct: 30,
  premium: 1.5,
  type: 'put',
  side: 'short',
  contracts: 1,
  rPct: 4.5,
  qPct: 0,
  solve: 'premium',
}

function useTheme(): ['light' | 'dark' | 'auto', () => void] {
  const [theme, setTheme] = useState<'light' | 'dark' | 'auto'>(
    () => (localStorage.getItem('optpop-theme') as 'light' | 'dark') || 'auto',
  )
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'auto') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    if (theme === 'auto') localStorage.removeItem('optpop-theme')
    else localStorage.setItem('optpop-theme', theme)
  }, [theme])
  const cycle = () => setTheme((t) => (t === 'auto' ? 'dark' : t === 'dark' ? 'light' : 'auto'))
  return [theme, cycle]
}

export default function App() {
  const [form, setForm] = useState<FormState>(() => {
    try {
      const saved = localStorage.getItem('optpop-form')
      return saved ? { ...DEFAULT_FORM, ...JSON.parse(saved) } : DEFAULT_FORM
    } catch {
      return DEFAULT_FORM
    }
  })
  const [theme, cycleTheme] = useTheme()
  const lastValidIv = useRef(form.ivPct / 100)

  useEffect(() => {
    localStorage.setItem('optpop-form', JSON.stringify(form))
  }, [form])

  const { trade, fairValue, solvedIvPct } = useMemo(() => {
    const T = Math.max(form.dte, 0) / 365
    const r = form.rPct / 100
    const q = form.qPct / 100
    const bsParams = { S: form.S, K: form.K, T, r, q }

    let iv = form.ivPct / 100
    let premium = form.premium
    let solvedPct = NaN
    if (form.solve === 'premium') {
      premium = bsPrice(form.type, { ...bsParams, sigma: iv })
      lastValidIv.current = iv
    } else {
      const solved = impliedVol(form.type, form.premium, bsParams)
      if (Number.isFinite(solved)) {
        iv = solved
        solvedPct = solved * 100
        lastValidIv.current = solved
      } else {
        iv = lastValidIv.current
      }
    }
    premium = Math.max(premium, 0.0001)

    const trade: TradeInputs = {
      S: form.S,
      K: form.K,
      dte: form.dte,
      iv,
      premium,
      type: form.type,
      side: form.side,
      r,
      q,
      contracts: form.contracts,
      multiplier: 100,
    }
    return { trade, fairValue: bsPrice(form.type, { ...bsParams, sigma: iv }), solvedIvPct: solvedPct }
  }, [form])

  const analysis = useMemo(() => analyze(trade), [trade])
  const recs = useMemo(() => recommend(trade, analysis), [trade, analysis])

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          Opt<span className="pop">PoP</span>
        </h1>
        <span className="tagline">
          Single-leg option risk, reward &amp; probabilities — POP · P50 · touch
        </span>
        <button className="theme-toggle" onClick={cycleTheme} aria-label="Cycle color theme">
          Theme: {theme}
        </button>
      </header>

      <div className="layout">
        <InputsPanel
          form={form}
          onChange={(patch) => {
            // Switching solve modes adopts the currently derived value so the
            // newly editable field starts where the model left it.
            if (patch.solve === 'iv' && form.solve === 'premium') {
              patch.premium = Math.round(trade.premium * 100) / 100
            } else if (patch.solve === 'premium' && form.solve === 'iv') {
              patch.ivPct = Math.round(trade.iv * 1000) / 10
            }
            setForm((f) => ({ ...f, ...patch }))
          }}
          fairValue={fairValue}
          solvedIvPct={solvedIvPct}
        />
        <main className="content">
          <StatTiles t={trade} a={analysis} />
          <PayoffChart t={trade} a={analysis} />
          <DistributionChart t={trade} a={analysis} />
          <GreeksTable t={trade} a={analysis} />
          <Recommendations recs={recs} />
          <p className="disclaimer">
            All probabilities assume lognormal (Black–Scholes) dynamics at the entered IV
            with risk-neutral drift; P50 uses a 4,000-path Monte Carlo with daily marks. Models simplify reality — this tool is for education,
            not investment advice.
          </p>
        </main>
      </div>
    </div>
  )
}
