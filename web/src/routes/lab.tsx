import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute } from "@tanstack/react-router";
import { Section, PageTitle, Tag, meta } from "@/components/Layout";
import { labProjects } from "@/data/peluqo";
import { Mascot } from "@/components/Stickers";
import { Link } from "@tanstack/react-router";

export const Route = createFileRoute("/lab")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "devices" } });
  },
  head: () =>
    meta("Robot y Lab", "Tu compañero robótico Peluqo Buddy y los proyectos para construirlo."),
  component: Lab,
});

function Lab() {
  return (
    <>
      <Section tone="sky">
        <PageTitle
          kicker="Laboratorio"
          title="Tu robot Peluqo"
          sub="Conoce a Buddy y explora los proyectos para construirlo."
          art="taller"
        />
      </Section>
      <Section>
        <div className="card mb-6 grid items-center gap-4 sm:grid-cols-[auto_1fr]">
          <Mascot />
          <div>
            <h2 className="text-2xl font-bold">Peluqo Buddy</h2>
            <p className="mt-2 text-muted-foreground">
              Explora los proyectos del laboratorio o personaliza tu compañero digital.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link to="/tienda" className="btn btn-primary">
                Ver tienda
              </Link>
              <Link to="/familia" className="btn">
                Personalizar Peluqo
              </Link>
            </div>
          </div>
        </div>
        <h2 className="mb-4 text-2xl font-bold">Proyectos de construcción</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {labProjects.map((p, i) => (
            <div key={p.title} className="card">
              <Tag color={p.color}>
                Proyecto {i + 1} · {p.level}
              </Tag>
              <h3 className="mt-3 text-xl font-bold">{p.title}</h3>
              <p className="mt-2 text-muted-foreground">{p.desc}</p>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
