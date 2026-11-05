import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute } from "@tanstack/react-router";
import { meta } from "@/components/Layout";
import { StudyPanel } from "@/components/StudyPanel";
export const Route = createFileRoute("/_authenticated/estudio/")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "materials" } });
  },
  head: () => meta("Peluqo Study", "Tus cuadernos y documentos privados para estudiar."),
  component: StudyPanel,
});
