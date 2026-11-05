import postgres from "postgres";
let database: ReturnType<typeof postgres> | undefined;
export function db() {
  const url = process.env["PELUQO_DATABASE_URL"];
  if (!url) throw new Error("El entorno educativo privado no está configurado.");
  return (database ??= postgres(url, {
    max: process.env["VERCEL"] === "1" ? 2 : 6,
    connect_timeout: 10,
    idle_timeout: 20,
    prepare: false,
  }));
}
