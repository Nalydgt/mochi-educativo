import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
const s = JSON.parse(await readFile(".runtime/pilot-secrets.json", "utf8"));
const cloud = JSON.parse(await readFile(".runtime/cloud-public.json", "utf8"));
const login = await fetch(cloud.url + "/auth/v1/token?grant_type=password", {
  method: "POST",
  headers: { apikey: cloud.key, "Content-Type": "application/json" },
  body: JSON.stringify({ email: "docente@peluqo.local", password: s.teacher_password }),
});
assert.equal(login.status, 200);
const token = (await login.json()).access_token;
async function api(body) {
  const r = await fetch("http://localhost:3000/api/education/", {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: "Bearer " + token,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await r.json();
  assert.equal(r.status, 200, JSON.stringify(data));
  return data;
}
const info = await api();
const demo = JSON.parse(await readFile(".runtime/demo.json", "utf8"));
const pupils = info.learners.filter((x) => x.class_id === demo.classId);
assert.equal(pupils.length, 2);
const version = info.versions.find((x) => x.class_id === demo.classId);
assert.ok(version);
const codes = [];
for (const p of pupils) {
  const code = await api({ action: "issue-code", learnerId: p.id });
  codes.push({ id: p.id, name: p.name, code: code.code });
}
await writeFile(
  ".runtime/demo-login.json",
  JSON.stringify({ classId: demo.classId, versionId: version.id, pupils: codes }, null, 2),
);
console.log(
  JSON.stringify({ demoReady: true, pupils: pupils.map((x) => x.name), published: true }),
);
