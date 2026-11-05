import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { adultRequest, useAdultAccountId } from "@/lib/education/adult-client";
import {
  deviceLessonAssignmentSchema,
  type DeviceLessonReport,
} from "@/lib/education/device-lessons";
import "./device-lessons.css";

export function DeviceLessons({
  role,
  pupils = [],
  classId,
}: {
  role: "teacher" | "family";
  pupils?: { id: string; name: string }[];
  classId?: string;
}) {
  const account = useAdultAccountId();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const report = useQuery({
    queryKey: ["device-lessons", account],
    queryFn: () => adultRequest<DeviceLessonReport>("/api/education/device-lessons"),
    enabled: !!account,
    refetchInterval: 12000,
    retry: false,
  });
  const lessons = (report.data?.lessons ?? []).filter(
    (lesson) => !classId || lesson.classId === classId,
  );

  async function assign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const factors = String(fields.get("factors"))
        .split(",")
        .map((entry) =>
          entry
            .trim()
            .split(/[x×*]/i)
            .map((value) => Number(value.trim())),
        );
      const checked = deviceLessonAssignmentSchema.safeParse({
        action: "assign-device-lesson",
        learnerId: fields.get("learnerId"),
        subject: "matematicas",
        title: fields.get("title"),
        goal: fields.get("goal"),
        instructions: fields.get("instructions"),
        dueAt: fields.get("dueAt"),
        factors,
      });
      if (!checked.success) {
        const lengthIssue = checked.error.issues.find(
          (issue) => issue.path[0] === "title" || issue.path[0] === "instructions",
        );
        throw new Error(
          lengthIssue?.message ??
            "Revisa los campos. Escribe entre uno y cinco productos, con factores del 1 al 12: 3×4, 4×3, 2×6.",
        );
      }
      await adultRequest("/api/education/", checked.data);
      await qc.invalidateQueries({ queryKey: ["device-lessons", account] });
      setNotice(
        "Deberes asignados. Mochi los recibirá cuando se conecte; puede completarlos sin internet después de descargarlos.",
      );
      form.reset();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="device-lessons edu-panel" aria-labelledby={`mochi-lessons-${role}`}>
      <h2 id={`mochi-lessons-${role}`}>Deberes en Mochi</h2>
      <p>
        El niño enseña a Mochi a multiplicar mediante agrupaciones. Los resultados se reciben al
        sincronizar el dispositivo.
      </p>
      {role === "teacher" && (
        <details className="device-lessons-create" open={lessons.length === 0 || undefined}>
          <summary>Asignar una actividad</summary>
          {pupils.length === 0 ? (
            <p>Añade un alumno a esta clase para asignarle deberes.</p>
          ) : (
            <form onSubmit={(event) => void assign(event)} className="device-lessons-form">
              <label>
                Alumno
                <select name="learnerId" required>
                  {pupils.map((pupil) => (
                    <option key={pupil.id} value={pupil.id}>
                      {pupil.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Asignatura
                <input value="Matemáticas" readOnly />
              </label>
              <label>
                Título
                <input
                  name="title"
                  minLength={3}
                  maxLength={80}
                  defaultValue="Enseña a Mochi a multiplicar"
                  required
                />
              </label>
              <label>
                Fecha de entrega
                <input type="date" name="dueAt" required />
              </label>
              <label className="device-lessons-wide">
                Objetivo educativo
                <input
                  name="goal"
                  minLength={8}
                  maxLength={300}
                  defaultValue="Comprender la multiplicación mediante grupos iguales."
                  required
                />
              </label>
              <label className="device-lessons-wide">
                Instrucciones para Mochi
                <textarea
                  name="instructions"
                  minLength={8}
                  maxLength={200}
                  defaultValue="Enséñame cuántos objetos hay en cada grupo. Si nos confundimos, contamos juntos."
                  required
                />
              </label>
              <label className="device-lessons-wide">
                Multiplicaciones, separadas por comas
                <input
                  name="factors"
                  defaultValue="3×4, 4×3, 2×6"
                  aria-describedby="mochi-factor-help"
                  required
                />
                <small id="mochi-factor-help">
                  Entre uno y cinco ejercicios, factores del 1 al 12. Revisa los deberes antes de
                  asignarlos.
                </small>
              </label>
              <button className="btn btn-primary" disabled={busy}>
                {busy ? "Asignando…" : "Asignar a Mochi"}
              </button>
            </form>
          )}
        </details>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
      {!account || report.isPending ? (
        <p role="status">Cargando los deberes…</p>
      ) : report.isError ? (
        <p role="alert">
          {report.error.message}{" "}
          <button className="btn" onClick={() => void report.refetch()}>
            Volver a cargar
          </button>
        </p>
      ) : lessons.length === 0 ? (
        <p>No hay deberes asignados a Mochi para mostrar.</p>
      ) : (
        <ul className="device-lessons-list">
          {lessons.map((lesson) => (
            <li key={lesson.id}>
              <div className="device-lessons-row">
                <div>
                  <h3>{lesson.title}</h3>
                  <p>
                    {lesson.learnerName} · Entrega:{" "}
                    {new Intl.DateTimeFormat("es", { dateStyle: "medium" }).format(
                      new Date(lesson.dueAt + "T12:00:00"),
                    )}
                  </p>
                </div>
                <span className="device-lessons-status">
                  {lesson.result
                    ? "Recibido · pendiente de revisión"
                    : "Pendiente de completar y sincronizar"}
                </span>
              </div>
              <p>{lesson.goal}</p>
              {lesson.result && (
                <details>
                  <summary>Consultar evidencias de {lesson.learnerName}</summary>
                  <p>
                    {lesson.result.attempts} {lesson.result.attempts === 1 ? "intento" : "intentos"}{" "}
                    · {lesson.result.hints} {lesson.result.hints === 1 ? "pista" : "pistas"} ·{" "}
                    {lesson.result.elapsedSeconds < 60
                      ? "menos de 1 min"
                      : `${Math.round(lesson.result.elapsedSeconds / 60)} min aproximados`}{" "}
                    · {lesson.exerciseCount}{" "}
                    {lesson.exerciseCount === 1 ? "ejercicio completado" : "ejercicios completados"}
                  </p>
                  <ol>
                    {lesson.result.answers.map((answer, index) => (
                      <li key={index}>
                        {answer.a} × {answer.b} = {answer.choice}.{" "}
                        {answer.correct ? "Respuesta correcta" : "Necesitó otro intento"}.
                      </li>
                    ))}
                  </ol>
                  <p>
                    Indicadores de práctica guiada pendientes de revisión humana. No son una
                    calificación oficial ni un diagnóstico. Las conversaciones privadas no se
                    incluyen.
                  </p>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="device-lessons-note">
        La práctica descargada funciona con reglas locales. La conversación por voz requiere los
        servicios conectados; no se ejecuta un modelo de lenguaje en la placa.
      </p>
    </section>
  );
}
