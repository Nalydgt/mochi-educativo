import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Compass } from "lucide-react";
import { catalogue } from "@/lib/learning.functions";
import { presentationArt, subjectLandscape } from "@/components/BrandMark";
import { EmptyState, Section, PageTitle, Tag, meta } from "@/components/Layout";

export const Route = createFileRoute("/mundos/")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "assignments" } });
  },
  loader: () => catalogue(),
  head: () =>
    meta("Mapa de mundos", "Explora Matemáticas, Ciencias Naturales, Lengua y Ciencias Sociales."),
  component: Worlds,
});

function Worlds() {
  const data = Route.useLoaderData();
  return (
    <>
      <Section tone="sky">
        <PageTitle
          kicker="Biblioteca de Peluqo"
          title="¿Adónde vamos hoy?"
          sub="Elige un mundo y encuentra una lección para explorar a tu ritmo."
        />
      </Section>
      <Section>
        {data.subjects.length ? (
          <div className="grid gap-5 md:grid-cols-2">
            {data.subjects.map((subject) => {
              const topics = new Set(
                data.topics
                  .filter((topic) => topic.subject_id === subject.id)
                  .map((topic) => topic.id),
              );
              const count = data.lessons.filter((lesson) => topics.has(lesson.topic_id)).length;
              return (
                <Link
                  className="platform-world"
                  key={subject.id}
                  to="/mundos/$mundo"
                  params={{ mundo: subject.slug }}
                >
                  <img
                    src={`${presentationArt}/${subjectLandscape(subject.slug)}.webp`}
                    alt=""
                    width={1680}
                    height={746}
                  />
                  <div>
                    <Tag>
                      {count ? `${count} ${count === 1 ? "lección" : "lecciones"}` : "Próximamente"}
                    </Tag>
                    <h2 className="mt-2 text-2xl font-bold">{subject.name}</h2>
                    <p className="mt-1 text-muted-foreground">{subject.description}</p>
                    <span className="platform-route-action mt-3">
                      Ver mundo <ArrowRight size={16} aria-hidden="true" />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <EmptyState title="La biblioteca está vacía">
            Las lecciones que se publiquen aparecerán aquí.
          </EmptyState>
        )}
        <Link className="btn mt-6" to="/expedicion">
          <Compass size={18} aria-hidden="true" /> Ir a Peluqo Aula
        </Link>
      </Section>
    </>
  );
}
