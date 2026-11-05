const allowedOrigin = "https://peluqo-mundos.vercel.app";
const cors = {
  "Access-Control-Allow-Origin": allowedOrigin,
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Cache-Control": "no-store",
  Vary: "Origin",
};

function reply(status: number, error: string) {
  return Response.json({ error }, { status, headers: cors });
}

type SignupCredentials = {
  email: string;
  password: string;
  invitation: string;
  action?: "register" | "activate";
};

function hasCredentials(value: unknown): value is SignupCredentials & Record<string, unknown> {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return (
    typeof data.email === "string" &&
    data.email.length <= 254 &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email) &&
    typeof data.password === "string" &&
    data.password.length >= 1 &&
    new TextEncoder().encode(data.password).length <= 72 &&
    typeof data.invitation === "string" &&
    /^[A-Z2-7]{24}$/.test(data.invitation) &&
    (data.action === undefined || data.action === "register" || data.action === "activate")
  );
}

function hasProfile(data: SignupCredentials & Record<string, unknown>): data is SignupCredentials &
  Record<string, unknown> & {
    display_name: string;
    account_type: "family" | "teacher";
    age_band: "18+";
  } {
  return (
    data.password.length >= 8 &&
    typeof data.display_name === "string" &&
    data.display_name.trim().length >= 1 &&
    data.display_name.length <= 60 &&
    (data.account_type === "family" || data.account_type === "teacher") &&
    data.age_band === "18+"
  );
}

async function activateExisting(
  url: string,
  headers: HeadersInit,
  data: SignupCredentials,
  hash: string,
) {
  const key = Deno.env.get("SUPABASE_ANON_KEY");
  if (!key) return reply(503, "El acceso no está disponible ahora.");
  // GoTrue reports email_not_confirmed only after verifying the password.
  const proof = await fetch(url + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: { apikey: key, "Content-Type": "application/json" },
    body: JSON.stringify({ email: data.email, password: data.password }),
  });
  if (proof.ok) {
    const signed = await proof.json().catch(() => null);
    if (signed?.user?.user_metadata?.age_band !== "18+")
      return reply(400, "El acceso escolar requiere una cuenta adulta de 18 años o más.");
    return Response.json({ ok: true }, { headers: cors });
  }
  const failure = await proof.json().catch(() => ({}));
  if ((failure.error_code ?? failure.code) !== "email_not_confirmed")
    return reply(401, "Revisa tu correo y tu contraseña.");

  const pending = await fetch(url + "/rest/v1/rpc/peluqo_pending_account_id", {
    method: "POST",
    headers,
    body: JSON.stringify({ p_email: data.email }),
  });
  if (!pending.ok) return reply(503, "El acceso no está disponible ahora.");
  const userId: unknown = await pending.json();
  if (typeof userId !== "string") return reply(401, "Vuelve a iniciar sesión.");
  const existing = await fetch(url + "/auth/v1/admin/users/" + encodeURIComponent(userId), {
    headers,
  });
  if (!existing.ok) return reply(503, "El acceso no está disponible ahora.");
  const record = await existing.json().catch(() => null);
  const user = record?.user ?? record;
  if (user?.id !== userId || user?.user_metadata?.age_band !== "18+")
    return reply(400, "El acceso escolar requiere una cuenta adulta de 18 años o más.");
  const priorMetadata =
    user.app_metadata && typeof user.app_metadata === "object" && !Array.isArray(user.app_metadata)
      ? user.app_metadata
      : {};
  // Only existing server-owned app metadata can preserve a teacher role.
  // User-editable metadata or a role sent in this request never promotes a teacher.
  const adultRole = priorMetadata.mochi_adult_role === "teacher" ? "teacher" : "family";
  const confirmed = await fetch(url + "/auth/v1/admin/users/" + encodeURIComponent(userId), {
    method: "PUT",
    headers,
    body: JSON.stringify({
      email_confirm: true,
      app_metadata: {
        ...priorMetadata,
        peluqo_invitation_hash: hash,
        mochi_adult_role: adultRole,
      },
    }),
  });
  return confirmed.ok
    ? Response.json({ ok: true }, { headers: cors })
    : reply(503, "No se pudo activar la cuenta. Vuelve a iniciar sesión.");
}

Deno.serve(async (request) => {
  if (request.headers.get("Origin") !== allowedOrigin) return reply(403, "Origen no autorizado.");
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (request.method !== "POST") return reply(405, "Solicitud no válida.");

  const data: unknown = await request.json().catch(() => null);
  if (!hasCredentials(data)) return reply(400, "Revisa el código y los datos de la cuenta.");
  const profile =
    data.action !== "activate" && hasProfile(data)
      ? {
          display_name: data.display_name.trim(),
          account_type: data.account_type,
          age_band: data.age_band,
        }
      : null;
  if (data.action !== "activate" && !profile) return reply(400, "Revisa los datos de la cuenta.");

  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) return reply(503, "El registro del piloto no está disponible.");
  const headers = {
    apikey: key,
    Authorization: "Bearer " + key,
    "Content-Type": "application/json",
  };
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(data.invitation));
  const hash = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");

  try {
    const available = await fetch(url + "/rest/v1/rpc/peluqo_account_invitation_available", {
      method: "POST",
      headers,
      body: JSON.stringify({ p_hash: hash }),
    });
    if (!available.ok) return reply(503, "El registro del piloto no está disponible.");
    if ((await available.json()) !== true)
      return reply(400, "La invitación ha caducado o ya se ha usado.");
    if (data.action === "activate") return await activateExisting(url, headers, data, hash);

    const created = await fetch(url + "/auth/v1/admin/users", {
      method: "POST",
      headers,
      body: JSON.stringify({
        email: data.email,
        password: data.password,
        email_confirm: true,
        user_metadata: profile,
        app_metadata: { peluqo_invitation_hash: hash, mochi_adult_role: profile.account_type },
      }),
    });
    if (!created.ok) {
      const error = await created.json().catch(() => ({}));
      if (["email_exists", "user_already_exists"].includes(error.error_code ?? error.code)) {
        return reply(409, "Ese correo ya tiene una cuenta. Puedes entrar con tu contraseña.");
      }
      return reply(
        400,
        "No se pudo crear la cuenta. Revisa el correo, la contraseña y la invitación.",
      );
    }
    return Response.json({ ok: true }, { headers: cors });
  } catch {
    return reply(503, "El registro del piloto no está disponible. Inténtalo de nuevo.");
  }
});
