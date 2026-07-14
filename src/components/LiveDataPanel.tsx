import { useState } from 'react'
import { fmtNum } from '../lib/format'
import type { TradierConfig, UnderlyingQuote } from '../lib/tradier'

interface Props {
  config: TradierConfig
  onConfig: (patch: Partial<TradierConfig>) => void
  symbol: string
  onSymbol: (s: string) => void
  quote: UnderlyingQuote | null
  loading: boolean
  error: string | null
  onConnect: () => void
  onRefresh: () => void
}

export function LiveDataPanel({
  config,
  onConfig,
  symbol,
  onSymbol,
  quote,
  loading,
  error,
  onConnect,
  onRefresh,
}: Props) {
  const [open, setOpen] = useState(!quote)
  const connected = quote !== null
  return (
    <div className="card live-card">
      <div className="chart-head">
        <h2>Live data (Tradier)</h2>
        {connected ? (
          <button className="view-toggle" onClick={onRefresh} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        ) : null}
      </div>

      {connected ? (
        <p className="live-status">
          <strong>{quote.symbol}</strong> · ${fmtNum(quote.last)} ·{' '}
          {new Date(quote.asOf).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          {config.sandbox ? ' (15-min delayed)' : ''}
        </p>
      ) : null}

      <div className="inputs">
        <div className="live-row">
          <div className="field" style={{ flex: 1 }}>
            <label>
              Symbol
              <input
                type="text"
                value={symbol}
                placeholder="AAPL"
                autoCapitalize="characters"
                autoCorrect="off"
                spellCheck={false}
                onChange={(e) => onSymbol(e.target.value.toUpperCase())}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && config.token && symbol) onConnect()
                }}
              />
            </label>
          </div>
          <button
            className="connect-btn"
            onClick={onConnect}
            disabled={loading || !config.token || !symbol}
          >
            {loading && !connected ? 'Loading…' : connected ? 'Load' : 'Connect'}
          </button>
        </div>

        {error ? <div className="input-error">{error}</div> : null}

        <details className="advanced" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
          <summary>API key {config.token ? '· saved on this device' : '· required'}</summary>
          <div className="inputs" style={{ marginTop: 10 }}>
            <div className="field">
              <label>
                Tradier access token
                <input
                  type="password"
                  value={config.token}
                  autoComplete="off"
                  onChange={(e) => onConfig({ token: e.target.value.trim() })}
                />
              </label>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={config.sandbox}
                onChange={(e) => onConfig({ sandbox: e.target.checked })}
              />
              Sandbox environment (free developer token, 15-min delayed)
            </label>
            <p className="derived">
              Get a free token at developer.tradier.com. It is stored only in this
              browser/app on your device and sent only to Tradier.
            </p>
          </div>
        </details>
      </div>
    </div>
  )
}
