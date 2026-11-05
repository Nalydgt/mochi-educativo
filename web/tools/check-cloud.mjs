import postgres from "postgres";
import { readFile, writeFile } from "node:fs/promises";
const secrets = JSON.parse(await readFile(".runtime/pilot-secrets.json", "utf8"));
const pub = JSON.parse(await readFile(".runtime/cloud-public.json", "utf8"));
for (const n of [1, 0]) {
  const host = `aws-${n}-eu-west-3.pooler.supabase.com`;
  const url = `postgres://peluqo_backend.${pub.project}:${secrets.cloud_database}@${host}:5432/postgres?sslmode=require`;
  const p = postgres(url, { max: 1, connect_timeout: 10, prepare: false });
  try {
    const [result] =
      await p`select current_user,(select count(*) from education.classes) as visible_classes`;
    await writeFile(".runtime/cloud-database.json", JSON.stringify({ url, host }, null, 2));
    console.log(JSON.stringify({ connected: true, host, ...result }));
    break;
  } catch (e) {
    console.log(JSON.stringify({ host, code: e.code, message: e.message.slice(0, 150) }));
  } finally {
    await p.end({ timeout: 1 });
  }
}
