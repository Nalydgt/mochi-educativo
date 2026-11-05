import { createFileRoute } from "@tanstack/react-router";
import { AdultWorkspace } from "@/components/education/AdultWorkspace";
export const Route = createFileRoute("/")({
  ssr: false,
  validateSearch: (search: Record<string, unknown>): { panel?: string } =>
    typeof search["panel"] === "string" ? { panel: search["panel"] } : {},
  head: () => ({
    meta: [
      { title: "MOCHI · Profesores y familias" },
      {
        name: "description",
        content:
          "Paneles para acompañar el aprendizaje con Mochi: actividades, revisión docente y comunicación familiar.",
      },
    ],
  }),
  component: AdultHome,
});
function AdultHome() {
  const { panel } = Route.useSearch();
  return <AdultWorkspace initialView={panel} />;
}
