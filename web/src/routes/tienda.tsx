import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { Field, meta, Section, PageTitle } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { billingCatalogue, createProductCheckout } from "@/lib/billing.functions";
import { formatMoney, isSoldOut } from "@/lib/billing-schema";

export const Route = createFileRoute("/tienda")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "devices" } });
  },
  head: () => meta("Tienda Peluqo", "Compra Peluqo Buddy y kits DIY, también como invitado."),
  loader: () => billingCatalogue(),
  component: Shop,
});

function Shop() {
  const d = Route.useLoaderData();
  const checkout = useServerFn(createProductCheckout);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [requestKey] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const items = Object.entries(qty)
    .filter(([, q]) => q > 0)
    .map(([productId, quantity]) => ({ productId, quantity }));
  const pay = async () => {
    setErr("");
    setBusy(true);
    try {
      const r = await checkout({ data: { requestKey, name, email, items } });
      window.location.href = r.url;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Error");
      setBusy(false);
    }
  };
  return (
    <>
      <Section tone="lavender">
        <PageTitle
          kicker="Peluqo"
          title="Tienda"
          sub="Buddy y kits DIY. Puedes comprar sin cuenta; la dirección de envío se pide en el pago de Stripe."
        />
      </Section>
      <Section>
        <div className="grid gap-4 md:grid-cols-3">
          {d.products.map((p) => {
            const sold = isSoldOut(p);
            const ok = p.is_active && p.unit_amount && !sold;
            return (
              <div key={p.id} className={`card ${p.kind === "buddy" ? "bg-sunburst" : "bg-mint"}`}>
                <h2 className="text-2xl font-bold">{p.name}</h2>
                <p className="mt-2">{p.description}</p>
                <p className="mt-3 text-xl font-bold">
                  {!p.is_active || !p.unit_amount
                    ? "Próximamente"
                    : sold
                      ? "Agotado"
                      : formatMoney(p.unit_amount, p.currency)}
                </p>
                {ok && (
                  <label className="mt-3 block">
                    Cantidad
                    <input
                      type="number"
                      min={0}
                      max={Math.min(10, p.stock)}
                      value={qty[p.id] ?? 0}
                      onChange={(e) =>
                        setQty({
                          ...qty,
                          [p.id]: Math.max(
                            0,
                            Math.min(Math.min(10, p.stock), Number(e.target.value)),
                          ),
                        })
                      }
                      className="platform-input ml-2 max-w-20"
                    />
                  </label>
                )}
              </div>
            );
          })}
        </div>
        {items.length > 0 && (
          <div className="card mt-8 max-w-xl bg-concrete">
            <h2 className="text-2xl font-bold">Tus datos</h2>
            <div className="mt-3 space-y-3">
              <Field
                label="Nombre"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <Field
                label="Correo"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            {err && (
              <p role="alert" className="platform-message mt-3">
                {err}
              </p>
            )}
            <Button
              className="mt-4"
              disabled={busy || name.length < 2 || !email.includes("@")}
              onClick={pay}
            >
              {busy ? "Abriendo pago…" : "Pagar con Stripe"}
            </Button>
          </div>
        )}
      </Section>
    </>
  );
}
