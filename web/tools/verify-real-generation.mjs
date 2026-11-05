import { readFile, writeFile } from "node:fs/promises";
import assert from "node:assert/strict";
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
    method: "POST",
    headers: {
      Authorization: "Bearer " + token,
      ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    },
    body: body instanceof FormData ? body : JSON.stringify(body),
    signal: AbortSignal.timeout(620000),
  });
  const data = await r.json();
  assert.equal(r.status, 200, JSON.stringify(data));
  return data;
}
const cl = await api({ action: "create-class", name: "Expedición de los vertebrados" });
const form = new FormData();
form.set("classId", cl.id);
form.set(
  "file",
  new File(
    [await readFile("output/pdf/expedicion-vertebrados.pdf")],
    "expedicion-vertebrados.pdf",
    { type: "application/pdf" },
  ),
);
const doc = await api(form);
const sources = await api({ action: "document-source", documentId: doc.documentId });
assert.ok(sources.length && sources.every((x) => x.page === 1));
await writeFile(
  ".runtime/demo.json",
  JSON.stringify({ classId: cl.id, documentId: doc.documentId, sources }, null, 2),
);
console.log(
  JSON.stringify({
    pdfUploaded: true,
    pageReferences: true,
    chunks: sources.length,
    generatingWith: "Hermes / peluqo",
  }),
);
const generated = await api({ action: "generate", classId: cl.id, documentId: doc.documentId });
await writeFile(".runtime/generated-mission.json", JSON.stringify(generated.draft, null, 2));
console.log(
  JSON.stringify({
    generated: true,
    title: generated.draft.title,
    types: generated.draft.practice.map((a) => a.type),
    activities: ["diagnostic", "practice", "final", "retention"].reduce(
      (n, k) => n + generated.draft[k].length,
      0,
    ),
  }),
);
