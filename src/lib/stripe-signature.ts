/**
 * Verify a Stripe webhook signature without the Stripe SDK, using Web Crypto
 * (available identically in the Cloudflare Workers runtime and in Node ≥18).
 * Pure and side-effect free so it can be unit-tested off-platform.
 *
 * Stripe signs `${timestamp}.${rawBody}` with HMAC-SHA256 keyed by the
 * endpoint's signing secret (whsec_…) and sends it as the `Stripe-Signature`
 * header: `t=<unix>,v1=<hex>` (possibly several v1 during key rotation).
 */

async function hmacSha256Hex(secret: string, data: string): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(data))
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** Constant-time comparison of two equal-purpose hex strings. */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

export function parseSignatureHeader(header: string): { t?: string; v1: string[] } {
  const out: { t?: string; v1: string[] } = { v1: [] }
  for (const part of header.split(',')) {
    const i = part.indexOf('=')
    if (i < 0) continue
    const key = part.slice(0, i).trim()
    const val = part.slice(i + 1).trim()
    if (key === 't') out.t = val
    else if (key === 'v1') out.v1.push(val)
  }
  return out
}

/**
 * @returns true only if a v1 signature matches AND the timestamp is within
 * `toleranceSec` of `nowMs` (replay protection).
 */
export async function verifyStripeSignature(
  rawBody: string,
  sigHeader: string,
  secret: string,
  toleranceSec = 300,
  nowMs: number = Date.now(),
): Promise<boolean> {
  if (!secret || !sigHeader) return false
  const { t, v1 } = parseSignatureHeader(sigHeader)
  if (!t || v1.length === 0) return false
  const ts = Number(t)
  if (!Number.isFinite(ts)) return false
  if (Math.abs(nowMs / 1000 - ts) > toleranceSec) return false
  const expected = await hmacSha256Hex(secret, `${t}.${rawBody}`)
  return v1.some((candidate) => timingSafeEqual(expected, candidate))
}

/** Build a valid header for a payload — used by tests (and handy locally). */
export async function signPayload(
  rawBody: string,
  secret: string,
  timestampSec: number,
): Promise<string> {
  const v1 = await hmacSha256Hex(secret, `${timestampSec}.${rawBody}`)
  return `t=${timestampSec},v1=${v1}`
}
