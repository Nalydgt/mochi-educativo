import { createFileRoute } from "@tanstack/react-router";
import { AuthForm } from "@/components/AuthForm";
import { meta } from "@/components/Layout";
export const Route = createFileRoute("/entrar")({
  head: () => meta("Entrar", "Accede a tu panel adulto de Mochi."),
  component: () => <AuthForm />,
});
