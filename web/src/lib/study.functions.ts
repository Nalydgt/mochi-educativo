import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

export const studyData = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const [notebooks, documents, messages] = await Promise.all([
      context.supabase.from("notebooks").select("*").order("created_at", { ascending: false }),
      context.supabase.from("notebook_documents").select("*"),
      context.supabase.from("ai_messages").select("*").order("created_at"),
    ]);
    if (notebooks.error || documents.error || messages.error)
      throw new Error("No se pudieron cargar tus cuadernos.");
    return { notebooks: notebooks.data, documents: documents.data, messages: messages.data };
  });

export const createNotebook = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(
    z.object({
      learner: z.string().uuid(),
      title: z.string().trim().min(1).max(120),
      description: z.string().max(1000),
    }),
  )
  .handler(async ({ data, context }) => {
    const result = await context.supabase
      .from("notebooks")
      .insert({
        owner_user_id: context.userId,
        learner_id: data.learner,
        title: data.title,
        description: data.description,
      })
      .select()
      .single();
    if (result.error) throw new Error("No se pudo crear el cuaderno.");
    return result.data;
  });

const processedDocument = z.object({
  ok: z.boolean(),
  id: z.string().uuid(),
  error: z.string().nullable(),
});

export const processDocument = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(
    z.object({
      notebook: z.string().uuid(),
      path: z.string().min(1).max(512),
      name: z.string().min(1).max(150),
    }),
  )
  .handler(async ({ data, context }) => {
    const own = await context.supabase
      .from("notebooks")
      .select("id")
      .eq("id", data.notebook)
      .eq("owner_user_id", context.userId)
      .maybeSingle();
    if (
      own.error ||
      !own.data ||
      !data.path.startsWith(context.userId + "/" + data.notebook + "/")
    ) {
      throw new Error("Documento no autorizado.");
    }
    const extension = /\.(pdf|txt)$/i.exec(data.name)?.[1]?.toLowerCase();
    if (
      (extension !== "pdf" && extension !== "txt") ||
      !data.path.toLowerCase().endsWith("." + extension)
    ) {
      throw new Error("Puedes subir un PDF digital o un TXT.");
    }
    const downloaded = await context.supabase.storage.from("learner-documents").download(data.path);
    if (downloaded.error) throw new Error("No se pudo leer el archivo. Vuelve a subirlo.");
    const { NotebookDocumentError, extractNotebookDocument } =
      await import("./notebook-document.server");
    let chunks: Awaited<ReturnType<typeof extractNotebookDocument>> = [];
    let error: string | null = null;
    try {
      chunks = await extractNotebookDocument(downloaded.data, extension);
    } catch (failure) {
      error =
        failure instanceof NotebookDocumentError
          ? failure.message
          : "No se pudo extraer el texto. Comprueba que el PDF sea digital.";
    }
    const saved = await context.supabase.rpc("finalize_notebook_document", {
      p_notebook: data.notebook,
      p_path: data.path,
      p_name: data.name,
      p_size: downloaded.data.size,
      p_mime: extension === "pdf" ? "application/pdf" : "text/plain",
      p_chunks: chunks,
      p_error: error,
    });
    if (saved.error) throw new Error("No se pudo guardar el documento. Inténtalo de nuevo.");
    return processedDocument.parse(saved.data);
  });

export const deleteDocument = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(z.object({ id: z.string().uuid() }))
  .handler(async ({ data, context }) => {
    const document = await context.supabase
      .from("notebook_documents")
      .select("id,notebook_id")
      .eq("id", data.id)
      .maybeSingle();
    if (document.error) throw new Error("No se pudo consultar el documento.");
    if (!document.data) return { ok: true, pendingFiles: 0 };
    const { deleteLegacyStudy } = await import("./education/privacy.server");
    return deleteLegacyStudy(context.userId, context.supabase, {
      notebookId: document.data.notebook_id,
      documentId: document.data.id,
    });
  });

export const deleteNotebook = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(z.object({ id: z.string().uuid() }))
  .handler(async ({ data, context }) => {
    const { deleteLegacyStudy } = await import("./education/privacy.server");
    return deleteLegacyStudy(context.userId, context.supabase, { notebookId: data.id });
  });

export const documentText = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .inputValidator(z.object({ id: z.string().uuid() }))
  .handler(async ({ data, context }) => {
    const result = await context.supabase
      .from("document_chunks")
      .select("content,page_number")
      .eq("document_id", data.id)
      .order("chunk_index");
    if (result.error) throw new Error("No se pudo leer el documento.");
    return result.data;
  });
