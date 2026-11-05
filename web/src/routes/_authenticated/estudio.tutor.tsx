import { redirect as redirectToAdultWorkspace } from "@tanstack/react-router";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ArrowLeft, BookOpen } from "lucide-react";
import { studyData } from "@/lib/study.functions";
import { supabase } from "@/integrations/supabase/client";
import { EmptyState, Field, PageTitle, Section, meta } from "@/components/Layout";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_authenticated/estudio/tutor")({
  beforeLoad: () => {
    throw redirectToAdultWorkspace({ to: "/", search: { panel: "materials" } });
  },
  validateSearch: (search: Record<string, unknown>) => ({
    cuaderno: typeof search["cuaderno"] === "string" ? search["cuaderno"] : "",
  }),
  head: () =>
    meta("Tutor Peluqo", "Estudia tus documentos y comprueba las fuentes de cada respuesta."),
  component: Tutor,
});

type Source = { id: number; file: string; page: number | null; fragment: string };

function SourceNotes({ sources }: { sources: Source[] }) {
  return sources.map((source, index) => (
    <details className="platform-source" key={`${source.id}:${index}`}>
      <summary>
        <BookOpen size={15} aria-hidden="true" /> [{source.id}] {source.file}
        {source.page ? ` · Página ${source.page}` : ""}
      </summary>
      <p>{source.fragment}</p>
    </details>
  ));
}

function Tutor() {
  const { cuaderno } = Route.useSearch();
  const read = useServerFn(studyData);
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["study"], queryFn: () => read() });
  const [selected, setSelected] = useState(cuaderno);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [questionDraft, setQuestionDraft] = useState("");
  const [notice, setNotice] = useState<{ text: string; error: boolean }>();
  const [sources, setSources] = useState<Source[]>([]);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !consent || busy) return;
    const form = event.currentTarget;
    const question = String(new FormData(form).get("question") ?? "").trim();
    if (!question) return;
    setBusy(true);
    setQuestionDraft(question);
    setDraft("");
    setSources([]);
    setNotice(undefined);
    const controller = new AbortController();
    abort.current = controller;
    try {
      const session = (await supabase.auth.getSession()).data.session;
      if (!session) throw new Error("Inicia sesión.");
      const response = await fetch("/api/tutor", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ notebook: selected, question, consent }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error ?? "El tutor no está disponible.");
      }
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No se recibió una respuesta.");
      const decoder = new TextDecoder();
      let pending = "";
      function handleLine(line: string) {
        if (!line) return;
        const message = JSON.parse(line);
        if (message.type === "sources") setSources(message.sources);
        if (message.type === "text") setDraft((value) => value + message.text);
        if (message.type === "error") throw new Error(message.message);
      }
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const lines = (pending + decoder.decode(value, { stream: true })).split("\n");
          pending = lines.pop() ?? "";
          lines.forEach(handleLine);
        }
        handleLine(pending + decoder.decode());
      } finally {
        await reader.cancel().catch(() => {});
      }
      await client.invalidateQueries({ queryKey: ["study"] });
      setQuestionDraft("");
      setDraft("");
      setSources([]);
      form.reset();
      setNotice({ text: "Respuesta guardada.", error: false });
    } catch (error) {
      const cancelled = error instanceof Error && error.name === "AbortError";
      setQuestionDraft("");
      setDraft("");
      setNotice({
        text: cancelled
          ? "Solicitud detenida."
          : error instanceof Error
            ? error.message
            : "No se pudo responder.",
        error: !cancelled,
      });
    } finally {
      setBusy(false);
      abort.current = null;
    }
  }

  return (
    <>
      <Section tone="sky">
        <Link className="platform-route-action mb-4" to="/estudio">
          <ArrowLeft size={17} aria-hidden="true" /> Mis cuadernos
        </Link>
        <PageTitle
          kicker="Estudio"
          title="Tutor Peluqo"
          sub="Haz una pregunta sobre tus apuntes y abre las fuentes para comprobar la respuesta."
          art="taller"
        />
      </Section>
      <Section>
        {query.error && (
          <p className="platform-message mb-4" role="alert">
            {query.error.message}
          </p>
        )}
        {query.isPending && <p role="status">Cargando tus cuadernos…</p>}
        {!query.isPending && !query.error && query.data?.notebooks.length === 0 ? (
          <EmptyState
            title="El tutor necesita un cuaderno"
            action={
              <Link className="btn btn-primary" to="/estudio">
                Crear un cuaderno
              </Link>
            }
          >
            Sube un PDF digital o un TXT con el material que quieras repasar.
          </EmptyState>
        ) : (
          <div className="platform-conversation">
            <label className="platform-field max-w-md">
              <span className="label">Cuaderno</span>
              <select
                className="platform-input"
                disabled={busy}
                value={selected}
                onChange={(event) => {
                  setSelected(event.target.value);
                  setConsent(false);
                  setDraft("");
                  setSources([]);
                  setNotice(undefined);
                }}
              >
                <option value="">Elige un cuaderno</option>
                {query.data?.notebooks.map((notebook) => (
                  <option key={notebook.id} value={notebook.id}>
                    {notebook.title}
                  </option>
                ))}
              </select>
            </label>
            <div className="platform-messages" aria-label="Conversación">
              {query.data?.messages
                .filter((message) => message.notebook_id === selected)
                .map((message) => (
                  <article key={message.id} className="platform-bubble" data-from={message.role}>
                    <h2>{message.role === "user" ? "Tú" : "Peluqo"}</h2>
                    <p>{message.content}</p>
                    {Array.isArray(message.source_references) && (
                      <SourceNotes sources={message.source_references as unknown as Source[]} />
                    )}
                  </article>
                ))}
              {busy && (
                <>
                  <article className="platform-bubble" data-from="user">
                    <h2>Tú</h2>
                    <p>{questionDraft}</p>
                  </article>
                  <article className="platform-bubble" data-from="assistant" aria-busy="true">
                    <h2>Peluqo</h2>
                    <p>{draft || "Consultando tus apuntes…"}</p>
                    <SourceNotes
                      sources={sources.filter((source) => draft.includes(`[${source.id}]`))}
                    />
                  </article>
                </>
              )}
            </div>
            <form className="space-y-3" onSubmit={ask}>
              <Field
                label="Tu pregunta"
                name="question"
                required
                maxLength={2000}
                readOnly={busy}
              />
              <label className="flex items-start gap-2 text-sm">
                <input
                  className="mt-1"
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => setConsent(event.target.checked)}
                />
                Autorizo a Peluqo a compartir fragmentos de este cuaderno con Lovable AI para
                responder.
              </label>
              <p className="text-sm text-muted-foreground">
                Los archivos permanecen privados y sus fragmentos no se usan para entrenar modelos.
                Puedes hacer 20 preguntas al día por cuenta.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button disabled={busy || !consent || !selected}>
                  {busy ? "Consultando…" : "Preguntar"}
                </Button>
                {busy && (
                  <Button variant="outline" type="button" onClick={() => abort.current?.abort()}>
                    Detener respuesta
                  </Button>
                )}
              </div>
              {notice && (
                <p className="platform-message" role={notice.error ? "alert" : "status"}>
                  {notice.text}
                </p>
              )}
            </form>
          </div>
        )}
      </Section>
    </>
  );
}
