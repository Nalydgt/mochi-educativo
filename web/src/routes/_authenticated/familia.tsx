import { createFileRoute } from "@tanstack/react-router";
import { AdultWorkspace } from "@/components/education/AdultWorkspace";
export const Route = createFileRoute("/_authenticated/familia")({
  validateSearch: (search: Record<string, unknown>): { panel?: string } =>
    typeof search["panel"] === "string" ? { panel: search["panel"] } : {},
  head: () => ({ meta: [{ title: "MOCHI · Panel familiar" }] }),
  component: Family,
});
function Family() {
  const { panel } = Route.useSearch();
  return <AdultWorkspace initialView={panel} />;
}
