/**
 * GET /api/subscription-status?session_id=…   (right after Checkout)
 * GET /api/subscription-status?customer=…      (on later app loads)
 *
 * Returns { pro: boolean, customerId?: string }. Reads the durable KV cache
 * kept fresh by the Stripe webhook when available; otherwise verifies live
 * against Stripe and warms the cache. Either way the client flag is never
 * trusted — entitlement is decided server-side.
 *
 * Required env: STRIPE_SECRET_KEY. Optional: ENTITLEMENTS (KV binding).
 *
 * NOTE: this identifies subscribers by the Stripe customer id stored on the
 * device. That's a solid MVP, but it does not sync entitlement across a user's
 * devices — cross-device requires user accounts (sign-in / magic link) so the
 * customer id can be tied to an identity. See README for the hardening path.
 */
interface KV {
  get(key: string): Promise<string | null>
  put(key: string, value: string): Promise<void>
}
interface Env {
  STRIPE_SECRET_KEY: string
  /** Optional KV cache populated by the Stripe webhook. */
  ENTITLEMENTS?: KV
}

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  })

async function stripeGet(path: string, key: string): Promise<Record<string, unknown> | null> {
  const res = await fetch(`https://api.stripe.com/v1/${path}`, {
    headers: { Authorization: `Bearer ${key}` },
  })
  if (!res.ok) return null
  return (await res.json()) as Record<string, unknown>
}

export async function onRequestGet(context: { request: Request; env: Env }): Promise<Response> {
  const { env, request } = context
  if (!env.STRIPE_SECRET_KEY) return json({ pro: false, error: 'stripe_not_configured' }, 500)

  const url = new URL(request.url)
  const sessionId = url.searchParams.get('session_id')
  let customerId = url.searchParams.get('customer') || undefined

  if (sessionId) {
    const session = await stripeGet(`checkout/sessions/${encodeURIComponent(sessionId)}`, env.STRIPE_SECRET_KEY)
    const cust = session?.customer
    if (typeof cust === 'string') customerId = cust
  }
  if (!customerId) return json({ pro: false })

  // Fast path: the webhook keeps this fresh in KV, so most loads never hit Stripe.
  if (env.ENTITLEMENTS) {
    const cached = await env.ENTITLEMENTS.get(`pro:${customerId}`)
    if (cached !== null) return json({ pro: cached === '1', customerId })
  }

  // Fallback: verify live against Stripe (also covers the first check before any
  // webhook has fired) and warm the cache for next time.
  const subs = await stripeGet(
    `subscriptions?customer=${encodeURIComponent(customerId)}&status=all&limit=10`,
    env.STRIPE_SECRET_KEY,
  )
  const data = (subs?.data as Array<{ status?: string }> | undefined) ?? []
  const pro = data.some((s) => s.status === 'active' || s.status === 'trialing')
  if (env.ENTITLEMENTS) await env.ENTITLEMENTS.put(`pro:${customerId}`, pro ? '1' : '0')
  return json({ pro, customerId })
}
