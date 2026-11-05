import { adultAccount, ApiError } from "./adult-auth.server";
import { db } from "./db.server";

const headers = { "Cache-Control": "no-store" };

export async function resolveHomeStudio(adult: string) {
  const [row] = await db()<{ owner: string | null }[]>`
    SELECT education.resolve_home_studio(${adult}) AS owner
  `;
  if (!row?.owner) throw new ApiError(404, "Activa tu Studio desde el panel familiar.");
  return row.owner;
}

export async function activateHomeStudio(request: Request) {
  try {
    const origin = request.headers.get("origin");
    const expected = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
    if (origin && origin !== expected) throw new ApiError(403, "Origen no autorizado.");
    const adult = await adultAccount(request);
    const [row] = await db()<{ enabled: boolean }[]>`
      SELECT education.enable_home_studio(${adult}) AS enabled
    `;
    if (!row?.enabled)
      throw new ApiError(403, "El Studio en casa requiere una cuenta familiar adulta.");
    return Response.json({ ok: true }, { headers });
  } catch (error) {
    return Response.json(
      { error: error instanceof ApiError ? error.message : "No se pudo abrir tu Studio en casa." },
      { headers, status: error instanceof ApiError ? error.status : 503 },
    );
  }
}
