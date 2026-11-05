import { createFileRoute } from "@tanstack/react-router";
import type Stripe from "stripe";

export const Route = createFileRoute("/api/public/stripe-webhook")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const secret = process.env["STRIPE_WEBHOOK_SECRET"];
        const sig = request.headers.get("stripe-signature");
        if (!secret || !sig) return new Response("Not configured", { status: 400 });
        const StripeLib = (await import("stripe")).default;
        const { getStripe } = await import("@/lib/stripe.server");
        const stripe = getStripe();
        const body = await request.text();
        let event: Stripe.Event;
        try {
          event = await stripe.webhooks.constructEventAsync(
            body,
            sig,
            secret,
            undefined,
            StripeLib.createSubtleCryptoProvider(),
          );
        } catch {
          return new Response("Invalid signature", { status: 400 });
        }
        const { supabaseAdmin: admin } = await import("@/integrations/supabase/client.server");
        const seen = await admin
          .from("stripe_events")
          .select("id")
          .eq("id", event.id)
          .maybeSingle();
        if (seen.data) return new Response("duplicate");

        const syncSub = async (subId: string) => {
          const s = await stripe.subscriptions.retrieve(subId);
          const userId = s.metadata["user_id"];
          if (!userId) return;
          const item = s.items.data[0];
          await admin.from("billing_subscriptions").upsert(
            {
              user_id: userId,
              stripe_subscription_id: s.id,
              stripe_customer_id: String(s.customer),
              plan_code: s.metadata["plan_code"] ?? "plus",
              billing_interval: item?.price.recurring?.interval ?? "month",
              status: s.status,
              cancel_at_period_end: s.cancel_at_period_end,
              current_period_end: item?.current_period_end
                ? new Date(item.current_period_end * 1000).toISOString()
                : null,
              updated_at: new Date().toISOString(),
            },
            { onConflict: "stripe_subscription_id" },
          );
          await admin.from("billing_checkout_locks").delete().eq("user_id", userId);
        };

        const paidOrder = async (s: Stripe.Checkout.Session) => {
          const orderId = s.metadata?.["order_id"];
          if (!orderId || s.payment_status !== "paid") return;
          await admin
            .from("shop_orders")
            .update({
              status: "paid",
              paid_at: new Date().toISOString(),
              stripe_payment_intent: typeof s.payment_intent === "string" ? s.payment_intent : null,
              shipping: (s.collected_information?.shipping_details ?? null) as never,
            })
            .eq("id", orderId)
            .eq("status", "pending");
        };

        try {
          switch (event.type) {
            case "checkout.session.completed":
            case "checkout.session.async_payment_succeeded": {
              const s = event.data.object;
              const mail = await import("@/lib/confirmation-email.server");
              if (s.mode === "subscription" && s.subscription) {
                await syncSub(String(s.subscription));
                await mail.sendSubscriptionEmail(
                  admin,
                  String(s.subscription),
                  s.customer_details?.email,
                  s.customer_details?.name,
                );
              }
              if (s.mode === "payment") {
                await paidOrder(s);
                if (s.metadata?.["order_id"])
                  await mail.sendOrderEmail(admin, s.metadata["order_id"]);
              }
              break;
            }
            case "checkout.session.expired":
            case "checkout.session.async_payment_failed": {
              const s = event.data.object;
              const orderId = s.metadata?.["order_id"];
              if (orderId) {
                await admin
                  .from("shop_orders")
                  .update({
                    status: event.type === "checkout.session.expired" ? "expired" : "failed",
                  })
                  .eq("id", orderId)
                  .eq("status", "pending");
                await admin.rpc("release_order_stock", { p_order: orderId });
              }
              if (s.mode === "subscription" && s.client_reference_id)
                await admin.from("billing_checkout_locks").delete().eq("stripe_session_id", s.id);
              break;
            }
            case "customer.subscription.created":
            case "customer.subscription.updated":
            case "customer.subscription.deleted":
              await syncSub(event.data.object.id);
              break;
          }
          await admin.from("stripe_events").insert({ id: event.id, type: event.type });
        } catch (e) {
          console.error("stripe webhook", e);
          return new Response("Retry", { status: 500 });
        }
        return new Response("ok");
      },
    },
  },
});
