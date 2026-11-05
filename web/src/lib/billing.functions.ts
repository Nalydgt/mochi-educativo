import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { z } from "zod";
import type { Database } from "@/integrations/supabase/types";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { guestOrderSchema, adminBillingSchema } from "./billing-schema";

function publicClient() {
  const key = process.env["SUPABASE_PUBLISHABLE_KEY"]!;
  return createClient<Database>(process.env["SUPABASE_URL"]!, key, {
    auth: { persistSession: false, autoRefreshToken: false, storage: undefined },
    global: {
      fetch: (input, init) => {
        const h = new Headers(init?.headers);
        if (key.startsWith("sb_") && h.get("Authorization") === `Bearer ${key}`)
          h.delete("Authorization");
        h.set("apikey", key);
        return fetch(input, { ...init, headers: h });
      },
    },
  });
}

export const billingCatalogue = createServerFn({ method: "GET" }).handler(async () => {
  const sb = publicClient();
  const [plans, prices, products] = await Promise.all([
    sb.from("billing_plans").select("id,code,name,description,is_active").order("created_at"),
    sb.from("billing_prices").select("id,plan_id,billing_interval,unit_amount,currency,is_active"),
    sb
      .from("shop_products")
      .select("id,slug,name,description,kind,unit_amount,currency,stock,is_active")
      .order("created_at"),
  ]);
  if (plans.error || prices.error || products.error) throw new Error("No se pudo cargar la tienda");
  return { plans: plans.data, prices: prices.data, products: products.data };
});

export const createProductCheckout = createServerFn({ method: "POST" })
  .inputValidator((i: unknown) => guestOrderSchema.parse(i))
  .handler(async ({ data }) => {
    const { supabaseAdmin: admin } = await import("@/integrations/supabase/client.server");
    const { getStripe, originOf } = await import("./stripe.server");
    const existing = await admin
      .from("shop_orders")
      .select("stripe_session_id,status")
      .eq("request_key", data.requestKey)
      .maybeSingle();
    if (existing.data?.stripe_session_id) {
      const s = await getStripe().checkout.sessions.retrieve(existing.data.stripe_session_id);
      if (s.status === "open" && s.url) return { url: s.url };
      throw new Error("Este pedido ya se procesó. Recarga la página para empezar uno nuevo.");
    }
    const ids = data.items.map((i) => i.productId);
    const { data: products } = await admin.from("shop_products").select("*").in("id", ids);
    const lines = data.items.map((i) => {
      const p = products?.find((x) => x.id === i.productId);
      if (!p || !p.is_active || !p.unit_amount) throw new Error("Producto no disponible");
      return { p, q: i.quantity };
    });
    const currency = lines[0]!.p.currency;
    if (lines.some((l) => l.p.currency !== currency))
      throw new Error("Divisas distintas en el pedido");
    // Optional signed-in owner
    let userId: string | null = null;
    const auth = getRequest().headers.get("authorization");
    if (auth?.startsWith("Bearer ")) {
      const u = await admin.auth.getUser(auth.slice(7));
      userId = u.data.user?.id ?? null;
    }
    const reserve = await admin.rpc("reserve_stock", {
      p_items: lines.map((l) => ({ product_id: l.p.id, quantity: l.q })),
    });
    if (reserve.error) throw new Error("Agotado: no quedan unidades suficientes");
    const total = lines.reduce((s, l) => s + l.p.unit_amount! * l.q, 0);
    const order = await admin
      .from("shop_orders")
      .insert({
        user_id: userId,
        customer_name: data.name,
        customer_email: data.email,
        total_amount: total,
        currency,
        request_key: data.requestKey,
      })
      .select()
      .single();
    if (order.error) throw new Error("No se pudo crear el pedido");
    await admin.from("shop_order_items").insert(
      lines.map((l) => ({
        order_id: order.data.id,
        product_id: l.p.id,
        product_name: l.p.name,
        quantity: l.q,
        unit_amount: l.p.unit_amount!,
      })),
    );
    try {
      const origin = originOf(getRequest());
      const s = await getStripe().checkout.sessions.create(
        {
          mode: "payment",
          customer_email: data.email,
          client_reference_id: order.data.id,
          line_items: lines.map((l) => ({
            quantity: l.q,
            price_data: {
              currency,
              unit_amount: l.p.unit_amount!,
              product_data: { name: l.p.name, metadata: { product_id: l.p.id } },
            },
          })),
          shipping_address_collection: { allowed_countries: ["ES", "PT", "FR", "IT", "DE"] },
          metadata: { kind: "shop_order", order_id: order.data.id },
          payment_intent_data: { metadata: { order_id: order.data.id } },
          expires_at: Math.floor(Date.now() / 1000) + 30 * 60,
          success_url: `${origin}/pago-completado?session_id={CHECKOUT_SESSION_ID}`,
          cancel_url: `${origin}/tienda`,
        },
        { idempotencyKey: `order-${data.requestKey}` },
      );
      await admin.from("shop_orders").update({ stripe_session_id: s.id }).eq("id", order.data.id);
      return { url: s.url! };
    } catch (e) {
      await admin.from("shop_orders").update({ status: "failed" }).eq("id", order.data.id);
      await admin.rpc("release_order_stock", { p_order: order.data.id });
      throw new Error("No se pudo abrir el pago. Inténtalo de nuevo.");
    }
  });

async function customerFor(
  admin: SupabaseClient<Database>,
  userId: string,
  email: string | undefined,
) {
  const { getStripe } = await import("./stripe.server");
  const c = await admin
    .from("billing_customers")
    .select("stripe_customer_id")
    .eq("user_id", userId)
    .maybeSingle();
  if (c.data) return c.data.stripe_customer_id as string;
  const cu = await getStripe().customers.create(
    { ...(email ? { email } : {}), metadata: { user_id: userId } },
    { idempotencyKey: `customer-${userId}` },
  );
  await admin.from("billing_customers").upsert({ user_id: userId, stripe_customer_id: cu.id });
  return cu.id;
}

const ACTIVE = ["active", "trialing", "past_due", "incomplete"];

export const createSubscriptionCheckout = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(z.object({ priceId: z.string().uuid() }))
  .handler(async ({ data, context }) => {
    const { supabaseAdmin: admin } = await import("@/integrations/supabase/client.server");
    const { getStripe, stripePriceFor, originOf } = await import("./stripe.server");
    const subs = await admin
      .from("billing_subscriptions")
      .select("status")
      .eq("user_id", context.userId)
      .in("status", ACTIVE);
    if (subs.data?.length) throw new Error("Ya tienes una suscripción. Cámbiala desde tu perfil.");
    const lock = await admin
      .from("billing_checkout_locks")
      .select("*")
      .eq("user_id", context.userId)
      .maybeSingle();
    const stripe = getStripe();
    if (lock.data && new Date(lock.data.expires_at) > new Date()) {
      const s = await stripe.checkout.sessions.retrieve(lock.data.stripe_session_id);
      if (s.status === "open" && s.url) return { url: s.url };
    }
    const price = await stripePriceFor(admin, data.priceId);
    const customer = await customerFor(
      admin,
      context.userId,
      context.claims.email as string | undefined,
    );
    const origin = originOf(getRequest());
    const expires = Math.floor(Date.now() / 1000) + 30 * 60;
    const s = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer,
      client_reference_id: context.userId,
      line_items: [{ price: price.stripePrice, quantity: 1 }],
      metadata: { kind: "subscription", user_id: context.userId },
      subscription_data: {
        metadata: {
          user_id: context.userId,
          plan_code: price.plan,
          billing_interval: price.interval,
        },
      },
      expires_at: expires,
      success_url: `${origin}/pago-completado?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/planes`,
    });
    await admin.from("billing_checkout_locks").upsert({
      user_id: context.userId,
      stripe_session_id: s.id,
      expires_at: new Date(expires * 1000).toISOString(),
    });
    return { url: s.url! };
  });

export const myBilling = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const [subs, orders] = await Promise.all([
      context.supabase
        .from("billing_subscriptions")
        .select("*")
        .order("updated_at", { ascending: false }),
      context.supabase
        .from("shop_orders")
        .select(
          "id,status,total_amount,currency,created_at,shop_order_items(product_name,quantity)",
        )
        .order("created_at", { ascending: false }),
    ]);
    return { subscriptions: subs.data ?? [], orders: orders.data ?? [] };
  });

export const openBillingPortal = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { supabaseAdmin: admin } = await import("@/integrations/supabase/client.server");
    const { getStripe, originOf } = await import("./stripe.server");
    const c = await admin
      .from("billing_customers")
      .select("stripe_customer_id")
      .eq("user_id", context.userId)
      .maybeSingle();
    if (!c.data) throw new Error("Todavía no tienes suscripciones");
    const p = await getStripe().billingPortal.sessions.create({
      customer: c.data.stripe_customer_id,
      return_url: `${originOf(getRequest())}/suscripcion`,
    });
    return { url: p.url };
  });

export const changeSubscription = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(
    z.object({
      action: z.enum(["change", "cancel", "resume"]),
      priceId: z.string().uuid().optional(),
    }),
  )
  .handler(async ({ data, context }) => {
    const { supabaseAdmin: admin } = await import("@/integrations/supabase/client.server");
    const { getStripe, stripePriceFor } = await import("./stripe.server");
    const sub = await context.supabase
      .from("billing_subscriptions")
      .select("*")
      .in("status", ACTIVE)
      .limit(1)
      .maybeSingle();
    if (!sub.data) throw new Error("No tienes una suscripción activa");
    const stripe = getStripe();
    if (data.action === "cancel" || data.action === "resume") {
      await stripe.subscriptions.update(sub.data.stripe_subscription_id, {
        cancel_at_period_end: data.action === "cancel",
      });
      return { ok: true };
    }
    if (!data.priceId) throw new Error("Elige un plan");
    const price = await stripePriceFor(admin, data.priceId);
    const current = await stripe.subscriptions.retrieve(sub.data.stripe_subscription_id);
    await stripe.subscriptions.update(current.id, {
      items: [{ id: current.items.data[0]!.id, price: price.stripePrice }],
      proration_behavior: "create_prorations",
      cancel_at_period_end: false,
      metadata: {
        user_id: context.userId,
        plan_code: price.plan,
        billing_interval: price.interval,
      },
    });
    return { ok: true };
  });

export const saveBillingAdmin = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((i: unknown) => adminBillingSchema.parse(i))
  .handler(async ({ data, context }) => {
    const role = await context.supabase.rpc("has_role", {
      _user_id: context.userId,
      _role: "admin",
    });
    if (!role.data) throw new Error("No autorizado");
    const { supabaseAdmin: admin } = await import("@/integrations/supabase/client.server");
    const r =
      data.kind === "price"
        ? await admin
            .from("billing_prices")
            .update({ unit_amount: data.unit_amount, is_active: data.is_active })
            .eq("id", data.id)
        : data.kind === "plan"
          ? await admin
              .from("billing_plans")
              .update({ is_active: data.is_active })
              .eq("id", data.id)
          : await admin
              .from("shop_products")
              .update({
                unit_amount: data.unit_amount,
                stock: data.stock,
                is_active: data.is_active,
              })
              .eq("id", data.id);
    if (r.error) throw new Error(r.error.message);
    return { ok: true };
  });
