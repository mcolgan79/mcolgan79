/**
 * POST /api/stripe-webhook
 * Receives Stripe events, verifies the signature, and records each customer's
 * ad-free entitlement in Cloudflare KV so `subscription-status` can answer from
 * a durable cache and react to cancellations / payment failures immediately.
 *
 * Setup:
 *   1. Create a KV namespace and bind it to the Pages project as `ENTITLEMENTS`.
 *   2. In Stripe → Developers → Webhooks, add an endpoint pointing at
 *      https://<your-site>/api/stripe-webhook and subscribe to:
 *        checkout.session.completed
 *        customer.subscription.updated
 *        customer.subscription.deleted
 *        invoice.payment_failed
 *   3. Copy the endpoint's signing secret to STRIPE_WEBHOOK_SECRET (secret).
 *
 * Without the KV binding or secret this is a safe no-op — subscription-status
 * still verifies live against Stripe.
 */
import { verifyStripeSignature } from '../../src/lib/stripe-signature'

interface KV {
  get(key: string): Promise<string | null>
  put(key: string, value: string): Promise<void>
}
interface Env {
  STRIPE_WEBHOOK_SECRET?: string
  ENTITLEMENTS?: KV
}

export async function onRequestPost(context: { request: Request; env: Env }): Promise<Response> {
  const { request, env } = context
  const raw = await request.text()
  const sig = request.headers.get('stripe-signature') ?? ''

  if (!env.STRIPE_WEBHOOK_SECRET) return new Response('webhook not configured', { status: 500 })
  if (!(await verifyStripeSignature(raw, sig, env.STRIPE_WEBHOOK_SECRET))) {
    return new Response('invalid signature', { status: 400 })
  }

  let event: { type?: string; data?: { object?: Record<string, unknown> } }
  try {
    event = JSON.parse(raw)
  } catch {
    return new Response('bad payload', { status: 400 })
  }

  const type = event.type ?? ''
  const obj = event.data?.object ?? {}
  const customerId = typeof obj.customer === 'string' ? obj.customer : undefined

  let pro: boolean | null = null
  if (type === 'customer.subscription.updated' || type === 'customer.subscription.deleted') {
    pro = obj.status === 'active' || obj.status === 'trialing'
  } else if (type === 'checkout.session.completed') {
    pro = true
  } else if (type === 'invoice.payment_failed') {
    pro = false
  }

  if (pro !== null && customerId && env.ENTITLEMENTS) {
    await env.ENTITLEMENTS.put(`pro:${customerId}`, pro ? '1' : '0')
  }
  return new Response('ok', { status: 200 })
}
