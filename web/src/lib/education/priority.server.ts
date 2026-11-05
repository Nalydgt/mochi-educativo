import { z } from "zod";
import { adultAccount, ApiError } from "./adult-auth.server";
import { db } from "./db.server";
import { prioritySchema, type StudyPriority } from "./priority";

const headers = { "Cache-Control": "no-store" };

export async function handlePriority(request: Request) {
  try {
    const url = new URL(request.url);
    const parsed = z.string().uuid().safeParse(url.searchParams.get("learnerId"));
    if (!parsed.success) throw new ApiError(400, "Selecciona un estudiante.");
    const adult = await adultAccount(request);
    let priority: StudyPriority | undefined;
    if (request.method === "POST") {
      const origin = request.headers.get("origin");
      if (origin && origin !== (process.env["PELUQO_WEB_ORIGIN"] ?? url.origin))
        throw new ApiError(403, "Origen no autorizado.");
      const input = prioritySchema.safeParse(await request.json().catch(() => null));
      if (!input.success) throw new ApiError(400, "Revisa la prioridad de aprendizaje.");
      priority = input.data;
    }
    const [row] = await db()<{ result: StudyPriority | null }[]>`
      SELECT education.manage_study_priority(${adult}, ${parsed.data}, ${priority?.subject ?? null}, ${priority?.goal ?? null}) AS result
    `;
    if (!row?.result) throw new ApiError(404, "Este estudiante no está vinculado a tu cuenta.");
    return Response.json(row.result, { headers });
  } catch (error) {
    return Response.json(
      { error: error instanceof ApiError ? error.message : "No se pudo guardar la prioridad." },
      { headers, status: error instanceof ApiError ? error.status : 500 },
    );
  }
}
