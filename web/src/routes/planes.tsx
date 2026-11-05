import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { meta, Section, PageTitle } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { billingCatalogue, createSubscriptionCheckout } from "@/lib/billing.functions";
import { formatMoney } from "@/lib/billing-schema";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/planes")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "settings" } });
  },
  head: () =>
    meta("Planes Peluqo", "Suscripciones mensuales o anuales a Peluqo Plus, Family y Lab."),
  loader: () => billingCatalogue(),
  component: Plans,
});

const tones = ["bg-sunburst", "bg-lavender", "bg-mint"];

function Plans() {
  const d = Route.useLoaderData();
  const checkout = useServerFn(createSubscriptionCheckout);
  const [interval, setInterval] = useState<"month" | "year">("month");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const buy = async (priceId: string) => {
    setErr("");
    const { data } = await supabase.auth.getUser();
    if (!data.user) {
      window.location.href = "/auth";
      return;
    }
    setBusy(priceId);
    try {
      const r = await checkout({ data: { priceId } });
      window.location.href = r.url;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Error");
      setBusy(null);
    }
  };
  return (
    <>
      <Section tone="sky">
        <PageTitle
          kicker="Peluqo"
          title="Planes"
          sub="Las suscripciones necesitan una cuenta. El pago se hace en Stripe; Peluqo no guarda datos bancarios."
        />
      </Section>
      <Section>
        <div className="flex gap-2">
          <Button
            aria-pressed={interval === "month"}
            variant={interval === "month" ? "default" : "outline"}
            onClick={() => setInterval("month")}
          >
            Mensual
          </Button>
          <Button
            aria-pressed={interval === "year"}
            variant={interval === "year" ? "default" : "outline"}
            onClick={() => setInterval("year")}
          >
            Anual
          </Button>
        </div>
        {err && (
          <p role="alert" className="platform-message mt-4">
            {err}
          </p>
        )}
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {d.plans.map((p, i) => {
            const price = d.prices.find(
              (x) => x.plan_id === p.id && x.billing_interval === interval,
            );
            const ok = p.is_active && price?.is_active && price.unit_amount;
            return (
              <div key={p.id} className={`card ${tones[i % 3]}`}>
                <h2 className="text-3xl font-bold">{p.name}</h2>
                <p className="mt-3">{p.description}</p>
                <p className="mt-4 text-2xl font-bold">
                  {ok
                    ? `${formatMoney(price!.unit_amount, price!.currency)} / ${interval === "month" ? "mes" : "año"}`
                    : "Próximamente"}
                </p>
                <Button
                  className="mt-4"
                  disabled={!ok || busy !== null}
                  onClick={() => price && buy(price.id)}
                >
                  {busy === price?.id ? "Abriendo pago…" : "Suscribirme"}
                </Button>
              </div>
            );
          })}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link className="btn" to="/suscripcion">
            Gestionar mi suscripción
          </Link>
          <Link className="btn" to="/tienda">
            Tienda Buddy y kits
          </Link>
        </div>
      </Section>
    </>
  );
}
