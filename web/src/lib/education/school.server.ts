import { adultAccount, ApiError } from "./adult-auth.server";
import { db } from "./db.server";
import { InferenceUnavailable, queueInference } from "./inference.server";
import {
  schoolCommandSchema,
  suggestedAssignmentSchema,
  type SchoolSnapshot,
} from "./school-schema";

const headers = { "Cache-Control": "no-store" };

function databaseFailure(error: unknown) {
  const code = error && typeof error === "object" && "code" in error ? String(error.code) : "";
  if (code === "42501") return new ApiError(403, "Tu cuenta no tiene permiso para esta acción.");
  if (code === "P0002") return new ApiError(404, "No disponible o no vinculado a tu cuenta.");
  if (["23505", "40001"].includes(code))
    return new ApiError(
      409,
      "Los datos cambiaron o la petición ya se usó. Recarga el panel y vuelve a intentarlo.",
    );
  if (["22023", "22P02", "22007", "22008", "23514", "23502"].includes(code))
    return new ApiError(400, "Revisa los datos del formulario.");
  if (code === "54000")
    return new ApiError(429, "Has alcanzado el límite de solicitudes. Prueba más tarde.");
  return new ApiError(
    503,
    "El servicio escolar no está disponible. Tus cambios no se han confirmado.",
  );
}

export async function handleSchool(request: Request): Promise<Response> {
  try {
    if (request.method !== "GET" && request.method !== "POST")
      return Response.json(
        { error: "Método no permitido." },
        { status: 405, headers: { ...headers, Allow: "GET, POST" } },
      );
    const adult = await adultAccount(request);
    if (request.method === "GET") {
      const [row] = await db()<{ snapshot: SchoolSnapshot | null }[]>`
        SELECT education.school_read(${adult}::uuid) AS snapshot
      `;
      if (!row?.snapshot?.role)
        throw new ApiError(403, "Este panel requiere una cuenta adulta autorizada.");
      return Response.json(row.snapshot, { headers });
    }
    const origin = request.headers.get("origin");
    const expected = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
    if (origin && origin !== expected) throw new ApiError(403, "Origen no autorizado.");
    const raw = await request.text();
    if (raw.length > 64_000) throw new ApiError(413, "El formulario es demasiado grande.");
    let body: unknown;
    try {
      body = JSON.parse(raw);
    } catch {
      throw new ApiError(400, "El formulario no es válido.");
    }
    const parsed = schoolCommandSchema.safeParse(body);
    if (!parsed.success)
      throw new ApiError(
        400,
        parsed.error.issues[0]?.message ?? "Revisa los datos del formulario.",
      );
    const command = parsed.data;
    if (command.action === "suggest-assignment") {
      const [context] = await db()<
        { context: { sources: { id: string; page: number | null; content: string }[] } }[]
      >`
        SELECT education.school_proposal_context(${adult}::uuid,${command.classId}::uuid,${command.requestId}::uuid) AS context
      `;
      const result = await queueInference(
        "/proposal",
        {
          topic: command.topic,
          count: command.count,
          sources: context?.context.sources ?? [],
        },
        { classId: command.classId },
      );
      const suggestion = suggestedAssignmentSchema.safeParse(result);
      if (!suggestion.success)
        throw new ApiError(
          502,
          "La IA no produjo una actividad válida. Revisa el tema o crea los ejercicios manualmente.",
        );
      return Response.json(suggestion.data, { headers });
    }
    // Cast through text explicitly: postgres.js must not JSON-encode an already encoded JSON string.
    const [row] = await db()<{ result: unknown }[]>`
      SELECT education.school_command(${adult}::uuid,${JSON.stringify(command)}::text::jsonb) AS result
    `;
    if (!row?.result)
      throw new ApiError(
        503,
        "No se ha confirmado el cambio. Recarga el panel antes de repetirlo.",
      );
    return Response.json(row.result, { headers });
  } catch (error) {
    const failure =
      error instanceof ApiError
        ? error
        : error instanceof InferenceUnavailable
          ? new ApiError(
              503,
              "La propuesta de IA no está disponible ahora. Puedes crear una actividad manualmente; no se ha publicado nada.",
            )
          : databaseFailure(error);
    return Response.json({ error: failure.message }, { status: failure.status, headers });
  }
}
