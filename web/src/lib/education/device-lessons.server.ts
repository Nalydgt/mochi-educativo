import { adultAccount, ApiError } from "./adult-auth.server";
import { db } from "./db.server";
import type { DeviceLessonReport } from "./device-lessons";

export async function handleDeviceLessons(request: Request) {
  const headers = { "Cache-Control": "no-store" };
  try {
    const adult = await adultAccount(request);
    const [row] = await db()<{ snapshot: DeviceLessonReport }[]>`
      SELECT education.device_lesson_snapshot(${adult}::uuid) AS snapshot
    `;
    if (!row?.snapshot?.role)
      throw new ApiError(403, "Este espacio requiere una cuenta docente o familiar adulta.");
    return Response.json(row.snapshot, { headers });
  } catch (error) {
    return Response.json(
      {
        error:
          error instanceof ApiError ? error.message : "No se pudieron cargar los deberes de Mochi.",
      },
      { headers, status: error instanceof ApiError ? error.status : 503 },
    );
  }
}
