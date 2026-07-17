/**
 * POST /api/create-portal-session  { customer: "cus_…" }
 * Returns { url } for the Stripe Billing Customer Portal so a subscriber can
 * update payment method, view invoices, or cancel.
 *
 * Required env: STRIPE_SECRET_KEY. Also enable the portal once in Stripe →
 * Settings → Billing → Customer portal.
 *
 * SECURITY: this trusts the customer id sent by the client, matching the app's
 * current no-account MVP (see subscription-status). Before a real public launch
 * with money involved, gate this behind user auth so one user can't open
 * another's billing portal — the portal can cancel a subscription.
 */
interface Env {
  STRIPE_SECRET_KEY?: string
  PUBLIC_BASE_URL?: string
}

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  })

export async function onRequestPost(context: { request: Request; env: Env }): Promise<Response> {
  const { request, env } = context
  if (!env.STRIPE_SECRET_KEY) return json({ error: 'stripe_not_configured' }, 500)

  let customer = ''
  try {
    customer = ((await request.json()) as { customer?: string }).customer ?? ''
  } catch {
    /* no body */
  }
  if (!customer.startsWith('cus_')) return json({ error: 'missing_customer' }, 400)

  const origin = env.PUBLIC_BASE_URL || new URL(request.url).origin
  const body = new URLSearchParams()
  body.set('customer', customer)
  body.set('return_url', origin)

  const res = await fetch('https://api.stripe.com/v1/billing_portal/sessions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  })
  if (!res.ok) return json({ error: 'stripe_error', detail: await res.text() }, 502)
  const session = (await res.json()) as { url?: string }
  return json({ url: session.url })
}
