import { createHash, randomBytes } from "node:crypto";
import { z } from "zod";
import { adultAccount, ApiError } from "./adult-auth.server";
import { db } from "./db.server";
import {
  displayStudentCode,
  studentAccessCommand,
  studentAccessProfile,
  studentAccessStatus,
  type AccessDuration,
  type StudentAccessOptions,
} from "./student-access";

const uuid = z.string().uuid();
const responseHeaders = { "Cache-Control": "no-store" };
const codeAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const hash = (value: string) => createHash("sha256").update(value).digest("hex");
export const randomAccessCode = (length = 12) =>
  Array.from(randomBytes(length), (byte) => codeAlphabet[byte % codeAlphabet.length]).join("");
const expiryHours = { "24h": 24, "7d": 168, "30d": 720 };

export function studentCodeExpiry(
  duration: AccessDuration,
  selected: string | undefined,
  now = Date.now(),
) {
  if (duration === "unlimited") return null;
  const expires =
    duration === "custom" ? Date.parse(selected ?? "") : now + expiryHours[duration] * 3_600_000;
  if (!Number.isFinite(expires) || expires <= now)
    throw new ApiError(400, "Elige una fecha futura.");
  return new Date(expires).toISOString();
}

async function manageAccess(
  adult: string,
  learner: string,
  action: string,
  code: string | null,
  expiresAt: string | null,
) {
  const [row] = await db()<{ result: unknown }[]>`
    SELECT education.manage_student_access(${adult}, ${learner}, ${action}, ${code && hash(code)}, ${expiresAt}) AS result
  `;
  if (!row?.result) throw new ApiError(404, "El perfil no está disponible para tu cuenta.");
  return studentAccessStatus.parse(row.result);
}

export async function legacyStudentCode(teacher: string, learner: string) {
  const code = randomAccessCode();
  await manageAccess(
    teacher,
    learner,
    "issue-legacy",
    code,
    new Date(Date.now() + 600_000).toISOString(),
  );
  return { code, expiresIn: 600 };
}

export async function openStudentLogin(
  code: string,
  { remember, learnerId }: StudentAccessOptions,
) {
  const token = randomBytes(32).toString("base64url");
  const [row] = await db()<{ result: { profile: unknown; expiresAt: string } | null }[]>`
    SELECT education.open_student_login(${hash(code)}, ${hash(token)}, ${remember}, ${learnerId ?? null}) AS result
  `;
  if (!row?.result) throw new ApiError(401, "Revisa el código con tu docente o tu familia.");
  return {
    token,
    profile: studentAccessProfile.parse(row.result.profile),
    maxAge: Math.max(0, Math.floor((Date.parse(row.result.expiresAt) - Date.now()) / 1_000)),
  };
}

export async function handleStudentAccess(request: Request) {
  try {
    const adult = await adultAccount(request);
    if (request.method === "GET") {
      const learner = uuid.safeParse(new URL(request.url).searchParams.get("learnerId"));
      if (!learner.success) throw new ApiError(400, "Elige un perfil válido.");
      return Response.json(await manageAccess(adult, learner.data, "status", null, null), {
        headers: responseHeaders,
      });
    }
    const origin = request.headers.get("origin");
    const expected = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
    if (origin && origin !== expected) throw new ApiError(403, "Origen no autorizado.");
    const body = studentAccessCommand.safeParse(await request.json().catch(() => null));
    if (!body.success) throw new ApiError(400, "Revisa el perfil y la duración del código.");
    const { learnerId, action, duration, expiresAt } = body.data;
    const code = action === "issue" ? randomAccessCode() : null;
    const expiry = code && duration ? studentCodeExpiry(duration, expiresAt) : null;
    const result = await manageAccess(adult, learnerId, action, code, expiry);
    return Response.json(code ? { ...result, code: displayStudentCode(code) } : result, {
      headers: responseHeaders,
    });
  } catch (error) {
    return Response.json(
      {
        error:
          error instanceof ApiError
            ? error.message
            : "No se pudo actualizar el acceso de este alumno.",
      },
      { headers: responseHeaders, status: error instanceof ApiError ? error.status : 503 },
    );
  }
}
