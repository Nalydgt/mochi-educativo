import { useServerFn } from "@tanstack/react-start";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { Download, RefreshCcw, ShieldCheck, Trash2 } from "lucide-react";
import {
  exportLearningData,
  learningPrivacyState,
  removeLearningData,
  retryLearningCleanup,
} from "@/lib/privacy.functions";
import { useAdultAccountId } from "@/lib/education/adult-client";
import { Button } from "./ui/button";

export function PrivacyAction() {
  const account = useAdultAccountId();
  const remove = useServerFn(removeLearningData);
  const download = useServerFn(exportLearningData);
  const cleanup = useServerFn(retryLearningCleanup);
  const read = useServerFn(learningPrivacyState);
  const client = useQueryClient();
  const requestId = useRef<string | undefined>(undefined);
  const [busy, setBusy] = useState<"remove" | "download" | "cleanup">();
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState<{ text: string; error?: boolean }>();
  const status = useQuery({
    queryKey: ["privacy-files", account],
    queryFn: () => read(),
    enabled: !!account,
    retry: false,
  });

  async function exportSummary() {
    setBusy("download");
    setMessage(undefined);
    try {
      const summary = await download();
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(summary, null, 2)], { type: "application/json;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `peluqo-aprendizaje-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
      setMessage({ text: "Resumen preparado para descargar." });
    } catch (error) {
      setMessage({
        text: error instanceof Error ? error.message : "No se pudo preparar el resumen.",
        error: true,
      });
    } finally {
      setBusy(undefined);
    }
  }

  async function clearData(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (confirmation !== "ELIMINAR") return;
    setBusy("remove");
    setMessage(undefined);
    requestId.current ??= crypto.randomUUID();
    try {
      const result = await remove({
        data: { confirmation: "ELIMINAR", requestId: requestId.current },
      });
      requestId.current = undefined;
      setConfirmation("");
      try {
        localStorage.removeItem("peluqo.student-picker.v1");
      } catch {
        /* Optional browser storage. */
      }
      await client.invalidateQueries();
      setMessage({
        text: result.pendingFiles
          ? "Los datos de aprendizaje están eliminados. Quedan archivos pendientes de limpieza, puedes reintentar abajo."
          : "Datos de aprendizaje y archivos eliminados. Puedes volver a preparar tu espacio.",
      });
    } catch (error) {
      setMessage({
        text: error instanceof Error ? error.message : "No se pudo eliminar. Puedes reintentar.",
        error: true,
      });
    } finally {
      setBusy(undefined);
    }
  }

  async function finishCleanup() {
    setBusy("cleanup");
    setMessage(undefined);
    try {
      const result = await cleanup();
      await status.refetch();
      setMessage({
        text: result.pendingFiles
          ? `Quedan ${result.pendingFiles} archivos por limpiar. Vuelve a intentarlo cuando el almacenamiento esté disponible.`
          : "Limpieza de archivos completada.",
      });
    } catch (error) {
      setMessage({
        text: error instanceof Error ? error.message : "No se pudo completar la limpieza.",
        error: true,
      });
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <section
      id="privacidad"
      className="mt-10 grid gap-4 border-t py-6"
      aria-labelledby="privacy-heading"
    >
      <h2 id="privacy-heading" className="flex items-center gap-2 text-2xl font-bold">
        <ShieldCheck size={23} aria-hidden="true" /> Tus datos de aprendizaje
      </h2>
      <p className="max-w-3xl">
        Descarga un resumen de perfiles, progreso, referencias de documentos y actividad de estudio.
        El archivo se guarda en tu dispositivo.
      </p>
      <Button
        className="w-fit"
        variant="outline"
        disabled={!!busy}
        onClick={() => void exportSummary()}
      >
        <Download size={17} aria-hidden="true" />{" "}
        {busy === "download" ? "Preparando resumen…" : "Descargar resumen de aprendizaje"}
      </Button>
      {status.data && status.data.pendingFiles > 0 && (
        <div className="platform-message">
          <p>Hay {status.data.pendingFiles} archivos pendientes de eliminación.</p>
          <Button variant="outline" disabled={!!busy} onClick={() => void finishCleanup()}>
            <RefreshCcw size={16} aria-hidden="true" />{" "}
            {busy === "cleanup" ? "Limpiando…" : "Reintentar limpieza de archivos"}
          </Button>
        </div>
      )}
      {status.isError && (
        <p role="alert">
          No se pudo consultar la limpieza pendiente.{" "}
          <button type="button" className="underline" onClick={() => void status.refetch()}>
            Volver a comprobar
          </button>
        </p>
      )}
      <details className="rounded-xl border p-4">
        <summary className="cursor-pointer font-semibold">
          Eliminar mis datos de aprendizaje
        </summary>
        <p className="mt-3 max-w-3xl">
          Se eliminarán tus perfiles, cuadernos y documentos personales, y los alumnos, aventuras y
          registros de tu Studio en casa. Se retirarán tus vínculos familiares con aulas escolares.
        </p>
        <p className="mt-2 max-w-3xl">
          Los datos del aula escolar los gestiona su docente. Tu cuenta seguirá disponible.
        </p>
        <form
          className="mt-4 flex max-w-xl flex-wrap items-end gap-3"
          onSubmit={(event) => void clearData(event)}
        >
          <label className="grid gap-1 font-semibold">
            Escribe ELIMINAR para confirmar
            <input
              className="min-h-11 rounded-lg border bg-white px-3 py-2"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              disabled={!!busy}
              required
            />
          </label>
          <Button variant="destructive" disabled={!!busy || confirmation !== "ELIMINAR"}>
            <Trash2 size={17} aria-hidden="true" />{" "}
            {busy === "remove" ? "Eliminando…" : "Eliminar datos"}
          </Button>
        </form>
      </details>
      {message && (
        <p role={message.error ? "alert" : "status"} className="platform-message">
          {message.text}
        </p>
      )}
    </section>
  );
}
