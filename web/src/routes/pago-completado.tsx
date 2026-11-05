import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { meta, Section, PageTitle } from "@/components/Layout";

export const Route = createFileRoute("/pago-completado")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "settings" } });
  },
  head: () => meta("Pago recibido · Peluqo", "Estamos confirmando tu pago con Stripe."),
  component: () => (
    <Section tone="sky">
      <PageTitle
        kicker="Gracias"
        title="Pago recibido"
        sub="Stripe nos confirmará el pago en unos segundos. Tu plan o pedido se activará solo cuando llegue esa confirmación."
      />
      <div className="mt-6 flex flex-wrap gap-3">
        <Link className="btn btn-primary" to="/suscripcion">
          Ver mi suscripción y pedidos
        </Link>
        <Link className="btn" to="/">
          Volver al inicio
        </Link>
      </div>
    </Section>
  ),
});
