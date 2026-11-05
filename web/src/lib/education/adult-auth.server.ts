import { createClient } from "@supabase/supabase-js";
import { db } from "./db.server";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function adultAccount(request: Request, requiredRole?: "teacher" | "family") {
  const bearer = request.headers.get("authorization");
  if (!bearer?.startsWith("Bearer "))
    throw new ApiError(401, "Inicia sesión con tu cuenta adulta.");
  const url = process.env["SUPABASE_URL"];
  const key = process.env["SUPABASE_PUBLISHABLE_KEY"];
  if (!url || !key) throw new ApiError(503, "El acceso adulto no está disponible.");
  const auth = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await auth.auth.getUser(bearer.slice(7));
  if (error || !data.user) throw new ApiError(401, "Inicia sesión de nuevo.");
  const [account] = await db()<{ role: string | null }[]>`
    SELECT education.adult_role(${data.user.id}::uuid) AS role
  `;
  if (!account?.role || !["teacher", "family"].includes(account.role))
    throw new ApiError(403, "Confirma tu cuenta familiar adulta para abrir el panel.");
  if (requiredRole && account.role !== requiredRole)
    throw new ApiError(
      403,
      requiredRole === "teacher"
        ? "Esta acción requiere una cuenta docente autorizada."
        : "Esta acción requiere una cuenta familiar autorizada.",
    );
  return data.user.id;
}
