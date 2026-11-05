import Stripe from "stripe";

export function getStripe() {
  const key = process.env["STRIPE_SECRET_KEY"];
  if (!key) throw new Error("Stripe no está configurado");
  return new Stripe(key, {
    apiVersion: "2025-08-27.basil",
    httpClient: Stripe.createFetchHttpClient(),
  });
}

type Admin = (typeof import("@/integrations/supabase/client.server"))["supabaseAdmin"];

/** Returns a Stripe Price matching the database price, creating it automatically when missing or outdated. */
export async function stripePriceFor(admin: Admin, priceId: string) {
  const { data: p, error } = await admin
    .from("billing_prices")
    .select("*, billing_plans(code,name,is_active)")
    .eq("id", priceId)
    .single();
  if (error || !p || !p.is_active || !p.unit_amount || !p.billing_plans?.is_active)
    throw new Error("Este plan no está disponible");
  if (p.stripe_price_id && p.stripe_price_amount === p.unit_amount)
    return {
      stripePrice: p.stripe_price_id,
      plan: p.billing_plans.code,
      interval: p.billing_interval,
    };
  const price = await getStripe().prices.create({
    unit_amount: p.unit_amount,
    currency: p.currency,
    recurring: { interval: p.billing_interval as "month" | "year" },
    product_data: { name: p.billing_plans.name, metadata: { plan_code: p.billing_plans.code } },
    metadata: {
      plan_code: p.billing_plans.code,
      billing_interval: p.billing_interval,
      db_price_id: p.id,
    },
  });
  await admin
    .from("billing_prices")
    .update({ stripe_price_id: price.id, stripe_price_amount: p.unit_amount })
    .eq("id", p.id);
  return { stripePrice: price.id, plan: p.billing_plans.code, interval: p.billing_interval };
}

export function originOf(request: Request) {
  const u = new URL(request.url);
  return request.headers.get("origin") ?? `${u.protocol}//${u.host}`;
}
