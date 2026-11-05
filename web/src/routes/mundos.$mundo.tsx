import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { catalogue } from "@/lib/learning.functions";
import { subjectLandscape } from "@/components/BrandMark";
import { EmptyState, Section, PageTitle, Tag, meta } from "@/components/Layout";

export const Route = createFileRoute("/mundos/$mundo")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "assignments" } });
  },
  loader: async ({ params }) => {
    const data = await catalogue();
    const world = data.subjects.find((subject) => subject.slug === params.mundo);
    if (!world) throw notFound();
    return { ...data, world };
  },
  head: ({ loaderData }) =>
    meta(
      loaderData?.world.name ?? "Mundo no disponible",
      loaderData?.world.description ?? "Catálogo educativo de Peluqo.",
    ),
  component: World,
});

function World() {
  const { world, topics, lessons } = Route.useLoaderData();
  const available = topics.filter((topic) => topic.subject_id === world.id);
  return (
    <>
      <Section tone="sky">
        <Link className="platform-route-action mb-4" to="/mundos">
          <ArrowLeft size={17} aria-hidden="true" /> Mapa de mundos
        </Link>
        <PageTitle
          kicker="Mundos Peluqo"
          title={world.name}
          sub={world.description}
          art={subjectLandscape(world.slug)}
        />
      </Section>
      <Section>
        {available.length > 0 ? (
          <div className="grid gap-6 md:grid-cols-2">
            {available.map((topic) => {
              const entries = lessons.filter((lesson) => lesson.topic_id === topic.id);
              return (
                <section key={topic.id}>
                  <h2 className="text-xl font-bold">{topic.title}</h2>
                  {entries.map((lesson) => (
                    <Link
                      className="platform-route-card card mt-3"
                      to="/lecciones/$leccion"
                      params={{ leccion: lesson.slug }}
                      key={lesson.id}
                    >
                      <div className="flex flex-wrap gap-2">
                        <Tag>{lesson.education_level}</Tag>
                        <Tag color="bg-mist">{lesson.estimated_minutes} min</Tag>
                      </div>
                      <h3 className="mt-2 text-xl font-bold">{lesson.title}</h3>
                      <p className="mt-1 text-muted-foreground">{lesson.description}</p>
                      <span className="platform-route-action">
                        Abrir lección <ArrowRight size={16} aria-hidden="true" />
                      </span>
                    </Link>
                  ))}
                  {!entries.length && (
                    <p className="mt-2 text-sm text-muted-foreground">Lecciones en preparación.</p>
                  )}
                </section>
              );
            })}
          </div>
        ) : (
          <EmptyState title="Este mundo está en preparación">
            Elige otro mundo en el mapa para continuar.
          </EmptyState>
        )}
      </Section>
    </>
  );
}
