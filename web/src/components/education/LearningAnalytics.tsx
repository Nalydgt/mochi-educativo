import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, CalendarDays, Clock3, Gamepad2, Target } from "lucide-react";
import { adultRequest, useAdultAccountId } from "@/lib/education/adult-client";
import type { AnalyticsData, AnalyticsMetrics, AnalyticsRow } from "@/lib/education/analytics";
import { activityLabels, difficulties, subjects } from "@/lib/education/schema";
import "./progress.css";

const metrics: AnalyticsMetrics = {
  active_seconds: 0,
  visible_seconds: 0,
  started: 0,
  completed: 0,
  attempts: 0,
  graded: 0,
  correct: 0,
  exits: 0,
  hints: 0,
  tutor: 0,
  logins: 0,
  logouts: 0,
  variants: 0,
  visits: 0,
  errors: 0,
};
const metricKeys = Object.keys(metrics) as (keyof AnalyticsMetrics)[];
const subjectNames = { ...subjects, sin_clasificar: "Sin asignatura asignada" };
const number = new Intl.NumberFormat("es");
const shortDate = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const monthDate = new Intl.DateTimeFormat("es", {
  month: "short",
  year: "2-digit",
  timeZone: "UTC",
});
const week = 7 * 86_400_000;
type Period = "day" | "week" | "month";

function total(rows: readonly AnalyticsMetrics[]) {
  const result = { ...metrics };
  for (const row of rows) for (const key of metricKeys) result[key] += row[key];
  return result;
}

function localDay(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function duration(seconds: number) {
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function grouping(rows: AnalyticsRow[], key: (row: AnalyticsRow) => string | null | undefined) {
  const groups = new Map<string, AnalyticsMetrics>();
  for (const row of rows) {
    const label = key(row);
    if (!label) continue;
    const group = groups.get(label) ?? { ...metrics };
    for (const k of metricKeys) group[k] += row[k];
    groups.set(label, group);
  }
  return [...groups.entries()];
}

function periodKey(day: string, period: Period) {
  if (period === "month") return day.slice(0, 7) + "-01";
  if (period === "day") return day;
  const date = new Date(day);
  const monday = Date.parse(day) - ((date.getUTCDay() + 6) % 7) * (week / 7);
  return new Date(monday).toISOString().slice(0, 10);
}

function Trend({
  rows,
  period,
  from,
  to,
}: {
  rows: AnalyticsRow[];
  period: Period;
  from: string;
  to: string;
}) {
  const byDay = new Map(grouping(rows, (row) => periodKey(row.day, period)));
  const bars: { label: string; key: string; value: AnalyticsMetrics }[] = [];
  for (let timestamp = Date.parse(from); timestamp <= Date.parse(to); timestamp += 86_400_000) {
    const day = periodKey(new Date(timestamp).toISOString().slice(0, 10), period);
    if (bars.at(-1)?.key !== day) {
      bars.push({
        label: (period === "month" ? monthDate : shortDate).format(new Date(day)),
        key: day,
        value: byDay.get(day) ?? metrics,
      });
    }
  }
  const maxTime = Math.max(1, ...bars.map(({ value }) => value.visible_seconds));
  return (
    <section className="progress-chart">
      <h3>
        <Activity size={19} aria-hidden="true" /> Ritmo de estudio y aciertos
      </h3>
      <p>
        El tiempo activo se estima por la interacción reciente. Al ocultar la pestaña se deja de
        contar.
      </p>
      <div className="progress-chart-legend">
        <span className="legend-open">Aula visible</span>
        <span className="legend-active">Estudio activo</span>
        <span className="legend-score">Aciertos entre respuestas corregidas</span>
      </div>
      <div
        className="progress-chart-scroll"
        role="region"
        aria-label="Gráfico de evolución"
        tabIndex={0}
      >
        <div className="progress-chart-bars" aria-hidden="true">
          {bars.map(({ key, label, value }) => (
            <div
              key={key}
              title={`${label} · ${duration(value.active_seconds)} de estudio · ${value.correct}/${value.graded} aciertos`}
            >
              <span className="chart-bars-track">
                <i
                  className="chart-open"
                  style={{ height: `${(value.visible_seconds / maxTime) * 100}%` }}
                />
                <i
                  className="chart-active"
                  style={{ height: `${(value.active_seconds / maxTime) * 100}%` }}
                />
                {value.graded > 0 && (
                  <i
                    className="chart-score"
                    style={{ bottom: `${(value.correct / value.graded) * 100}%` }}
                  />
                )}
              </span>
              <small>{label}</small>
            </div>
          ))}
        </div>
      </div>
      <details className="progress-chart-data">
        <summary>Ver datos del gráfico</summary>
        <div className="progress-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Aula visible</th>
                <th>Estudio activo</th>
                <th>Retos terminados</th>
                <th>Aciertos</th>
              </tr>
            </thead>
            <tbody>
              {bars.map(({ key, label, value }) => (
                <tr key={key}>
                  <th scope="row">{label}</th>
                  <td>{duration(value.visible_seconds)}</td>
                  <td>{duration(value.active_seconds)}</td>
                  <td>{value.completed}</td>
                  <td>
                    {value.graded
                      ? `${value.correct} de ${value.graded}`
                      : "Sin corrección disponible"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

export function LearningAnalytics({
  classId,
  learnerId,
  admin = false,
}: {
  classId?: string | undefined;
  learnerId?: string | undefined;
  admin?: boolean;
}) {
  const account = useAdultAccountId();
  const [from, setFrom] = useState(() => localDay(new Date(Date.now() - 4 * week + 86_400_000)));
  const [to, setTo] = useState(() => localDay(new Date()));
  const [period, setPeriod] = useState<Period>("week");
  const [subject, setSubject] = useState("");
  const [chosenActivity, setChosenActivity] = useState("");
  const [versionId, activityId] = chosenActivity.split(":");
  const valid =
    !!from &&
    !!to &&
    Date.parse(to) >= Date.parse(from) &&
    Date.parse(to) - Date.parse(from) < 90 * 86_400_000;
  const zone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);
  const params = new URLSearchParams({ from, to, zone, scope: admin ? "admin" : "education" });
  if (classId) params.set("classId", classId);
  if (learnerId) params.set("learnerId", learnerId);
  if (subject) params.set("subject", subject);
  if (versionId && activityId) {
    params.set("versionId", versionId);
    params.set("activityId", activityId);
  }
  const query = useQuery({
    queryKey: ["learning-analytics", account, params.toString()],
    queryFn: () => adultRequest<AnalyticsData>(`/api/education/analytics?${params}`),
    enabled: !!account && valid,
    retry: false,
    staleTime: 30_000,
  });
  const rows = query.data?.rows ?? [];
  const stats = total(rows);
  const activities = (query.data?.catalog ?? []).filter((a) => !subject || a.subject === subject);
  const uniqueGames = grouping(rows, (a) => a.game)
    .filter(([, value]) => value.started || value.attempts)
    .sort(([, a], [, b]) => b.started - a.started || b.attempts - a.attempts);
  const bySubject = grouping(rows, (a) => (a.version_id || a.game ? a.subject : null)).filter(
    ([, value]) => value.attempts || value.started || value.active_seconds,
  );
  const byDifficulty = grouping(rows, (a) =>
    a.game ? (a.difficulty ?? "unspecified") : null,
  ).filter(([, value]) => value.attempts || value.started);
  const byHour = new Map(grouping(rows, (a) => String(a.hour)));
  const maxHour = Math.max(1, ...[...byHour.values()].map((item) => item.active_seconds));
  const hasTime = stats.visible_seconds > 0;

  return (
    <section className="progress-analytics" aria-label="Actividad de aprendizaje">
      {admin && (
        <div className="progress-admin-intro">
          <h2>Actividad de la plataforma</h2>
          <p>Totales de Peluqo Aula, agrupados sin nombres de estudiantes ni títulos privados.</p>
        </div>
      )}
      <div className="progress-filters">
        <label>
          Desde{" "}
          <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label>
          Hasta{" "}
          <input
            type="date"
            value={to}
            min={from}
            max={localDay(new Date())}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <label>
          Agrupar por{" "}
          <select value={period} onChange={(e) => setPeriod(e.target.value as Period)}>
            <option value="day">Día</option>
            <option value="week">Semana</option>
            <option value="month">Mes</option>
          </select>
        </label>
        {!admin && (
          <label>
            Asignatura{" "}
            <select
              value={subject}
              onChange={(e) => {
                setSubject(e.target.value);
                setChosenActivity("");
              }}
            >
              <option value="">Todas</option>
              {Object.entries(subjectNames).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
        {!admin && (
          <label>
            Actividad{" "}
            <select value={chosenActivity} onChange={(e) => setChosenActivity(e.target.value)}>
              <option value="">Todas</option>
              {!!chosenActivity &&
                !activities.some((a) => `${a.version_id}:${a.id}` === chosenActivity) && (
                  <option value={chosenActivity}>Actividad seleccionada</option>
                )}
              {activities.map((a) => (
                <option key={`${a.version_id}:${a.id}`} value={`${a.version_id}:${a.id}`}>
                  {a.title}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {!valid ? (
        <p className="progress-empty" role="status">
          Elige un intervalo válido de hasta 90 días.
        </p>
      ) : query.isError ? (
        <p className="progress-empty" role="alert">
          {query.error.message} <button onClick={() => void query.refetch()}>Reintentar</button>
        </p>
      ) : query.isPending ? (
        <p className="progress-empty" role="status">
          Cargando actividad…
        </p>
      ) : rows.length === 0 ? (
        <p className="progress-empty">Todavía no hay actividad registrada en este intervalo.</p>
      ) : (
        <>
          <div className="progress-kpis">
            <div>
              <Clock3 size={19} aria-hidden="true" />
              <strong>{hasTime ? duration(stats.active_seconds) : "—"}</strong>
              <span>Estudio activo</span>
            </div>
            <div>
              <CalendarDays size={19} aria-hidden="true" />
              <strong>{hasTime ? duration(stats.visible_seconds) : "—"}</strong>
              <span>Aula visible</span>
            </div>
            <div>
              <Gamepad2 size={19} aria-hidden="true" />
              <strong>{number.format(stats.completed)}</strong>
              <span>Actividades completadas</span>
            </div>
            <div>
              <Target size={19} aria-hidden="true" />
              <strong>
                {stats.graded ? `${Math.round((stats.correct / stats.graded) * 100)}%` : "—"}
              </strong>
              <span>Aciertos · {stats.graded} respuestas corregidas</span>
            </div>
          </div>
          <Trend rows={rows} period={period} from={from} to={to} />
          {hasTime && (
            <section className="progress-chart">
              <h3>Horas habituales de estudio</h3>
              <p>Tiempo activo por hora local durante el intervalo.</p>
              <ol className="progress-hours">
                {Array.from({ length: 24 }, (_, hour) => {
                  const seconds = byHour.get(String(hour))?.active_seconds ?? 0;
                  return (
                    <li
                      key={hour}
                      aria-label={`${hour}:00 · ${duration(seconds)}`}
                      title={`${hour}:00 · ${duration(seconds)}`}
                    >
                      <span
                        aria-hidden="true"
                        style={{ height: `${(seconds / maxHour) * 100}%` }}
                      />
                      <small>{hour % 3 === 0 ? `${hour} h` : ""}</small>
                    </li>
                  );
                })}
              </ol>
            </section>
          )}
          <div className="progress-distributions">
            {!!bySubject.length && (
              <section className="progress-chart">
                <h3>Por asignatura</h3>
                <ul>
                  {bySubject.map(([key, value]) => (
                    <li key={key}>
                      <strong>
                        {subjectNames[key as keyof typeof subjectNames] ??
                          "Sin asignatura asignada"}
                      </strong>
                      <span>
                        {value.completed} completadas ·{" "}
                        {value.graded
                          ? `${value.correct} de ${value.graded} aciertos`
                          : "Sin corrección"}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {!!uniqueGames.length && (
              <section className="progress-chart">
                <h3>Juegos más practicados</h3>
                <ul>
                  {uniqueGames.map(([key, value]) => (
                    <li key={key}>
                      <strong>{activityLabels[key as keyof typeof activityLabels] ?? key}</strong>
                      <span>
                        {value.started} aperturas · {value.completed} completadas · {value.attempts}{" "}
                        intentos
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {!!byDifficulty.length && (
              <section className="progress-chart">
                <h3>Dificultad de los retos</h3>
                <ul>
                  {byDifficulty.map(([key, value]) => (
                    <li key={key}>
                      <strong>
                        {difficulties[key as keyof typeof difficulties] ?? "Sin nivel indicado"}
                      </strong>
                      <span>
                        {value.graded
                          ? `${value.correct} de ${value.graded} aciertos`
                          : "Sin corrección"}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
          <p className="progress-usage">
            {stats.logins} accesos · {stats.logouts} cierres registrados · {stats.exits} salidas de
            un reto sin terminar · {stats.hints} pistas · {stats.tutor} turnos con el tutor ·{" "}
            {stats.variants} cambios de variante
            {admin &&
              ` · ${stats.visits} visitas a secciones · ${stats.errors} incidencias de aplicación`}
          </p>
          <small>
            La medición de tiempo y uso empieza con esta versión del Aula. Los resultados incluyen
            los intentos previos disponibles. Los registros de uso se conservan 90 días.
          </small>
        </>
      )}
    </section>
  );
}
