import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ArrowRight, BookOpen, Compass, Star, UsersRound } from "lucide-react";
import { accountData, catalogue } from "@/lib/learning.functions";
import { EmptyState, PageTitle, Section, Tag, meta } from "@/components/Layout";

export const Route = createFileRoute("/_authenticated/dashboard")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "overview" } });
  },
  head: () => meta("Mi espacio", "Tu espacio de aprendizaje y actividades en Peluqo."),
  component: Dashboard,
});

function Dashboard() {
  const read = useServerFn(accountData);
  const account = useQuery({ queryKey: ["account"], queryFn: () => read() });
  const catalog = useQuery({ queryKey: ["catalogue"], queryFn: () => catalogue() });
  const data = account.data;
  const activeId = data?.profile?.active_learner_id;
  const learner = data?.learners.find((item) => item.id === activeId);
  const recent =
    data?.progress
      .filter((item) => item.learner_id === activeId)
      .sort((first, second) => second.updated_at.localeCompare(first.updated_at)) ?? [];
  const teacher = data?.profile?.account_type === "teacher";
  const family = data?.profile?.account_type === "family";
  const young = learner?.age_band === "6–8";
  const available =
    catalog.data?.lessons.filter(
      (lesson) =>
        !recent.some((item) => item.lesson_id === lesson.id && item.status === "completed"),
    ) ?? [];
  const title = young
    ? `¡Hola, ${learner.display_name}!`
    : learner
      ? `Hola, ${learner.display_name}`
      : teacher
        ? "Tu espacio docente"
        : family
          ? "Tu espacio familiar"
          : "Tu aventura";

  return (
    <>
      <Section tone="sky">
        <PageTitle
          kicker="Mi Peluqo"
          title={title}
          sub={
            young
              ? "Elige qué quieres descubrir hoy."
              : "Accede a tus mundos, cuadernos y resultados."
          }
          art={teacher ? "taller" : "reserva"}
        />
        <div className="mt-5 flex flex-wrap gap-2">
          {teacher && (
            <Link className="btn btn-primary" to="/expedicion">
              <Compass size={17} aria-hidden="true" /> Abrir Aula
            </Link>
          )}
          <Link className={family ? "btn btn-primary" : "btn"} to="/familia">
            <UsersRound size={17} aria-hidden="true" />{" "}
            {family ? "Abrir panel familiar" : "Elegir perfil"}
          </Link>
          <Link className="btn" to="/progreso">
            <Star size={17} aria-hidden="true" /> Mi progreso
          </Link>
          <Link className="btn" to="/estudio">
            <BookOpen size={17} aria-hidden="true" /> Mis cuadernos
          </Link>
          <Link className="btn" to="/suscripcion">
            Mi suscripción
          </Link>
          {data?.admin && (
            <Link className="btn" to="/administracion">
              Administración
            </Link>
          )}
          {data?.admin && (
            <Link className="btn" to="/admin-tienda">
              Precios y stock
            </Link>
          )}
        </div>
      </Section>

      <Section>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl font-bold">
            {young ? "¿Qué jugamos?" : "Continuar aprendiendo"}
          </h2>
          <Link className="btn" to="/mundos">
            Todos los mundos <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
        {account.error && (
          <p className="platform-message mb-4" role="alert">
            {account.error.message}
          </p>
        )}
        {catalog.error && (
          <p className="platform-message mb-4" role="alert">
            {catalog.error.message}
          </p>
        )}
        {account.isPending || catalog.isPending ? (
          <p role="status">Cargando tu espacio…</p>
        ) : (
          <>
            {!activeId && !account.error && (
              <p className="mb-4 text-muted-foreground">
                Elige un perfil para guardar el progreso de estas lecciones.
              </p>
            )}
            {available.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">
                {available.map((lesson) => (
                  <Link
                    className="platform-route-card card"
                    key={lesson.id}
                    to="/lecciones/$leccion"
                    params={{ leccion: lesson.slug }}
                  >
                    <div className="flex flex-wrap gap-2">
                      <Tag>{lesson.education_level}</Tag>
                      <Tag color="bg-mist">{lesson.estimated_minutes} min</Tag>
                    </div>
                    <h3 className={young ? "mt-3 text-xl font-bold" : "mt-3 text-lg font-bold"}>
                      {lesson.title}
                    </h3>
                    <p className="mt-1 text-muted-foreground">{lesson.description}</p>
                    <span className="platform-route-action">
                      Abrir lección <ArrowRight size={16} aria-hidden="true" />
                    </span>
                  </Link>
                ))}
              </div>
            ) : (
              !catalog.error && (
                <EmptyState
                  title="Ya estás al día"
                  action={
                    <Link className="btn" to="/mundos">
                      Volver al mapa
                    </Link>
                  }
                >
                  Puedes volver a tus lecciones favoritas desde el mapa.
                </EmptyState>
              )
            )}
            {activeId && (
              <div className="mt-8">
                <h2 className="text-2xl font-bold">Últimos resultados</h2>
                {recent.length > 0 ? (
                  <ul className="platform-result-list mt-3">
                    {recent.map((result) => (
                      <li key={result.id}>
                        <strong>{result.lessons?.title}</strong>
                        <span>
                          {result.completion_percentage}% completado · {result.best_score} estrellas
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-muted-foreground">
                    Aquí verás lo que hayas practicado con este perfil.
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </Section>
    </>
  );
}
