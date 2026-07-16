/**
 * POST /api/create-checkout-session
 * Creates a Stripe Checkout Session (subscription mode) and returns its URL.
 * Cloudflare Pages Function — runs server-side where the secret key is safe.
 *
 * Required environment variables (set in Cloudflare Pages → Settings → Env):
 *   STRIPE_SECRET_KEY   sk_live_… / sk_test_…
 *   STRIPE_PRICE_ID     price_…  (your OptPoP Pro recurring price)
 *   PUBLIC_BASE_URL     optional; the site origin for return URLs
 *
 * Uses Stripe's REST API directly (no SDK) so it runs on the Workers runtime
 * with zero dependencies.
 */
interface Env {
  STRIPE_SECRET_KEY: string
  STRIPE_PRICE_ID: string
  PUBLIC_BASE_URL?: string
}

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

export async function onRequestPost(context: { request: Request; env: Env }): Promise<Response> {
  const { env, request } = context
  if (!env.STRIPE_SECRET_KEY || !env.STRIPE_PRICE_ID) {
    return json({ error: 'stripe_not_configured' }, 500)
  }
  const origin = env.PUBLIC_BASE_URL || new URL(request.url).origin

  const body = new URLSearchParams()
  body.set('mode', 'subscription')
  body.append('line_items[0][price]', env.STRIPE_PRICE_ID)
  body.append('line_items[0][quantity]', '1')
  body.set('success_url', `${origin}/?checkout=success&session_id={CHECKOUT_SESSION_ID}`)
  body.set('cancel_url', `${origin}/?checkout=cancel`)
  body.set('allow_promotion_codes', 'true')
  body.set('billing_address_collection', 'auto')

  const res = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  })
  if (!res.ok) {
    return json({ error: 'stripe_error', detail: await res.text() }, 502)
  }
  const session = (await res.json()) as { url?: string }
  return json({ url: session.url })
}
