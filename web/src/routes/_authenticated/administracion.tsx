import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { adminData, saveContent } from "@/lib/admin.functions";
import { LearningAnalytics } from "@/components/education/LearningAnalytics";
import { Section, PageTitle, meta } from "@/components/Layout";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_authenticated/administracion")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "overview" } });
  },
  head: () =>
    meta("Administración", "Gestiona el contenido y consulta la actividad educativa de Peluqo."),
  component: Admin,
});

const examples = {
  subject: {
    name: "",
    slug: "",
    description: "",
    color: "sunburst",
    display_order: 1,
    is_active: true,
  },
  topic: { title: "", slug: "", subject_id: "", description: "", display_order: 1 },
  lesson: {
    title: "",
    slug: "",
    topic_id: "",
    description: "",
    education_level: "Primaria",
    estimated_minutes: 10,
    status: "draft",
    content: { version: 1, intro: "", goal: "", hints: [] },
  },
  activity: {
    lesson_id: "",
    title: "",
    activity_type: "multiple_choice",
    instructions: "",
    public_config: { options: ["Opción A", "Opción B"] },
    points: 10,
    display_order: 1,
    answer_config: { option: 0 },
    explanation: "",
  },
};
const groups = [
  { key: "subjects", kind: "subject", label: "Asignaturas" },
  { key: "topics", kind: "topic", label: "Temas" },
  { key: "lessons", kind: "lesson", label: "Lecciones" },
  { key: "activities", kind: "activity", label: "Actividades" },
] as const;
const labels = { subject: "asignatura", topic: "tema", lesson: "lección", activity: "actividad" };

function Admin() {
  const read = useServerFn(adminData);
  const save = useServerFn(saveContent);
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin"], queryFn: () => read(), retry: false });
  const [kind, setKind] = useState<keyof typeof examples>("lesson");
  const [id, setId] = useState<string>();
  const [content, setContent] = useState(JSON.stringify(examples.lesson, null, 2));
  const [notice, setNotice] = useState<{ text: string; error?: boolean }>();
  const [busy, setBusy] = useState(false);

  return (
    <>
      <Section tone="sky">
        <PageTitle
          kicker="Gestión de Peluqo"
          title="Administración"
          sub="Consulta las métricas de uso y gestiona el catálogo de lecciones."
        />
        {query.isSuccess && (
          <Link className="btn mt-4" to="/admin-tienda">
            Precios y stock
          </Link>
        )}
      </Section>
      <Section>
        {query.error ? (
          <p className="platform-message" role="alert">
            {query.error.message}
          </p>
        ) : query.isSuccess ? (
          <>
            <LearningAnalytics admin />
            <div className="mt-8">
              <h2 className="mb-4 text-2xl font-bold">Catálogo educativo</h2>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {groups.map(({ key, kind: itemKind, label }) => (
                  <details className="card" key={key}>
                    <summary className="cursor-pointer font-bold">
                      {label} · {query.data[key].length}
                    </summary>
                    <ul className="mt-3 grid gap-2">
                      {query.data[key].map((item) => (
                        <li key={item.id}>
                          <Button
                            variant="outline"
                            aria-pressed={id === item.id}
                            className="platform-feedback-option w-full justify-start"
                            onClick={() => {
                              setKind(itemKind);
                              setId(item.id);
                              setContent(JSON.stringify(item, null, 2));
                              setNotice(undefined);
                            }}
                          >
                            {"name" in item ? item.name : item.title}
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </details>
                ))}
              </div>
            </div>
            <div className="platform-settings">
              <div>
                <h2 className="text-2xl font-bold">Editor de contenido</h2>
                <div className="mt-4 flex flex-wrap gap-2">
                  {groups.map(({ kind: type }) => (
                    <Button
                      key={type}
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setKind(type);
                        setId(undefined);
                        setContent(JSON.stringify(examples[type], null, 2));
                        setNotice(undefined);
                      }}
                    >
                      Crear {labels[type]}
                    </Button>
                  ))}
                </div>
              </div>
              <form
                className="space-y-3"
                aria-busy={busy}
                onSubmit={async (event) => {
                  event.preventDefault();
                  setBusy(true);
                  setNotice(undefined);
                  try {
                    await save({
                      data: { kind, ...(id ? { id } : {}), body: JSON.parse(content) },
                    });
                    await client.invalidateQueries({ queryKey: ["admin"] });
                    setNotice({ text: "Contenido guardado." });
                  } catch (error) {
                    setNotice({
                      text: error instanceof Error ? error.message : "No se pudo guardar.",
                      error: true,
                    });
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label className="platform-field">
                  <span className="label">Contenido de {labels[kind]}</span>
                  <textarea
                    className="platform-input min-h-80 font-mono text-sm"
                    value={content}
                    onChange={(event) => setContent(event.target.value)}
                  />
                </label>
                <Button disabled={busy}>{busy ? "Guardando…" : `Guardar ${labels[kind]}`}</Button>
                {notice && (
                  <p className="platform-message" role={notice.error ? "alert" : "status"}>
                    {notice.text}
                  </p>
                )}
              </form>
            </div>
          </>
        ) : (
          <p role="status">Cargando administración…</p>
        )}
      </Section>
    </>
  );
}
