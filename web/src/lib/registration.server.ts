import { createHash, randomBytes } from "node:crypto";
import { isIP } from "node:net";
import { z } from "zod";
import { db } from "@/lib/education/db.server";
import { signupAge } from "@/lib/learning-schema";

const credentials = {
  email: z.string().trim().email().max(254).toLowerCase(),
  password: z
    .string()
    .min(1)
    .refine((value) => Buffer.byteLength(value) <= 72),
};
const registration = z.discriminatedUnion("action", [
  z
    .object({
      action: z.literal("register"),
      ...credentials,
      display_name: z.string().trim().min(1).max(60),
      account_type: z.enum(["family", "teacher"]),
      age_band: signupAge,
    })
    .strict(),
  z.object({ action: z.literal("activate"), ...credentials }).strict(),
]);

const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
const edgeOrigin = "https://peluqo-mundos.vercel.app";
const digest = (value: string) => createHash("sha256").update(value).digest("hex");
const unavailable = "El alta no está disponible ahora. Puedes volver a intentarlo en unos minutos.";

function reply(status: number, error?: string) {
  return Response.json(error ? { error } : { ok: true }, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function handleRegistration(request: Request) {
  const origin = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
  if (request.headers.get("origin") !== origin) return reply(403, "Origen no autorizado.");
  if (request.headers.get("content-type")?.split(";")[0] !== "application/json")
    return reply(415, "Solicitud no válida.");

  const parsed = registration.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return reply(400, "Revisa los datos de la cuenta y la contraseña.");
  const data = parsed.data;
  if (data.action === "register") {
    if (data.password.length < 8)
      return reply(400, "Elige una contraseña de al menos 8 caracteres.");
    if (data.age_band !== "18+")
      return reply(400, "Las cuentas familiares y docentes requieren una persona adulta.");
  }
  const url = process.env["SUPABASE_URL"];
  const key = process.env["SUPABASE_PUBLISHABLE_KEY"];
  if (!url || !key) return reply(503, unavailable);

  const ip =
    process.env["VERCEL"] === "1"
      ? request.headers.get("x-vercel-forwarded-for")?.split(",")[0]?.trim()
      : undefined;
  const client = digest("peluqo-signup:" + (ip && isIP(ip) ? ip : "default"));
  const invitation = Array.from(randomBytes(24), (byte) => alphabet.charAt(byte & 31)).join("");
  try {
    const [row] = await db()<
      {
        allowed: boolean;
      }[]
    >`select education.issue_signup_invite(${digest(invitation)}, ${client}) as allowed`;
    if (!row?.allowed) return reply(429, "Espera unos minutos antes de volver a intentarlo.");

    const result = await fetch(url + "/functions/v1/peluqo-pilot-signup", {
      method: "POST",
      headers: { apikey: key, Origin: edgeOrigin, "Content-Type": "application/json" },
      body: JSON.stringify({ ...data, invitation }),
      signal: AbortSignal.timeout(15_000),
    });
    if (result.ok) return reply(200);
    if (result.status === 409)
      return reply(409, "Ese correo ya tiene una cuenta. Puedes iniciar sesión.");
    if (result.status === 401) return reply(401, "Revisa tu correo y tu contraseña.");
    if (result.status === 400)
      return reply(400, "Revisa el correo y la contraseña e inténtalo de nuevo.");
    return reply(503, unavailable);
  } catch {
    return reply(503, unavailable);
  }
}
