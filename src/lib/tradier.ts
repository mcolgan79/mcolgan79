import type { OptionType } from './types'

/**
 * Minimal Tradier market-data client (https://documentation.tradier.com).
 * Bring-your-own-key: the token lives in the user's localStorage and every
 * request goes straight from their device to Tradier — the app never
 * proxies or redistributes market data.
 */

export interface TradierConfig {
  token: string
  /** Sandbox tokens get 15-minute-delayed data */
  sandbox: boolean
}

export interface UnderlyingQuote {
  symbol: string
  description: string
  last: number
  asOf: number
}

export interface ChainOption {
  type: OptionType
  strike: number
  bid: number
  ask: number
  last: number | null
  /** Bid/ask midpoint, falling back to last */
  mid: number | null
  /** Implied vol as a decimal, when Tradier supplies greeks */
  iv: number | null
}

export interface Chain {
  expiration: string
  options: ChainOption[]
}

const baseUrl = (c: TradierConfig) =>
  c.sandbox ? 'https://sandbox.tradier.com/v1' : 'https://api.tradier.com/v1'

/** Tradier collapses single-element arrays to bare objects — normalize. */
export function toArray<T>(x: T | T[] | null | undefined): T[] {
  if (x === null || x === undefined) return []
  return Array.isArray(x) ? x : [x]
}

export function midPrice(bid: number, ask: number, last: number | null): number | null {
  if (bid > 0 && ask > 0 && ask >= bid) return (bid + ask) / 2
  return last && last > 0 ? last : null
}

/** Calendar days from `now` to an ISO expiration date (floor 1 so T > 0). */
export function dteFrom(expiration: string, now = new Date()): number {
  const exp = new Date(`${expiration}T21:00:00Z`) // ~4pm ET close
  const days = Math.round((exp.getTime() - now.getTime()) / 86_400_000)
  return Math.max(days, 1)
}

/* ---------- response parsing (pure, unit-tested) ---------- */

export function parseQuote(json: unknown): Omit<UnderlyingQuote, 'asOf'> {
  const q = toArray((json as { quotes?: { quote?: unknown } })?.quotes?.quote)[0] as
    | { symbol?: string; description?: string; last?: number; close?: number; prevclose?: number }
    | undefined
  const last = q?.last ?? q?.close ?? q?.prevclose
  if (!q?.symbol || typeof last !== 'number') {
    throw new Error('Symbol not found')
  }
  return { symbol: q.symbol, description: q.description ?? q.symbol, last }
}

export function parseExpirations(json: unknown): string[] {
  const dates = toArray(
    (json as { expirations?: { date?: unknown } })?.expirations?.date,
  ) as string[]
  return dates.filter((d) => typeof d === 'string')
}

interface RawOption {
  option_type?: string
  strike?: number
  bid?: number
  ask?: number
  last?: number | null
  greeks?: { mid_iv?: number; smv_vol?: number } | null
}

export function parseChain(json: unknown, expiration: string): Chain {
  const raw = toArray(
    (json as { options?: { option?: unknown } })?.options?.option,
  ) as RawOption[]
  const options: ChainOption[] = raw
    .filter((o) => (o.option_type === 'call' || o.option_type === 'put') && typeof o.strike === 'number')
    .map((o) => {
      const bid = o.bid ?? 0
      const ask = o.ask ?? 0
      const last = o.last ?? null
      const ivRaw =
        [o.greeks?.mid_iv, o.greeks?.smv_vol].find((v) => typeof v === 'number' && v > 0) ?? null
      return {
        type: o.option_type as OptionType,
        strike: o.strike as number,
        bid,
        ask,
        last,
        mid: midPrice(bid, ask, last),
        iv: ivRaw && ivRaw > 0 ? ivRaw : null,
      }
    })
    .sort((x, y) => x.strike - y.strike)
  return { expiration, options }
}

/* ---------- HTTP ---------- */

async function apiGet(cfg: TradierConfig, path: string, params: Record<string, string>): Promise<unknown> {
  const url = new URL(baseUrl(cfg) + path)
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v)
  let res: Response
  try {
    res = await fetch(url, {
      headers: { Authorization: `Bearer ${cfg.token}`, Accept: 'application/json' },
    })
  } catch {
    throw new Error(
      'Could not reach Tradier — check your connection (or corporate/CORS restrictions).',
    )
  }
  if (res.status === 401) {
    throw new Error('Tradier rejected the API key (401). Check the token and the sandbox/production setting.')
  }
  if (res.status === 429) {
    throw new Error('Tradier rate limit hit (429) — wait a moment and retry.')
  }
  if (!res.ok) throw new Error(`Tradier error ${res.status}`)
  return res.json()
}

export async function fetchQuote(cfg: TradierConfig, symbol: string): Promise<UnderlyingQuote> {
  const json = await apiGet(cfg, '/markets/quotes', { symbols: symbol.trim().toUpperCase() })
  return { ...parseQuote(json), asOf: Date.now() }
}

export async function fetchExpirations(cfg: TradierConfig, symbol: string): Promise<string[]> {
  const json = await apiGet(cfg, '/markets/options/expirations', {
    symbol: symbol.trim().toUpperCase(),
    includeAllRoots: 'true',
    strikes: 'false',
  })
  const dates = parseExpirations(json)
  if (dates.length === 0) throw new Error('No listed options found for that symbol.')
  return dates
}

export async function fetchChain(
  cfg: TradierConfig,
  symbol: string,
  expiration: string,
): Promise<Chain> {
  const json = await apiGet(cfg, '/markets/options/chains', {
    symbol: symbol.trim().toUpperCase(),
    expiration,
    greeks: 'true',
  })
  const chain = parseChain(json, expiration)
  if (chain.options.length === 0) throw new Error(`No options returned for ${expiration}.`)
  return chain
}
