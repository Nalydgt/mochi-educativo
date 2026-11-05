import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { adultRequest, useAdultAccountId } from "@/lib/education/adult-client";
import { prioritySchema, type StudyPriority } from "@/lib/education/priority";
import { subjects } from "@/lib/education/schema";
import "./progress.css";

export function PupilPriority({ learnerId }: { learnerId: string }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean }>();
  const [saving, setSaving] = useState(false);
  const account = useAdultAccountId();
  const qc = useQueryClient();
  const url = `/api/education/priority?learnerId=${learnerId}`;
  const queryKey = ["study-priority", account, learnerId];
  const query = useQuery({
    queryKey,
    enabled: open && !!account,
    queryFn: () => adultRequest<StudyPriority>(url),
    retry: false,
  });

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const priority = prioritySchema.parse({
      subject: fields.get("subject") || null,
      goal: fields.get("goal"),
    });
    setSaving(true);
    setMessage(undefined);
    try {
      qc.setQueryData(queryKey, await adultRequest<StudyPriority>(url, priority));
      setMessage({
        text: "Prioridad guardada. Se aplicará a las próximas recomendaciones.",
        error: false,
      });
    } catch (error) {
      setMessage({ text: (error as Error).message, error: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <details
      className="progress-link progress-priority"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>Prioridad de aprendizaje</summary>
      <p>Peluqo usa esta preferencia al elegir qué retos sugerir.</p>
      {query.isError && (
        <p role="alert">
          {query.error.message} <button onClick={() => void query.refetch()}>Reintentar</button>
        </p>
      )}
      {open && query.isPending && <p role="status">Cargando prioridad…</p>}
      {query.data && (
        <form key={learnerId} onSubmit={(e) => void save(e)}>
          <label>
            Asignatura{" "}
            <select name="subject" defaultValue={query.data.subject ?? ""}>
              <option value="">Sin prioridad de asignatura</option>
              {Object.entries(subjects).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Enfoque{" "}
            <select name="goal" defaultValue={query.data.goal}>
              <option value="balanced">Equilibrar práctica y variedad</option>
              <option value="support">Reforzar y practicar paso a paso</option>
              <option value="stretch">Proponer desafíos cuando esté preparado</option>
            </select>
          </label>
          <button disabled={saving}>{saving ? "Guardando…" : "Guardar prioridad"}</button>
        </form>
      )}
      {message && <p role={message.error ? "alert" : "status"}>{message.text}</p>}
    </details>
  );
}
