import { createFileRoute } from "@tanstack/react-router";
import { AuthForm } from "@/components/AuthForm";
import { meta } from "@/components/Layout";
export const Route = createFileRoute("/auth")({
  head: () => meta("Acceso adulto", "Entra en el panel docente o familiar de Mochi."),
  component: () => <AuthForm />,
});
