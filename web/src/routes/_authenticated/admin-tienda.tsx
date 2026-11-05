import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { meta, Section, PageTitle } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { billingCatalogue, saveBillingAdmin } from "@/lib/billing.functions";
import { accountData } from "@/lib/learning.functions";
import type { z } from "zod";
import type { adminBillingSchema } from "@/lib/billing-schema";

export const Route = createFileRoute("/_authenticated/admin-tienda")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "overview" } });
  },
  head: () =>
    meta(
      "Precios y stock · Peluqo",
      "Administra precios de planes, productos y unidades disponibles.",
    ),
  component: AdminShop,
});

const euros = (c: number | null) => (c == null ? "" : String(c / 100));
const cents = (v: string) =>
  v.trim() === "" ? null : Math.round(Number(v.replace(",", ".")) * 100);

function AdminShop() {
  const save = useServerFn(saveBillingAdmin);
  const qc = useQueryClient();
  const read = useServerFn(accountData);
  const account = useQuery({ queryKey: ["account"], queryFn: () => read() });
  const q = useQuery({
    queryKey: ["billing-cat"],
    queryFn: () => billingCatalogue(),
    enabled: account.data?.admin === true,
  });
  const [msg, setMsg] = useState("");
  const go = async (data: z.infer<typeof adminBillingSchema>) => {
    try {
      await save({ data });
      setMsg("Guardado");
      qc.invalidateQueries({ queryKey: ["billing-cat"] });
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Error");
    }
  };
  return (
    <>
      <Section tone="gray">
        <PageTitle
          kicker="Administración"
          title="Precios y stock"
          sub="Precios en euros. Stripe usa siempre estos valores."
        />
      </Section>
      <Section>
        {account.isPending ? (
          <p role="status">Comprobando el acceso…</p>
        ) : account.error || !account.data?.admin ? (
          <p className="platform-message" role="alert">
            {account.error?.message ?? "Acceso reservado a administradores."}
          </p>
        ) : q.isPending ? (
          <p role="status">Cargando precios y stock…</p>
        ) : q.error ? (
          <p className="platform-message" role="alert">
            {q.error.message}
          </p>
        ) : (
          <>
            {msg && (
              <p role="status" className="platform-message mb-4">
                {msg}
              </p>
            )}
            <h2 className="text-3xl font-bold">Planes</h2>
            {q.data?.plans.map((p) => (
              <div key={p.id} className="card mt-4 bg-background">
                <label className="flex items-center gap-2 font-bold">
                  <input
                    type="checkbox"
                    defaultChecked={p.is_active}
                    onChange={(e) => go({ kind: "plan", id: p.id, is_active: e.target.checked })}
                  />
                  {p.name} disponible
                </label>
                {q
                  .data!.prices.filter((x) => x.plan_id === p.id)
                  .map((x) => (
                    <form
                      key={x.id}
                      className="mt-3 flex flex-wrap items-center gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        go({
                          kind: "price",
                          id: x.id,
                          unit_amount: cents(String(f.get("a"))),
                          is_active: f.get("on") === "on",
                        });
                      }}
                    >
                      <span className="w-20">
                        {x.billing_interval === "year" ? "Anual" : "Mensual"}
                      </span>
                      <input
                        name="a"
                        inputMode="decimal"
                        aria-label="Precio en euros"
                        defaultValue={euros(x.unit_amount)}
                        placeholder="€"
                        className="platform-input max-w-28"
                      />
                      <label>
                        <input type="checkbox" name="on" defaultChecked={x.is_active} /> activo
                      </label>
                      <Button type="submit" variant="outline">
                        Guardar
                      </Button>
                    </form>
                  ))}
              </div>
            ))}
            <h2 className="mt-10 text-3xl font-bold">Productos</h2>
            {q.data?.products.map((p) => (
              <form
                key={p.id}
                className="card mt-4 flex flex-wrap items-center gap-2 bg-background"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  go({
                    kind: "product",
                    id: p.id,
                    unit_amount: cents(String(f.get("a"))),
                    stock: Math.max(0, Number(f.get("s")) | 0),
                    is_active: f.get("on") === "on",
                  });
                }}
              >
                <span className="w-48 font-bold">{p.name}</span>
                <input
                  name="a"
                  inputMode="decimal"
                  aria-label="Precio en euros"
                  defaultValue={euros(p.unit_amount)}
                  placeholder="€"
                  className="platform-input max-w-28"
                />
                <label>
                  Stock{" "}
                  <input
                    name="s"
                    type="number"
                    min={0}
                    defaultValue={p.stock}
                    className="platform-input max-w-24"
                  />
                </label>
                <label>
                  <input type="checkbox" name="on" defaultChecked={p.is_active} /> a la venta
                </label>
                <Button type="submit" variant="outline">
                  Guardar
                </Button>
              </form>
            ))}
          </>
        )}
      </Section>
    </>
  );
}
