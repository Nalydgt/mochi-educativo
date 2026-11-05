import { createClient } from "@supabase/supabase-js";
import { z } from "zod";
import { ApiError } from "./adult-auth.server";
import { db } from "./db.server";

/** Initial adult declaration grants no access to any child, class or grade. */
export async function handleAdultOnboarding(request: Request) {
  const headers = { "Cache-Control": "no-store" };
  try {
    const bearer = request.headers.get("authorization");
    if (!bearer?.startsWith("Bearer ")) throw new ApiError(401, "Inicia sesión para continuar.");
    const url = process.env["SUPABASE_URL"],
      key = process.env["SUPABASE_PUBLISHABLE_KEY"];
    if (!url || !key) throw new ApiError(503, "El acceso adulto no está disponible.");
    const auth = createClient(url, key, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data, error } = await auth.auth.getUser(bearer.slice(7));
    if (error || !data.user) throw new ApiError(401, "Vuelve a iniciar sesión.");
    if (request.method === "POST") {
      const expected = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
      if (request.headers.get("origin") && request.headers.get("origin") !== expected)
        throw new ApiError(403, "Origen no autorizado.");
      if (
        !z
          .object({ confirmAdult: z.literal(true) })
          .strict()
          .safeParse(await request.json().catch(() => null)).success
      )
        throw new ApiError(
          400,
          "Confirma que eres una persona adulta para crear tu espacio familiar.",
        );
      await db()`SELECT education.onboard_family(${data.user.id}::uuid, true)`;
    }
    const [row] = await db()<{ role: "teacher" | "family" | null }[]>`
      SELECT education.adult_role(${data.user.id}::uuid) AS role
    `;
    return Response.json({ role: row?.role ?? null, needsConfirmation: !row?.role }, { headers });
  } catch (error) {
    return Response.json(
      { error: error instanceof ApiError ? error.message : "No se pudo abrir el espacio adulto." },
      { headers, status: error instanceof ApiError ? error.status : 503 },
    );
  }
}
