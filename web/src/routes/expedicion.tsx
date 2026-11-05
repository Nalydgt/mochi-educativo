import { createFileRoute } from "@tanstack/react-router";
import { AdultWorkspace } from "@/components/education/AdultWorkspace";
export const Route = createFileRoute("/expedicion")({
  ssr: false,
  validateSearch: (search: Record<string, unknown>): { panel?: string; espacio?: "casa" } => ({
    ...(typeof search["panel"] === "string" ? { panel: search["panel"] } : {}),
    ...(search["espacio"] === "casa" ? { espacio: "casa" as const } : {}),
  }),
  head: () => ({ meta: [{ title: "MOCHI · Panel docente" }] }),
  component: Expedition,
});
function Expedition() {
  const { panel } = Route.useSearch();
  return <AdultWorkspace key="mochi-workspace" initialView={panel} />;
}
