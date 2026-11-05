import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { EmptyState, meta, Section, PageTitle } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import {
  billingCatalogue,
  changeSubscription,
  myBilling,
  openBillingPortal,
} from "@/lib/billing.functions";
import { formatMoney } from "@/lib/billing-schema";

export const Route = createFileRoute("/_authenticated/suscripcion")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "settings" } });
  },
  head: () =>
    meta("Mi suscripción · Peluqo", "Gestiona, cambia o cancela tu plan y revisa tus pedidos."),
  component: Sub,
});

const status: Record<string, string> = {
  active: "Activa",
  trialing: "En prueba",
  past_due: "Pago pendiente",
  canceled: "Cancelada",
  incomplete: "Incompleta",
  unpaid: "Impagada",
};

function Sub() {
  const read = useServerFn(myBilling);
  const portal = useServerFn(openBillingPortal);
  const change = useServerFn(changeSubscription);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["billing"], queryFn: () => read(), refetchInterval: 10000 });
  const cat = useQuery({ queryKey: ["billing-cat"], queryFn: () => billingCatalogue() });
  const [msg, setMsg] = useState("");
  const sub = q.data?.subscriptions.find((s) => s.status !== "canceled");
  const run = async (f: () => Promise<unknown>, ok: string) => {
    setMsg("");
    try {
      await f();
      setMsg(ok);
      setTimeout(() => qc.invalidateQueries({ queryKey: ["billing"] }), 2000);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Error");
    }
  };
  return (
    <>
      <Section tone="sky">
        <PageTitle kicker="Mi perfil" title="Suscripción" />
      </Section>
      <Section>
        {msg && (
          <p role="status" className="platform-message mb-4">
            {msg}
          </p>
        )}
        {q.isPending ? (
          <p role="status">Cargando tu suscripción…</p>
        ) : q.error ? (
          <p className="platform-message" role="alert">
            {q.error.message}
          </p>
        ) : !sub ? (
          <EmptyState
            title="Tu cuenta no tiene un plan activo"
            action={
              <Link className="btn" to="/planes">
                Ver planes
              </Link>
            }
          >
            Consulta las modalidades disponibles para tu cuenta.
          </EmptyState>
        ) : (
          <div className="card bg-sunburst">
            <h2 className="text-3xl font-bold">
              Peluqo {sub.plan_code[0]!.toUpperCase() + sub.plan_code.slice(1)} ·{" "}
              {sub.billing_interval === "year" ? "anual" : "mensual"}
            </h2>
            <p className="mt-2">
              Estado: {status[sub.status] ?? sub.status}
              {sub.current_period_end &&
                ` · ${sub.cancel_at_period_end ? "termina" : "se renueva"} el ${new Date(sub.current_period_end).toLocaleDateString("es-ES")}`}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {sub.cancel_at_period_end ? (
                <Button
                  onClick={() =>
                    run(() => change({ data: { action: "resume" } }), "Renovación reactivada.")
                  }
                >
                  Mantener suscripción
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={() =>
                    confirm("¿Cancelar al final del periodo?") &&
                    run(
                      () => change({ data: { action: "cancel" } }),
                      "Se cancelará al final del periodo.",
                    )
                  }
                >
                  Cancelar
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() =>
                  run(async () => {
                    const r = await portal();
                    window.location.href = r.url;
                  }, "")
                }
              >
                Métodos de pago y facturas
              </Button>
            </div>
            <h3 className="mt-6 text-xl font-bold">Cambiar de plan</h3>
            <div className="mt-2 flex flex-wrap gap-2">
              {cat.data?.prices
                .filter((p) => p.is_active && p.unit_amount)
                .map((p) => {
                  const plan = cat.data!.plans.find((x) => x.id === p.plan_id);
                  if (
                    !plan?.is_active ||
                    (plan.code === sub.plan_code && p.billing_interval === sub.billing_interval)
                  )
                    return null;
                  return (
                    <Button
                      key={p.id}
                      variant="outline"
                      onClick={() =>
                        run(
                          () => change({ data: { action: "change", priceId: p.id } }),
                          "Plan actualizado.",
                        )
                      }
                    >
                      {plan.name} · {formatMoney(p.unit_amount, p.currency)}/
                      {p.billing_interval === "year" ? "año" : "mes"}
                    </Button>
                  );
                })}
            </div>
          </div>
        )}
        <h2 className="mt-10 text-3xl font-bold">Mis pedidos</h2>
        {q.data?.orders.length === 0 && (
          <p className="mt-3">Aún no hay pedidos asociados a tu cuenta.</p>
        )}
        {q.data?.orders.map((o) => (
          <p key={o.id} className="mt-3">
            {new Date(o.created_at).toLocaleDateString("es-ES")} ·{" "}
            {o.shop_order_items.map((i) => `${i.quantity}× ${i.product_name}`).join(", ")} ·{" "}
            {formatMoney(o.total_amount, o.currency)} ·{" "}
            {
              (
                {
                  paid: "Pagado",
                  pending: "Pendiente",
                  expired: "Caducado",
                  failed: "Fallido",
                } as Record<string, string>
              )[o.status]
            }
          </p>
        ))}
      </Section>
    </>
  );
}
