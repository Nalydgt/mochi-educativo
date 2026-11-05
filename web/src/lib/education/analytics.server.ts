import { createHash } from "node:crypto";
import { z } from "zod";
import { adultAccount, ApiError } from "./adult-auth.server";
import type { AnalyticsData } from "./analytics";
import { db } from "./db.server";
import { studyFormatSchema } from "./schema";

const noStore = { "Cache-Control": "no-store" };
const uuid = z.string().uuid();
const activity = z.string().regex(/^[a-z0-9_-]{1,48}$/);
const telemetry = z
  .object({
    visitId: uuid,
    event: z.enum(["enter", "sample", "leave", "failure"]),
    surface: z.enum(["aventura", "mundos", "preguntas", "peluqo"]),
    sessionId: uuid.nullable(),
    activityId: activity.nullable(),
    format: studyFormatSchema.nullable(),
    active: z.boolean(),
  })
  .strict();
const filters = z.object({
  scope: z.enum(["education", "admin"]).default("education"),
  classId: uuid.optional(),
  learnerId: uuid.optional(),
  versionId: uuid.optional(),
  activityId: activity.optional(),
  subject: z
    .enum(["ciencias", "matematicas", "lengua", "historia", "geografia", "otros", "sin_clasificar"])
    .optional(),
  from: z.string().date(),
  to: z.string().date(),
  zone: z.string().max(70).default("UTC"),
});

function failure(error: unknown, message: string) {
  return Response.json(
    { error: error instanceof ApiError ? error.message : message },
    { headers: noStore, status: error instanceof ApiError ? error.status : 500 },
  );
}

export async function handleTelemetry(request: Request) {
  try {
    const origin = request.headers.get("origin");
    const expected = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
    if (origin && origin !== expected) throw new ApiError(403, "Origen no autorizado.");
    const token = request.headers
      .get("cookie")
      ?.match(/(?:^|;\s*)peluqo_student=([\w-]{40,160})(?=;|$)/)?.[1];
    if (!token) throw new ApiError(401, "Sesión de alumno cerrada.");
    const parsed = telemetry.safeParse(await request.json().catch(() => null));
    if (!parsed.success) throw new ApiError(400, "Evento no válido.");
    const e = parsed.data;
    const hash = createHash("sha256").update(token).digest("hex");
    const [row] = await db()<{ recorded: boolean }[]>`
      SELECT education.record_telemetry(${hash}, ${e.visitId}, ${e.event}, ${e.surface},
        ${e.sessionId}, ${e.activityId}, ${e.active}, ${e.format}) AS recorded
    `;
    if (!row?.recorded) throw new ApiError(409, "El contexto de estudio ha cambiado.");
    return new Response(null, { headers: noStore, status: 204 });
  } catch (error) {
    return failure(error, "El registro de actividad no está disponible.");
  }
}

export async function handleAnalytics(request: Request) {
  try {
    const adult = await adultAccount(request);
    const parsed = filters.safeParse(Object.fromEntries(new URL(request.url).searchParams));
    if (!parsed.success) throw new ApiError(400, "Revisa los filtros y las fechas.");
    const q = parsed.data;
    const days = (Date.parse(q.to) - Date.parse(q.from)) / 86_400_000;
    if (days < 0 || days > 89) throw new ApiError(400, "Elige un intervalo de hasta 90 días.");
    let zone: string;
    try {
      zone = new Intl.DateTimeFormat("es", { timeZone: q.zone }).resolvedOptions().timeZone;
    } catch {
      throw new ApiError(400, "Zona horaria no válida.");
    }
    const [row] = await db()<{ snapshot: AnalyticsData }[]>`
      SELECT education.analytics_snapshot(${adult}, ${q.scope === "admin"}, ${q.classId ?? null},
        ${q.learnerId ?? null}, ${q.versionId ?? null}, ${q.activityId ?? null}, ${q.subject ?? null},
        ${q.from}, ${q.to}, ${zone}) AS snapshot
    `;
    if (!row?.snapshot?.role)
      throw new ApiError(403, "Esta cuenta no tiene acceso a estas métricas.");
    return Response.json(row.snapshot, { headers: noStore });
  } catch (error) {
    return failure(error, "No se pudieron cargar las métricas.");
  }
}
