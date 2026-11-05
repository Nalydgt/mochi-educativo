import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { reviewedMission } from "../fixtures/reviewed-mission";
import postgres from "postgres";
const secrets = JSON.parse(await readFile(".runtime/pilot-secrets.json", "utf8"));
const cloud = JSON.parse(await readFile(".runtime/cloud-public.json", "utf8"));
const results: string[] = [];
const base = "http://localhost:3000";
async function auth(email: string, password: string) {
  const r = await fetch(cloud.url + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: { apikey: cloud.key, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const b = await r.json();
  assert.equal(r.status, 200, b.msg ?? "Teacher authentication failed");
  return b.access_token as string;
}
async function api(body: unknown, token?: string, cookie?: string) {
  const r = await fetch(base + "/api/education/", {
    method: body ? "POST" : "GET",
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(cookie ? { Cookie: cookie } : {}),
      ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: body instanceof FormData ? body : JSON.stringify(body) } : {}),
  });
  const data = await r.json();
  return { status: r.status, data, cookie: r.headers.get("set-cookie")?.split(";")[0] };
}
const teacher = await auth("docente@peluqo.local", secrets.teacher_password);
const other = await auth("otro@peluqo.local", secrets.other_password);
assert.equal((await api(undefined)).status, 401);
results.push("Anonymous classroom access denied");
const cl = await api(
  { action: "create-class", name: "Verificación " + new Date().toISOString() },
  teacher,
);
assert.equal(cl.status, 200);
assert.equal(
  (await api({ action: "create-learner", classId: cl.data.id, name: "Intruso" }, other)).status,
  404,
);
results.push("Cross-teacher writes denied");
const form = new FormData();
form.set("classId", cl.data.id);
form.set(
  "file",
  new File([await readFile("fixtures/vertebrados.txt")], "vertebrados.txt", { type: "text/plain" }),
);
const doc = await api(form, teacher);
assert.equal(doc.status, 200, doc.data.error);
const chunks = await api({ action: "document-source", documentId: doc.data.documentId }, teacher);
assert.equal(chunks.status, 200);
assert.ok(chunks.data.length);
assert.equal(
  (await api({ action: "document-source", documentId: doc.data.documentId }, other)).data.length,
  0,
);
results.push("Real upload, extraction and owner-scoped sources");
const mission = reviewedMission(chunks.data[0].id, chunks.data[0].page);
assert.equal(
  (await api({ action: "save-draft", classId: cl.data.id, mission }, teacher)).status,
  200,
);
const version = await api({ action: "publish", classId: cl.data.id }, teacher);
assert.equal(version.status, 200, JSON.stringify(version.data));
const students = [];
for (const name of ["Explorador Uno", "Explorador Dos"]) {
  const l = await api({ action: "create-learner", classId: cl.data.id, name }, teacher);
  const code = await api({ action: "issue-code", learnerId: l.data.id }, teacher);
  const login = await api({ action: "login", code: code.data.code });
  assert.equal(login.status, 200);
  assert.equal((await api({ action: "login", code: code.data.code })).status, 401);
  students.push({ id: l.data.id, cookie: login.cookie! });
}
results.push("Individual single-use codes and independent pupils");
const first = students[0]!,
  second = students[1]!;
let state = await api(undefined, undefined, first.cookie);
assert.equal(state.data.progress.discoveries, 0);
assert.equal(
  (await api({ action: "create-class", name: "No permitido" }, undefined, first.cookie)).status,
  403,
);
assert.equal(
  (
    await api(
      { action: "companion", companion: { name: "Nube", color: "mint", accessory: "star" } },
      undefined,
      first.cookie,
    )
  ).status,
  403,
);
assert.equal(
  (
    await api(
      { action: "companion", companion: { name: "Nube", color: "mint", accessory: "none" } },
      undefined,
      first.cookie,
    )
  ).status,
  200,
);
const start = await api({ action: "start", versionId: version.data.id }, undefined, first.cookie);
assert.equal(start.status, 200);
const sid = start.data.id;
assert.equal(
  (await api({ action: "focus", sessionId: sid, activityId: "d1" }, undefined, second.cookie))
    .status,
  404,
);
assert.equal(
  (await api({ action: "hint", sessionId: sid, activityId: "d1" }, undefined, first.cookie)).status,
  403,
);
results.push("Learner isolation, locked rewards and unaided assessments");
state = await api(undefined, undefined, first.cookie);
assert.ok(!JSON.stringify(state.data.learning.activities).includes('"answer"'));
assert.ok(!JSON.stringify(state.data.learning.activities).includes('"hints"'));
for (const a of mission.diagnostic) {
  const response = await api(
    {
      action: "answer",
      sessionId: sid,
      activityId: a.id,
      requestId: randomUUID(),
      answer: a.answer,
    },
    undefined,
    first.cookie,
  );
  assert.equal(response.status, 200);
  assert.equal(response.data.correct, null);
}
state = await api(undefined, undefined, first.cookie);
assert.ok(
  state.data.learning.attempts.every(
    (attempt: { correct: boolean | null }) => attempt.correct === null,
  ),
);
results.push("Assessment submissions and learner history withhold correctness during evaluation");
assert.equal(
  (await api({ action: "advance", sessionId: sid }, undefined, first.cookie)).status,
  200,
);
const p = mission.practice[0]!;
const requestId = randomUUID();
const body = { action: "answer", sessionId: sid, activityId: p.id, requestId, answer: p.answer };
const repeat = await Promise.all([
  api(body, undefined, first.cookie),
  api(body, undefined, first.cookie),
]);
assert.ok(repeat.every((x) => x.status === 200));
state = await api(undefined, undefined, first.cookie);
assert.equal(state.data.progress.discoveries, 1);
assert.equal(
  state.data.learning.attempts.filter((a: { activity_id: string }) => a.activity_id === p.id)
    .length,
  1,
);
results.push("Concurrent duplicate submissions evaluated once");
assert.equal(
  (
    await api(
      { action: "hint", sessionId: sid, activityId: mission.practice[1]!.id },
      undefined,
      first.cookie,
    )
  ).status,
  200,
);
for (const a of mission.practice.slice(1))
  assert.equal(
    (
      await api(
        {
          action: "answer",
          sessionId: sid,
          activityId: a.id,
          requestId: randomUUID(),
          answer: a.answer,
        },
        undefined,
        first.cookie,
      )
    ).status,
    200,
  );
assert.equal(
  (await api({ action: "advance", sessionId: sid }, undefined, first.cookie)).status,
  200,
);
for (const a of mission.final)
  assert.equal(
    (
      await api(
        {
          action: "answer",
          sessionId: sid,
          activityId: a.id,
          requestId: randomUUID(),
          answer: a.answer,
        },
        undefined,
        first.cookie,
      )
    ).status,
    200,
  );
assert.equal(
  (await api({ action: "advance", sessionId: sid }, undefined, first.cookie)).status,
  200,
);
state = await api(undefined, undefined, first.cookie);
assert.equal(state.data.learning.phase, "completed");
assert.equal(state.data.progress.discoveries, 3);
assert.equal(
  (await api({ action: "advance", sessionId: sid }, undefined, first.cookie)).status,
  409,
);
results.push("Three games, real stored results and delayed retention gate");
const s2 = await api(undefined, undefined, second.cookie);
assert.equal(s2.data.learner.companion.name, "Peluqo");
assert.equal(s2.data.progress.discoveries, 0);
assert.equal(s2.data.learning, null);
const connection = JSON.parse(await readFile(".runtime/cloud-database.json", "utf8"));
const pg = postgres(connection.url, { max: 1, prepare: false });
try {
  await pg.begin(async (tx) => {
    await tx`select set_config('peluqo.service','true',true)`;
    await tx`update education.sessions set completed_at=now()-interval '8 days' where id=${sid}`;
  });
  const nextCode = await api({ action: "issue-code", learnerId: first.id }, teacher);
  const returnVisit = await api({ action: "login", code: nextCode.data.code });
  assert.equal(returnVisit.status, 200, JSON.stringify(returnVisit.data));
  assert.equal((await api(undefined, undefined, first.cookie)).status, 404);
  first.cookie = returnVisit.cookie!;
  const resumed = await api(undefined, undefined, first.cookie);
  assert.equal(resumed.data.learning.id, sid);
  assert.equal(resumed.data.learner.companion.name, "Nube");
  assert.equal(
    (await api({ action: "advance", sessionId: sid }, undefined, first.cookie)).status,
    200,
  );
  for (const a of mission.retention)
    assert.equal(
      (
        await api(
          {
            action: "answer",
            sessionId: sid,
            activityId: a.id,
            requestId: randomUUID(),
            answer: a.answer,
          },
          undefined,
          first.cookie,
        )
      ).status,
      200,
    );
  assert.equal(
    (await api({ action: "advance", sessionId: sid }, undefined, first.cookie)).status,
    200,
  );
  const delayed = await api(undefined, undefined, first.cookie);
  assert.ok(delayed.data.learning.retention_completed_at);
  results.push(
    "A fresh individual code resumes the same mission and permits delayed evaluation after seven days",
  );
  const teachers = await pg.begin(async (tx) => {
    await tx`select set_config('peluqo.teacher',${JSON.parse(Buffer.from(teacher.split(".")[1]!, "base64url").toString()).sub},true)`;
    return tx`select teacher_id from education.classes`;
  });
  assert.ok(
    teachers.every(
      (x) =>
        x.teacher_id ===
        JSON.parse(Buffer.from(teacher.split(".")[1]!, "base64url").toString()).sub,
    ),
  );
  assert.equal((await pg`select id from education.classes`).length, 0);
  results.push(
    "Database RLS enforces teacher ownership without application predicates and resets between pooled transactions",
  );
} finally {
  await pg.end();
}
assert.equal((await api({ action: "logout" }, undefined, first.cookie)).status, 200);
assert.equal((await api(undefined, undefined, first.cookie)).status, 404);
results.push("Logout revokes the pupil session");
await writeFile(
  ".runtime/verification.json",
  JSON.stringify(
    {
      at: new Date().toISOString(),
      checks: results,
      classId: cl.data.id,
      versionId: version.data.id,
    },
    null,
    2,
  ),
);
console.log(JSON.stringify({ passed: results.length, checks: results }, null, 2));
