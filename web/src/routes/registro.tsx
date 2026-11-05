import { createFileRoute } from "@tanstack/react-router";
import { AuthForm } from "@/components/AuthForm";
import { meta } from "@/components/Layout";

export const Route = createFileRoute("/registro")({
  validateSearch: (search: Record<string, unknown>): { tipo?: "docente" } =>
    search["tipo"] === "docente" ? { tipo: "docente" } : {},
  head: () => meta("Crear cuenta", "Crea tu cuenta y tus perfiles de aprendizaje."),
  component: Registration,
});

function Registration() {
  const { tipo } = Route.useSearch();
  return <AuthForm signup defaultType={tipo === "docente" ? "teacher" : "family"} />;
}
