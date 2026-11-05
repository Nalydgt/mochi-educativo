import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/integrations/supabase/types";
import { buildProgressDashboard, type ProgressSnapshot } from "./progress";
import { db } from "./db.server";

type FileQueue = { pendingFiles: number; files: { id: string; storage_path: string }[] };
type AccountClient = SupabaseClient<Database>;

export async function learningFileQueue(adult: string, completed: string[] = []) {
  const [row] = await db()<{ result: FileQueue | null }[]>`
    SELECT education.learning_file_cleanup(${adult}, ${completed}::uuid[]) AS result
  `;
  if (!row?.result) throw new Error("No se pudo consultar la eliminación pendiente.");
  return row.result;
}

export async function cleanupLearningFiles(adult: string, client: AccountClient) {
  let queue = await learningFileQueue(adult);
  // Bound each request while preserving the remaining work for the next retry.
  for (let batch = 0; batch < 5 && queue.files.length; batch++) {
    const paths = queue.files.map((file) => file.storage_path);
    try {
      const result = await client.storage.from("learner-documents").remove(paths);
      if (result.error) return queue.pendingFiles;
    } catch {
      return queue.pendingFiles;
    }
    queue = await learningFileQueue(
      adult,
      queue.files.map((file) => file.id),
    );
  }
  return queue.pendingFiles;
}

export async function resetLearningData(adult: string, client: AccountClient, requestId: string) {
  const [row] = await db()<
    {
      result: { homeLearners: number; legacyLearners: number; pendingFiles: number } | null;
    }[]
  >`SELECT education.reset_learning_data(${adult}, 'ELIMINAR', ${requestId}) AS result`;
  if (!row?.result) throw new Error("No se pudieron eliminar los datos de aprendizaje.");
  let pendingFiles = row.result.pendingFiles;
  try {
    pendingFiles = await cleanupLearningFiles(adult, client);
  } catch {
    // The reset committed. Its durable queue retains all unacknowledged paths.
  }
  return { ok: true as const, ...row.result, pendingFiles };
}

export async function deleteLegacyStudy(
  adult: string,
  client: AccountClient,
  target: { notebookId: string; documentId?: string },
) {
  const [row] = await db()<{ removed: boolean }[]>`
    SELECT education.remove_legacy_study(${adult}, ${target.notebookId}, ${target.documentId ?? null}) AS removed
  `;
  if (!row?.removed)
    throw new Error("El cuaderno o el documento no está disponible para tu cuenta.");
  const queue = await learningFileQueue(adult);
  let pendingFiles = queue.pendingFiles;
  try {
    pendingFiles = await cleanupLearningFiles(adult, client);
  } catch {
    // Retrying the same deletion or the privacy cleanup will finish the file removal.
  }
  return { ok: true as const, pendingFiles };
}

export async function exportLearningSummary(adult: string) {
  const [row] = await db()<
    { result: ({ progress: ProgressSnapshot } & Record<string, unknown>) | null }[]
  >`
    SELECT education.export_learning_data(${adult}) AS result
  `;
  if (!row?.result) throw new Error("No se pudieron descargar los datos de aprendizaje.");
  const { progress, ...account } = row.result;
  return {
    ...account,
    progress: progress.role ? buildProgressDashboard(progress, progress.role) : null,
  };
}
