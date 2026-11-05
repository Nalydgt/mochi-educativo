// Sends purchase confirmations only from the verified Stripe webhook.
// Each row is claimed atomically (sent_at IS NULL -> now()) so retries or page reloads never resend.
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/integrations/supabase/types";
const GATEWAY = "https://connector-gateway.lovable.dev/resend";
const esc = (s: string) =>
  s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
const money = (cents: number, cur: string) =>
  new Intl.NumberFormat("es-ES", { style: "currency", currency: cur.toUpperCase() }).format(
    cents / 100,
  );
export const newCode = (prefix: string) =>
  `${prefix}-${crypto.randomUUID().replace(/-/g, "").slice(0, 10).toUpperCase()}`;

async function send(to: string, subject: string, html: string) {
  const lk = process.env["LOVABLE_API_KEY"];
  const rk = process.env["RESEND_API_KEY"];
  if (!lk || !rk) throw new Error("Resend no configurado");
  const r = await fetch(`${GATEWAY}/emails`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${lk}`,
      "X-Connection-Api-Key": rk,
    },
    body: JSON.stringify({
      from: process.env["RESEND_FROM"] ?? "Peluqo <onboarding@resend.dev>",
      to: [to],
      subject,
      html,
    }),
  });
  if (!r.ok) throw new Error(`Resend [${r.status}]: ${await r.text()}`);
}

const layout = (title: string, rows: [string, string][]) =>
  `<div style="font-family:Arial,sans-serif;color:#111;max-width:560px"><h1>${esc(title)}</h1><table style="border-collapse:collapse">${rows.map(([k, v]) => `<tr><td style="padding:6px 16px 6px 0"><b>${esc(k)}</b></td><td>${esc(v)}</td></tr>`).join("")}</table><p>Gracias por confiar en Peluqo.</p></div>`;

export async function sendOrderEmail(admin: SupabaseClient<Database>, orderId: string) {
  const claim = await admin
    .from("shop_orders")
    .update({
      confirmation_email_sent_at: new Date().toISOString(),
      confirmation_code: newCode("PLQ-PED"),
    })
    .eq("id", orderId)
    .eq("status", "paid")
    .is("confirmation_email_sent_at", null)
    .select("id,customer_name,customer_email,total_amount,currency,paid_at,confirmation_code")
    .maybeSingle();
  if (!claim.data) return;
  const o = claim.data;
  const items = await admin
    .from("shop_order_items")
    .select("product_name,quantity")
    .eq("order_id", orderId);
  try {
    await send(
      o.customer_email,
      `Tu pedido Peluqo ${o.confirmation_code}`,
      layout("Pedido confirmado", [
        ["Nombre", o.customer_name],
        ["Código", o.confirmation_code!],
        [
          "Fecha",
          new Date(o.paid_at ?? Date.now()).toLocaleString("es-ES", { timeZone: "Europe/Madrid" }),
        ],
        [
          "Productos",
          (items.data ?? []).map((i) => `${i.quantity} × ${i.product_name}`).join(", "),
        ],
        ["Total", money(o.total_amount, o.currency)],
      ]),
    );
  } catch (e) {
    await admin.from("shop_orders").update({ confirmation_email_sent_at: null }).eq("id", orderId);
    throw e;
  }
}

export async function sendSubscriptionEmail(
  admin: SupabaseClient<Database>,
  subId: string,
  email: string | null | undefined,
  name: string | null | undefined,
) {
  if (!email) return;
  const claim = await admin
    .from("billing_subscriptions")
    .update({
      confirmation_email_sent_at: new Date().toISOString(),
      confirmation_code: newCode("PLQ-SUB"),
    })
    .eq("stripe_subscription_id", subId)
    .is("confirmation_email_sent_at", null)
    .in("status", ["active", "trialing"])
    .select("plan_code,billing_interval,confirmation_code")
    .maybeSingle();
  if (!claim.data) return;
  const s = claim.data;
  const plan = await admin
    .from("billing_plans")
    .select("name")
    .eq("code", s.plan_code)
    .maybeSingle();
  try {
    await send(
      email,
      `Tu suscripción ${plan.data?.name ?? "Peluqo"} está activa`,
      layout("Suscripción activada", [
        ["Nombre", name ?? email],
        ["Plan", plan.data?.name ?? s.plan_code],
        ["Periodo", s.billing_interval === "year" ? "Anual" : "Mensual"],
        ["Código", s.confirmation_code!],
        ["Fecha", new Date().toLocaleString("es-ES", { timeZone: "Europe/Madrid" })],
      ]),
    );
  } catch (e) {
    await admin
      .from("billing_subscriptions")
      .update({ confirmation_email_sent_at: null })
      .eq("stripe_subscription_id", subId);
    throw e;
  }
}
