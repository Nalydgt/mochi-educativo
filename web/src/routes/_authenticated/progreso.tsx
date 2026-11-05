import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ArrowRight, BookOpen, Medal, Star } from "lucide-react";
import { accountData } from "@/lib/learning.functions";
import { EmptyState, PageTitle, Section, meta } from "@/components/Layout";

export const Route = createFileRoute("/_authenticated/progreso")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "assignments" } });
  },
  head: () => meta("Mi progreso", "Resultados e insignias de tu perfil en Peluqo."),
  component: Progress,
});

function Progress() {
  const read = useServerFn(accountData);
  const account = useQuery({ queryKey: ["account"], queryFn: () => read() });
  const id = account.data?.profile?.active_learner_id;
  const learner = account.data?.learners.find((item) => item.id === id);
  const lessons = account.data?.progress.filter((item) => item.learner_id === id) ?? [];
  const badges = account.data?.badges.filter((item) => item.learner_id === id) ?? [];
  const metrics = [
    {
      label: "Lecciones completadas",
      value: lessons.filter((item) => item.status === "completed").length,
      icon: BookOpen,
    },
    {
      label: "Estrellas ganadas",
      value: lessons.reduce((sum, item) => sum + item.best_score, 0),
      icon: Star,
    },
    { label: "Insignias", value: badges.length, icon: Medal },
  ];

  return (
    <>
      <Section tone="sky">
        <PageTitle
          kicker={learner?.display_name ?? "Tu perfil"}
          title="Mi progreso"
          sub="Repasa lo que has practicado y los logros que has conseguido."
        />
      </Section>
      <Section>
        {account.error ? (
          <p className="platform-message" role="alert">
            {account.error.message}
          </p>
        ) : account.isPending ? (
          <p role="status">Cargando tus resultados…</p>
        ) : !id ? (
          <EmptyState
            title="Elige un perfil"
            action={
              <Link className="btn btn-primary" to="/familia">
                Seleccionar perfil
              </Link>
            }
          >
            El progreso se guarda por separado en cada perfil de aprendizaje.
          </EmptyState>
        ) : (
          <>
            <dl className="platform-metrics">
              {metrics.map(({ label, value, icon: Icon }) => (
                <div key={label}>
                  <dt>
                    <Icon size={18} aria-hidden="true" /> {label}
                  </dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <h2 className="mt-8 mb-4 text-2xl font-bold">Mis lecciones</h2>
            {lessons.length === 0 ? (
              <EmptyState
                title="Empieza por un mundo"
                action={
                  <Link className="btn" to="/mundos">
                    Explorar mundos
                  </Link>
                }
              >
                Aquí verás cuánto has completado de cada lección.
              </EmptyState>
            ) : (
              <ul className="platform-result-list">
                {lessons.map((lesson) => (
                  <li key={lesson.id}>
                    {lesson.lessons?.slug ? (
                      <Link
                        className="platform-route-action"
                        to="/lecciones/$leccion"
                        params={{ leccion: lesson.lessons.slug }}
                      >
                        {lesson.lessons.title} <ArrowRight size={16} aria-hidden="true" />
                      </Link>
                    ) : (
                      <strong>Lección</strong>
                    )}
                    <span>
                      {lesson.completion_percentage}% completado · {lesson.best_score} estrellas
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <h2 className="mt-8 mb-4 text-2xl font-bold">Mi colección</h2>
            {badges.length > 0 ? (
              <ul className="flex flex-wrap gap-2">
                {badges.map((badge) => (
                  <li className="platform-tag bg-sunburst" key={badge.id}>
                    <Medal size={17} aria-hidden="true" /> {badge.achievements?.title}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">
                Las insignias aparecerán aquí cuando completes lecciones.
              </p>
            )}
          </>
        )}
      </Section>
    </>
  );
}
