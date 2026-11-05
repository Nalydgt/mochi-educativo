import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ArrowLeft, Lightbulb, Star } from "lucide-react";
import { catalogue, accountData, evaluate } from "@/lib/learning.functions";
import { Section, PageTitle, Tag, meta } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Mascot } from "@/components/Stickers";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/lecciones/$leccion")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "assignments" } });
  },
  loader: async ({ params }) => {
    const data = await catalogue();
    const lesson = data.lessons.find((entry) => entry.slug === params.leccion);
    if (!lesson) throw notFound();
    return {
      lesson,
      activities: data.activities.filter((activity) => activity.lesson_id === lesson.id),
    };
  },
  head: ({ loaderData }) =>
    meta(
      loaderData?.lesson.title ?? "Lección no disponible",
      loaderData?.lesson.description ?? "Aprendizaje interactivo de Peluqo.",
    ),
  component: Lesson,
});

function Lesson() {
  const data = Route.useLoaderData();
  return <LessonPage key={data.lesson.id} {...data} />;
}

type ActivityData = Awaited<ReturnType<typeof catalogue>>["activities"][number];
type LessonData = Awaited<ReturnType<typeof catalogue>>["lessons"][number];

function LessonPage({ lesson, activities }: { lesson: LessonData; activities: ActivityData[] }) {
  const [hint, setHint] = useState(0);
  const [planet, setPlanet] = useState(0);
  const client = useQueryClient();
  const read = useServerFn(accountData);
  const { data: user } = useQuery({
    queryKey: ["session-user"],
    queryFn: async () => (await supabase.auth.getUser()).data.user,
  });
  const account = useQuery({ queryKey: ["account"], queryFn: () => read(), enabled: !!user });
  const learner = account.data?.profile?.active_learner_id;
  const age = account.data?.learners.find((profile) => profile.id === learner)?.age_band;
  const progress = account.data?.progress.find(
    (item) => item.lesson_id === lesson.id && item.learner_id === learner,
  );
  const planets = lesson.content.planets;
  const activePlanet = planets?.[planet];

  return (
    <>
      <Section tone="sky">
        <Link className="platform-route-action mb-4" to="/mundos">
          <ArrowLeft size={17} aria-hidden="true" /> Mapa de mundos
        </Link>
        <PageTitle
          kicker={lesson.education_level}
          title={lesson.title}
          sub={lesson.content.intro}
          art={planets ? "observatorio" : "taller"}
        />
        <p className="mt-4">
          <strong>Objetivo.</strong> {lesson.content.goal}
        </p>
        {progress && (
          <p className="mt-2 text-sm font-bold text-primary">
            {progress.completion_percentage}% completado
          </p>
        )}
      </Section>
      <Section className={age === "6–8" ? "platform-young" : ""}>
        {planets && (
          <div className="card mb-6">
            <h2 className="text-xl font-bold">Explora los planetas</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {planets.map((item, index) => (
                <Button
                  key={item.name}
                  variant="outline"
                  className="platform-feedback-option"
                  aria-pressed={planet === index}
                  onClick={() => setPlanet(index)}
                >
                  {item.name}
                </Button>
              ))}
            </div>
            {activePlanet && (
              <div className="mt-4" role="status">
                <h3 className="font-bold">{activePlanet.name}</h3>
                <p>{activePlanet.detail}</p>
              </div>
            )}
          </div>
        )}

        {!user ? (
          <p className="platform-message">
            <Link to="/entrar" className="platform-route-action">
              Entrar para guardar tu aprendizaje
            </Link>
          </p>
        ) : (
          !learner && (
            <p className="platform-message">
              <Link className="platform-route-action" to="/familia">
                Seleccionar un perfil para comenzar
              </Link>
            </p>
          )
        )}

        <div className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(12rem,17rem)]">
          <div className="space-y-4">
            {activities.map((activity) => (
              <Activity
                key={`${activity.id}-${learner}`}
                activity={activity}
                learner={learner}
                onSaved={() => client.invalidateQueries({ queryKey: ["account"] })}
              />
            ))}
          </div>
          <aside className="card bg-mint" aria-label="Pistas de Peluqo">
            <Mascot mood="think" />
            <h2 className="mt-2 text-xl font-bold">Pistas de Peluqo</h2>
            <div aria-live="polite">
              {lesson.content.hints.slice(0, hint).map((item, index) => (
                <p className="mt-2" key={index}>
                  {item}
                </p>
              ))}
            </div>
            <Button
              className="mt-4"
              variant="outline"
              disabled={hint >= lesson.content.hints.length}
              onClick={() => setHint((value) => value + 1)}
            >
              <Lightbulb aria-hidden="true" /> Pedir pista
            </Button>
          </aside>
        </div>

        {progress?.status === "completed" && (
          <div className="platform-message mt-5" data-tone="success">
            <h2 className="text-xl font-bold">¡Lección completada!</h2>
            <Link className="platform-route-action mt-2" to="/progreso">
              <Star size={16} aria-hidden="true" /> Ver mis estrellas e insignias
            </Link>
          </div>
        )}
      </Section>
    </>
  );
}

function Activity({
  activity,
  learner,
  onSaved,
}: {
  activity: ActivityData;
  learner: string | undefined | null;
  onSaved: () => unknown;
}) {
  const submit = useServerFn(evaluate);
  const [selected, setSelected] = useState<number[]>([]);
  const [option, setOption] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof evaluate>>>();
  const [error, setError] = useState("");
  const isFraction = activity.activity_type === "interactive_fractions";
  const total = activity.public_config.total ?? 4;

  async function check() {
    if (!learner) return;
    setBusy(true);
    setError("");
    try {
      const scored = await submit({
        data: {
          learner,
          activity: activity.id,
          answer: isFraction ? { selected: selected.length } : { option: option ?? 0 },
        },
      });
      setResult(scored);
      await onSaved();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "No se pudo comprobar la respuesta.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card" aria-busy={busy}>
      <Tag color="bg-mist">Actividad {activity.display_order}</Tag>
      <h2 className="mt-2 text-xl font-bold">{activity.title}</h2>
      <p className="mt-2">{activity.instructions}</p>
      {isFraction ? (
        <div className="mt-5 grid items-center gap-4 sm:grid-cols-2">
          <svg
            className="mx-auto w-56 max-w-full"
            viewBox="0 0 200 200"
            role="group"
            aria-label="Pizza en porciones iguales"
          >
            {Array.from({ length: total }, (_, index) => {
              const start = (index / total) * 2 * Math.PI - Math.PI / 2;
              const end = ((index + 1) / total) * 2 * Math.PI - Math.PI / 2;
              const path = `M100,100 L${100 + 90 * Math.cos(start)},${100 + 90 * Math.sin(start)} A90,90 0 0 1 ${100 + 90 * Math.cos(end)},${100 + 90 * Math.sin(end)} Z`;
              const toggle = () => {
                if (busy) return;
                setResult(undefined);
                setSelected((pieces) =>
                  pieces.includes(index)
                    ? pieces.filter((piece) => piece !== index)
                    : [...pieces, index],
                );
              };
              return (
                <path
                  key={index}
                  d={path}
                  role="button"
                  tabIndex={0}
                  aria-label={`Porción ${index + 1}`}
                  aria-pressed={selected.includes(index)}
                  aria-disabled={busy}
                  onClick={toggle}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggle();
                    }
                  }}
                  className={
                    selected.includes(index)
                      ? "platform-fraction fill-electric"
                      : "platform-fraction fill-sunburst"
                  }
                  strokeWidth={2}
                />
              );
            })}
          </svg>
          <p role="status" className="text-lg font-bold">
            {selected.length} de {total} porciones seleccionadas
          </p>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          {activity.public_config.options?.map((answer, index) => (
            <Button
              key={index}
              variant="outline"
              disabled={busy}
              className="platform-feedback-option"
              aria-pressed={option === index}
              onClick={() => {
                setOption(index);
                setResult(undefined);
              }}
            >
              {answer}
            </Button>
          ))}
        </div>
      )}
      <Button
        className="mt-4"
        disabled={!learner || busy || (!isFraction && option === null)}
        onClick={() => void check()}
      >
        {busy ? "Comprobando…" : "Comprobar respuesta"}
      </Button>
      {result && (
        <div
          className="platform-message mt-4"
          data-tone={result.correct ? "success" : "error"}
          role={result.correct ? "status" : "alert"}
        >
          <strong>{result.correct ? "¡Correcto!" : "Revisa tu respuesta"}</strong>
          <p>{result.explanation}</p>
          {result.points > 0 && <p>{result.points} estrellas ganadas</p>}
        </div>
      )}
      {error && (
        <p className="platform-message mt-4" role="alert">
          {error}
        </p>
      )}
    </article>
  );
}
