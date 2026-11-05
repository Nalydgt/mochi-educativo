import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Link } from "@tanstack/react-router";
import { ArrowRight, BookOpen, FileText, Plus, Upload } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import {
  studyData,
  createNotebook,
  processDocument,
  deleteDocument,
  deleteNotebook,
  documentText,
} from "@/lib/study.functions";
import { accountData, saveLearner, selectLearner } from "@/lib/learning.functions";
import { EmptyState, Field, PageTitle, Section, Tag } from "./Layout";
import { Button } from "./ui/button";

const subjects = ["Matemáticas", "Ciencias", "Lengua", "Apuntes libres"];

export function StudyPanel() {
  const client = useQueryClient();
  const read = useServerFn(studyData);
  const getAccount = useServerFn(accountData);
  const create = useServerFn(createNotebook);
  const process = useServerFn(processDocument);
  const remove = useServerFn(deleteDocument);
  const removeNotebook = useServerFn(deleteNotebook);
  const view = useServerFn(documentText);
  const addLearner = useServerFn(saveLearner);
  const pick = useServerFn(selectLearner);
  const query = useQuery({ queryKey: ["study"], queryFn: () => read() });
  const account = useQuery({ queryKey: ["account"], queryFn: () => getAccount() });
  const activeId = account.data?.profile?.active_learner_id ?? account.data?.learners[0]?.id;
  const notebooks =
    query.data?.notebooks.filter((notebook) => notebook.learner_id === activeId) ?? [];
  const [notice, setNotice] = useState<{ text: string; error?: boolean }>();
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState<string>();
  const [viewing, setViewing] = useState<{ id: string; text: string }>();
  const [pendingFiles, setPendingFiles] = useState(0);
  const refresh = () => client.invalidateQueries({ queryKey: ["study"] });
  const fail = (error: unknown, fallback: string) =>
    setNotice({ text: error instanceof Error ? error.message : fallback, error: true });

  async function createNamed(title: string) {
    setCreating(true);
    setNotice(undefined);
    try {
      let learnerId = activeId;
      if (!learnerId) {
        const learner = await addLearner({
          data: {
            display_name: account.data?.profile?.display_name || "Mi perfil",
            education_level: "Primaria",
            grade_level: "",
            age_band: "18+",
            color: "sunburst",
            ia: false,
          },
        });
        learnerId = learner.id;
        await pick({ data: { id: learnerId } });
        await client.invalidateQueries({ queryKey: ["account"] });
      }
      await create({ data: { learner: learnerId, title, description: "" } });
      await refresh();
      setNotice({ text: `Cuaderno «${title}» creado.` });
      return true;
    } catch (error) {
      fail(error, "No se pudo crear el cuaderno.");
      return false;
    } finally {
      setCreating(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const title = String(new FormData(form).get("title") ?? "").trim();
    if (title && (await createNamed(title))) form.reset();
  }

  async function upload(file: File, notebook: string) {
    setUploading(notebook);
    setNotice(undefined);
    try {
      if (!file.size || file.size > 10485760)
        throw new Error("El archivo debe tener entre 1 byte y 10 MB.");
      const extension = /\.(pdf|txt)$/i.exec(file.name)?.[1]?.toLowerCase();
      if (!extension) throw new Error("Puedes subir un PDF digital o un TXT.");
      const user = (await supabase.auth.getUser()).data.user;
      if (!user) throw new Error("Inicia sesión.");
      const path = `${user.id}/${notebook}/${crypto.randomUUID()}.${extension}`;
      const result = await supabase.storage.from("learner-documents").upload(path, file);
      if (result.error) throw result.error;
      const document = await process({ data: { notebook, path, name: file.name } });
      await refresh();
      setNotice({
        text: document.ok
          ? "Documento guardado y procesado."
          : (document.error ?? "No se pudo procesar el documento."),
        error: !document.ok,
      });
    } catch (error) {
      fail(error, "No se pudo subir el documento.");
    } finally {
      setUploading(undefined);
    }
  }

  return (
    <>
      <Section tone="sky">
        <PageTitle
          kicker="Estudio"
          title="Tus cuadernos"
          sub="Reúne tus apuntes y consulta sus fuentes cuando estudies."
          art="taller"
        />
      </Section>
      <Section>
        <div className="platform-notebook-tools">
          <form className="flex flex-wrap items-end gap-3" aria-busy={creating} onSubmit={submit}>
            <div className="min-w-40 flex-1">
              <Field label="Nombre del nuevo cuaderno" name="title" required maxLength={120} />
            </div>
            <Button disabled={creating || account.isPending || !!account.error}>
              <Plus aria-hidden="true" />
              {creating ? "Creando…" : "Crear cuaderno"}
            </Button>
          </form>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Empezar con</span>
            {subjects.map((title) => (
              <Button
                key={title}
                type="button"
                size="sm"
                variant="outline"
                disabled={creating || account.isPending || !!account.error}
                onClick={() => void createNamed(title)}
              >
                {title}
              </Button>
            ))}
          </div>
        </div>
        {pendingFiles > 0 && (
          <p className="platform-message my-4" role="status">
            Queda por completar la eliminación de {pendingFiles}{" "}
            {pendingFiles === 1 ? "archivo" : "archivos"}.{" "}
            <Link className="platform-route-action" to="/familia" hash="privacidad">
              Reintentar desde Privacidad
            </Link>
          </p>
        )}
        {notice && (
          <p className="platform-message my-4" role={notice.error ? "alert" : "status"}>
            {notice.text}
          </p>
        )}
        {query.error || account.error ? (
          <p className="platform-message mt-4" role="alert">
            {query.error?.message ?? account.error?.message}
          </p>
        ) : query.isPending || account.isPending ? (
          <p className="mt-5" role="status">
            Cargando tus cuadernos…
          </p>
        ) : (
          <div className="mt-7 space-y-4">
            <h2 className="text-2xl font-bold">Mis cuadernos</h2>
            {notebooks.length === 0 && (
              <EmptyState title="Tu biblioteca empieza con un cuaderno">
                Crea un cuaderno para un tema y añade los PDF digitales o archivos de texto que
                quieras estudiar.
              </EmptyState>
            )}
            {notebooks.map((notebook) => (
              <article className="card" key={notebook.id}>
                <h3 className="platform-icon-title [overflow-wrap:anywhere]">
                  <BookOpen size={22} aria-hidden="true" /> {notebook.title}
                </h3>
                {notebook.description && (
                  <p className="mt-2 text-muted-foreground">{notebook.description}</p>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Link
                    className="btn btn-primary"
                    to="/estudio/tutor"
                    search={{ cuaderno: notebook.id }}
                  >
                    Preguntar al tutor <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                  <label className="btn platform-upload">
                    <Upload size={16} aria-hidden="true" />{" "}
                    {uploading === notebook.id ? "Procesando…" : "Subir PDF o TXT"}
                    <input
                      aria-label={`Subir documento a ${notebook.title}`}
                      className="sr-only"
                      type="file"
                      accept=".pdf,.txt"
                      disabled={!!uploading}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        event.target.value = "";
                        if (file) void upload(file, notebook.id);
                      }}
                    />
                  </label>
                  <Button
                    variant="ghost"
                    onClick={async () => {
                      if (!window.confirm("¿Eliminar el cuaderno y sus documentos?")) return;
                      try {
                        const removed = await removeNotebook({ data: { id: notebook.id } });
                        setPendingFiles(removed.pendingFiles);
                        await refresh();
                        setNotice({ text: "Cuaderno eliminado." });
                      } catch (error) {
                        fail(error, "No se pudo borrar el cuaderno.");
                      }
                    }}
                  >
                    Eliminar cuaderno
                  </Button>
                </div>
                <ul className="platform-notebook-files mt-4">
                  {query.data?.documents
                    .filter((document) => document.notebook_id === notebook.id)
                    .map((document) => (
                      <li key={document.id}>
                        <div className="flex flex-wrap items-center gap-2 [overflow-wrap:anywhere]">
                          <FileText size={17} aria-hidden="true" />
                          <strong>{document.file_name}</strong>
                          <Tag
                            color={
                              document.processing_status === "ready"
                                ? "bg-mint"
                                : document.processing_status === "error"
                                  ? "bg-ember"
                                  : "bg-sunburst"
                            }
                          >
                            {document.processing_status === "ready"
                              ? "Listo"
                              : document.processing_status === "error"
                                ? "Error de procesamiento"
                                : "Pendiente"}
                          </Tag>
                        </div>
                        {document.processing_error && (
                          <p className="platform-message mt-2" role="alert">
                            {document.processing_error}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={document.processing_status !== "ready"}
                            onClick={async () => {
                              if (viewing?.id === document.id) {
                                setViewing(undefined);
                                return;
                              }
                              try {
                                const chunks = await view({ data: { id: document.id } });
                                setViewing({
                                  id: document.id,
                                  text: chunks
                                    .map(
                                      (chunk) =>
                                        (chunk.page_number ? `Página ${chunk.page_number}\n` : "") +
                                        chunk.content,
                                    )
                                    .join("\n\n"),
                                });
                              } catch (error) {
                                fail(error, "No se pudo abrir el texto del documento.");
                              }
                            }}
                          >
                            {viewing?.id === document.id ? "Cerrar texto" : "Ver texto"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={async () => {
                              try {
                                const removed = await remove({ data: { id: document.id } });
                                setPendingFiles(removed.pendingFiles);
                                if (viewing?.id === document.id) setViewing(undefined);
                                await refresh();
                                setNotice({ text: "Documento eliminado." });
                              } catch (error) {
                                fail(error, "No se pudo eliminar el documento.");
                              }
                            }}
                          >
                            Eliminar documento
                          </Button>
                        </div>
                        {viewing?.id === document.id && (
                          <pre className="platform-document mt-3">
                            {viewing.text || "El documento no contiene texto extraído."}
                          </pre>
                        )}
                      </li>
                    ))}
                </ul>
              </article>
            ))}
          </div>
        )}
      </Section>
    </>
  );
}
