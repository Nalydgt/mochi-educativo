import { createHash } from "node:crypto";
import { z } from "zod";
import { adultAccount, ApiError } from "./adult-auth.server";
import { db } from "./db.server";
import { buildProgressDashboard, type ProgressSnapshot } from "./progress";

const headers = { "Cache-Control": "no-store" };
const classId = z.string().uuid();
const familyCode = z.object({ code: z.string().min(8).max(40) });

export async function handleProgress(request: Request) {
  try {
    const adult = await adultAccount(request);
    if (request.method === "POST") {
      const origin = request.headers.get("origin");
      const expected = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
      if (origin && origin !== expected) throw new ApiError(403, "Origen no autorizado.");
      const body = familyCode.safeParse(await request.json().catch(() => null));
      const code = body.success ? body.data.code.replace(/[\s-]/g, "").toUpperCase() : "";
      if (!/^F[A-HJ-NP-Z2-9]{12}$/.test(code))
        throw new ApiError(400, "Introduce el código familiar que empieza por F.");
      const hash = createHash("sha256").update(code).digest("hex");
      const [result] = await db()<
        { allowed: boolean }[]
      >`select education.redeem_family_code(${adult}, ${hash}) as allowed`;
      if (!result?.allowed)
        throw new ApiError(400, "El código ha caducado, ya se usó o requiere una cuenta familiar.");
      return Response.json({ ok: true }, { headers });
    }

    const requested = new URL(request.url).searchParams.get("classId");
    if (requested !== null && !classId.safeParse(requested).success)
      throw new ApiError(400, "Clase no válida.");
    const [row] = await db()<{ snapshot: ProgressSnapshot }[]>`
      select education.progress_snapshot(${adult}, ${requested}::uuid) as snapshot
    `;
    const snapshot = row?.snapshot;
    if (!snapshot?.role)
      throw new ApiError(403, "El seguimiento requiere una cuenta docente o familiar.");
    return Response.json(buildProgressDashboard(snapshot, snapshot.role), { headers });
  } catch (error) {
    return Response.json(
      { error: error instanceof ApiError ? error.message : "No se pudo cargar el seguimiento." },
      { headers, status: error instanceof ApiError ? error.status : 500 },
    );
  }
}
