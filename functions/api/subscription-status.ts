/**
 * GET /api/subscription-status?session_id=…   (right after Checkout)
 * GET /api/subscription-status?customer=…      (on later app loads)
 *
 * Returns { pro: boolean, customerId?: string } by asking Stripe whether the
 * customer has an active or trialing subscription. Verifying against Stripe on
 * every check keeps entitlement honest (the client flag is never trusted).
 *
 * Required env: STRIPE_SECRET_KEY
 *
 * NOTE: this identifies subscribers by the Stripe customer id stored on the
 * device. That's a solid MVP, but it does not sync entitlement across a user's
 * devices — cross-device requires user accounts (sign-in / magic link) so the
 * customer id can be tied to an identity. See README for the hardening path.
 */
interface Env {
  STRIPE_SECRET_KEY: string
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

  const subs = await stripeGet(
    `subscriptions?customer=${encodeURIComponent(customerId)}&status=all&limit=10`,
    env.STRIPE_SECRET_KEY,
  )
  const data = (subs?.data as Array<{ status?: string }> | undefined) ?? []
  const pro = data.some((s) => s.status === 'active' || s.status === 'trialing')
  return json({ pro, customerId })
}
