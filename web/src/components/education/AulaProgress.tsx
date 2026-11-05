import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  ChartNoAxesCombined,
  CircleHelp,
  Flag,
  GraduationCap,
  Link2,
  Users,
} from "lucide-react";
import { adultRequest, useAdultAccountId } from "@/lib/education/adult-client";
import type {
  ProgressDashboardData,
  ProgressRole,
  ProgressStatus,
  WorldProgress,
} from "@/lib/education/progress";
import { LearningAnalytics } from "./LearningAnalytics";
import "./progress.css";

const statusNames: Record<ProgressStatus, string> = {
  not_started: "Sin empezar",
  working: "En marcha",
  support: "Revisar práctica",
  inactive: "Sin respuestas recientes",
  complete: "Completada",
};

const date = new Intl.DateTimeFormat("es", { dateStyle: "medium" });

function Assessment({
  name,
  score,
  due,
}: {
  name: string;
  score: WorldProgress["diagnostic"];
  due?: string | null;
}) {
  return (
    <div>
      <span>{name}</span>
      <strong>{score ? `${score.correct} de ${score.total}` : "Pendiente"}</strong>
      {score ? (
        <small>respuestas correctas</small>
      ) : (
        due && <small>Desde el {date.format(new Date(due))}</small>
      )}
    </div>
  );
}

function Evidence({ row }: { row: WorldProgress }) {
  return (
    <div className="progress-evidence">
      {!!row.alerts.length && (
        <section className="progress-alerts" aria-label="Señales para revisar">
          <h4>
            <CircleHelp size={17} aria-hidden="true" /> Señales para revisar
          </h4>
          <ul>
            {row.alerts.map((alert) => (
              <li key={`${alert.kind}:${alert.title}`}>
                <strong>{alert.title}</strong>
                <span>{alert.detail}</span>
                <small>{alert.action}</small>
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="progress-assessments">
        <Assessment name="Punto de partida" score={row.diagnostic} />
        <Assessment name="Evaluación final" score={row.final} />
        <Assessment name="Retención" score={row.retention} due={row.retentionAt} />
      </div>
      <p>
        {row.discoveries} de {row.practiceTotal} retos completados · {row.responses} respuestas ·{" "}
        {row.aids} ayudas
      </p>
      {!!row.skills.length && (
        <ul className="progress-skills" aria-label="Evidencias por competencia">
          {row.skills.map((skill) => (
            <li key={skill.name}>
              <strong>{skill.name}</strong>
              <span>
                {skill.unaided} retos resueltos sin ayuda de {skill.solved} completados
              </span>
              {skill.needsSupport && (
                <small>
                  Varios intentos sin resolver. Revisa un ejemplo juntos y vuelve a probar con otra
                  mecánica.
                </small>
              )}
            </li>
          ))}
        </ul>
      )}
      {!!row.formats.length && (
        <div className="progress-format">
          {row.formats.map((format) => (
            <span key={format.format}>
              {format.format === "cards" ? "Variante guiada" : "Juego principal"} · {format.correct}{" "}
              de {format.attempts} aciertos
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function AulaProgress({
  role,
  classId,
  renderControls,
}: {
  role: ProgressRole;
  classId?: string;
  renderControls?: (pupil: ProgressDashboardData["pupils"][number]) => React.ReactNode;
}) {
  const accountId = useAdultAccountId();
  const qc = useQueryClient();
  const [pupilId, setPupilId] = useState("");
  const [worldId, setWorldId] = useState("");
  const [filter, setFilter] = useState<"all" | "review" | "not_started" | "complete">("all");
  const [view, setView] = useState<"overview" | "analytics">("overview");
  const [linkStatus, setLinkStatus] = useState<{ text: string; error: boolean }>();
  const [linking, setLinking] = useState(false);
  const endpoint = "/api/education/progress";
  const report = useQuery({
    queryKey: ["aula-progress", accountId, role, classId],
    queryFn: () =>
      adultRequest<ProgressDashboardData>(classId ? `${endpoint}?classId=${classId}` : endpoint),
    enabled: !!accountId,
    retry: false,
    staleTime: 30_000,
  });
  const pupils = report.data?.pupils ?? [];
  const chosenPupil =
    pupils.find((p) => p.id === pupilId) ?? (role === "family" ? pupils[0] : undefined);
  const worlds = (report.data?.worlds ?? []).filter(
    (w) => !chosenPupil || w.classId === chosenPupil.classId,
  );
  const chosenWorld =
    worlds.find((w) => w.id === worldId) ??
    worlds.find((w) =>
      pupils.some(
        (p) =>
          (!chosenPupil || chosenPupil.id === p.id) &&
          p.progress.some((row) => row.worldId === w.id && row.status !== "not_started"),
      ),
    ) ??
    worlds[0];
  const rows = (chosenPupil ? [chosenPupil] : pupils).flatMap((pupil) => {
    const row = pupil.progress.find((x) => x.worldId === chosenWorld?.id);
    return row ? [{ pupil, row }] : [];
  });
  const complete = rows.filter(({ row }) => row.status === "complete").length;
  const review = rows.filter(({ row }) => ["support", "inactive"].includes(row.status)).length;
  const notStarted = rows.filter(({ row }) => row.status === "not_started").length;
  const visible = rows.filter(
    ({ row }) =>
      filter === "all" ||
      (filter === "review" ? ["support", "inactive"].includes(row.status) : row.status === filter),
  );

  async function linkFamily(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setLinking(true);
    setLinkStatus(undefined);
    try {
      await adultRequest(endpoint, { code: new FormData(form).get("code") });
      form.reset();
      await qc.invalidateQueries({ queryKey: ["aula-progress", accountId] });
      setLinkStatus({ text: "Ya puedes consultar el progreso de este estudiante.", error: false });
    } catch (error) {
      setLinkStatus({ text: (error as Error).message, error: true });
    } finally {
      setLinking(false);
    }
  }

  return (
    <div className="progress-dashboard">
      <header className="progress-dashboard-head">
        <div>
          <span className="progress-eyebrow">
            <ChartNoAxesCombined size={18} aria-hidden="true" /> Cuaderno de seguimiento
          </span>
          <h2>{role === "teacher" ? "El progreso de tu clase" : "El progreso en Peluqo"}</h2>
          <p>
            Consulta lo que han practicado, lo que ya pueden resolver y dónde conviene acompañarlos.
          </p>
        </div>
        <div className="progress-views" aria-label="Vista del seguimiento">
          <button
            type="button"
            aria-pressed={view === "overview"}
            onClick={() => setView("overview")}
          >
            <BookOpen size={17} aria-hidden="true" /> Aprendizaje
          </button>
          <button
            type="button"
            aria-pressed={view === "analytics"}
            onClick={() => setView("analytics")}
          >
            <ChartNoAxesCombined size={17} aria-hidden="true" /> Actividad
          </button>
        </div>
      </header>
      {role === "family" && (
        <details className="progress-link" open={pupils.length === 0 || undefined}>
          <summary>
            <Link2 size={18} aria-hidden="true" /> Vincular a un estudiante
          </summary>
          <p>Introduce el código familiar que facilita el docente. Empieza por F.</p>
          <form onSubmit={(event) => void linkFamily(event)}>
            <label htmlFor="progress-family-code">Código familiar</label>
            <input
              id="progress-family-code"
              name="code"
              autoComplete="off"
              spellCheck={false}
              maxLength={40}
              required
            />
            <button disabled={linking}>{linking ? "Vinculando…" : "Vincular estudiante"}</button>
          </form>
          {linkStatus && <p role={linkStatus.error ? "alert" : "status"}>{linkStatus.text}</p>}
        </details>
      )}
      {report.isError ? (
        <p className="progress-empty" role="alert">
          {report.error.message}{" "}
          <button onClick={() => void report.refetch()}>Volver a cargar</button>
        </p>
      ) : !accountId || report.isPending ? (
        <p className="progress-empty" role="status">
          Cargando el seguimiento…
        </p>
      ) : (
        <>
          {pupils.length > 0 && (
            <div className="progress-filters">
              <label>
                Estudiante
                <select value={chosenPupil?.id ?? ""} onChange={(e) => setPupilId(e.target.value)}>
                  {role === "teacher" && <option value="">Toda la clase</option>}
                  {pupils.map((pupil) => (
                    <option value={pupil.id} key={pupil.id}>
                      {pupil.name}
                      {role === "family" && ` · ${pupil.className}`}
                    </option>
                  ))}
                </select>
              </label>
              {view === "overview" && !!worlds.length && (
                <label>
                  Aventura
                  <select
                    value={chosenWorld?.id ?? ""}
                    onChange={(e) => setWorldId(e.target.value)}
                  >
                    {worlds.map((world) => (
                      <option key={world.id} value={world.id}>
                        {world.title} · {date.format(new Date(world.publishedAt))}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          )}
          {role === "family" && chosenPupil && renderControls?.(chosenPupil)}
          {view === "analytics" ? (
            <LearningAnalytics classId={classId} learnerId={chosenPupil?.id} />
          ) : !chosenWorld ? (
            <div className="progress-empty">
              <BookOpen size={28} aria-hidden="true" />
              <h3>Aún no hay aventuras para mostrar</h3>
              <p>El avance aparecerá aquí cuando haya una misión publicada para los estudiantes.</p>
            </div>
          ) : (
            <>
              <div className="progress-kpis">
                <div>
                  <Users size={19} aria-hidden="true" />
                  <strong>{rows.length}</strong>
                  <span>{role === "teacher" ? "Estudiantes" : "Estudiante seleccionado"}</span>
                </div>
                <div>
                  <GraduationCap size={19} aria-hidden="true" />
                  <strong>{complete}</strong>
                  <span>Misiones completadas</span>
                </div>
                <div>
                  <CircleHelp size={19} aria-hidden="true" />
                  <strong>{review}</strong>
                  <span>Para revisar</span>
                </div>
                <div>
                  <Flag size={19} aria-hidden="true" />
                  <strong>{notStarted}</strong>
                  <span>Sin empezar</span>
                </div>
              </div>
              {role === "teacher" && (
                <label className="progress-row-filter">
                  Situación
                  <select
                    value={filter}
                    onChange={(e) => setFilter(e.target.value as typeof filter)}
                  >
                    <option value="all">Todas</option>
                    <option value="review">Para revisar</option>
                    <option value="not_started">Sin empezar</option>
                    <option value="complete">Completadas</option>
                  </select>
                </label>
              )}
              <div className="progress-roster">
                {visible.map(({ pupil, row }) => (
                  <article key={pupil.id} className="progress-pupil">
                    <div className="progress-pupil-summary">
                      <div className="progress-pupil-name">
                        <span aria-hidden="true">{pupil.name.slice(0, 1)}</span>
                        <div>
                          <h3>{pupil.name}</h3>
                          <small>{pupil.guided ? "Refuerzo guiado activo" : pupil.className}</small>
                        </div>
                      </div>
                      <div className="progress-bar">
                        <strong>{row.percent}%</strong>
                        <progress
                          aria-label={`Avance de ${pupil.name}`}
                          value={row.percent}
                          max={100}
                        />
                      </div>
                      <span className="progress-status" data-status={row.status}>
                        {statusNames[row.status]}
                      </span>
                      <small>
                        {row.lastActivity
                          ? date.format(new Date(row.lastActivity))
                          : "Sin actividad"}
                      </small>
                    </div>
                    <details open={role === "family" || undefined}>
                      <summary>
                        Ver evidencias{" "}
                        {row.alerts.length > 0 &&
                          `· ${row.alerts.length} ${row.alerts.length === 1 ? "señal" : "señales"}`}{" "}
                        <ArrowUpRight size={15} aria-hidden="true" />
                      </summary>
                      <Evidence row={row} />
                      {role === "teacher" && renderControls?.(pupil)}
                    </details>
                  </article>
                ))}
                {!visible.length && (
                  <p className="progress-empty">No hay estudiantes que coincidan con el filtro.</p>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
