import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
const s = JSON.parse(await readFile(".runtime/pilot-secrets.json", "utf8"));
const cloud = JSON.parse(await readFile(".runtime/cloud-public.json", "utf8"));
const demo = JSON.parse(await readFile(".runtime/demo-login.json", "utf8"));
async function auth(email, password) {
  const r = await fetch(cloud.url + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: { apikey: cloud.key, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  assert.equal(r.status, 200);
  return (await r.json()).access_token;
}
async function api(body, token, cookie) {
  const r = await fetch("http://localhost:3000/api/education/", {
    method: body ? "POST" : "GET",
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(cookie ? { Cookie: cookie } : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  return {
    status: r.status,
    data: await r.json(),
    cookie: r.headers.get("set-cookie")?.split(";")[0],
  };
}
async function connector(path, token, body = {}) {
  const r = await fetch("http://localhost:54321/v1/education/" + path, {
    method: "POST",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: r.status, data: await r.json() };
}
const teacher = await auth("docente@peluqo.local", s.teacher_password),
  other = await auth("otro@peluqo.local", s.other_password);
const leo = demo.pupils.find((p) => p.name === "Leo");
const code = await api({ action: "issue-code", learnerId: leo.id }, teacher);
assert.equal(code.status, 200);
const login = await api({ action: "login", code: code.data.code });
assert.equal(login.status, 200);
await api(
  { action: "companion", companion: { name: "Brisa", color: "lavender", accessory: "none" } },
  null,
  login.cookie,
);
const start = await api({ action: "start", versionId: demo.versionId }, null, login.cookie);
assert.equal(start.status, 200);
assert.equal((await connector("pair/start", "wrong")).status, 401);
const pairing = await connector("pair/start", s.provision);
assert.equal(pairing.status, 200);
const approved = await api(
  { action: "approve-pair", code: pairing.data.code, learnerId: leo.id },
  teacher,
);
assert.equal(approved.status, 200);
assert.equal(
  (await api({ action: "approve-pair", code: pairing.data.code, learnerId: leo.id }, teacher))
    .status,
  404,
);
const linked = await connector("pair/status", s.provision, { pending: pairing.data.pending });
assert.ok(linked.data.paired);
const deviceToken = linked.data.token;
assert.equal(
  (
    await api(
      { action: "bind-device", deviceId: approved.data.deviceId, sessionId: start.data.id },
      other,
    )
  ).status,
  404,
);
assert.equal(
  (
    await api(
      { action: "bind-device", deviceId: approved.data.deviceId, sessionId: start.data.id },
      teacher,
    )
  ).status,
  200,
);
const first = await connector("events", deviceToken);
assert.equal(first.data.sessionId, start.data.id);
assert.equal(first.data.companion.name, "Brisa");
const real = JSON.parse(await readFile(".runtime/demo-device.json", "utf8"));
const forged = await connector("events", deviceToken, {
  sessionId: real.sessionId,
  learnerId: demo.pupils.find((p) => p.name === "Luna").id,
});
assert.equal(forged.data.sessionId, start.data.id);
assert.equal(forged.data.companion.name, "Brisa");
await api({ action: "logout" }, null, login.cookie);
const closed = await connector("events", deviceToken);
assert.equal(closed.data.sessionId, null);
await api({ action: "revoke-device", deviceId: approved.data.deviceId }, teacher);
assert.equal((await connector("events", deviceToken)).status, 404);
const checks = [
  "private_provisioning",
  "one_time_pairing",
  "teacher_device_ownership",
  "two_independent_pupils",
  "explicit_session_cannot_be_forged",
  "logout_disconnects_active_session",
  "revocation_denies_old_credential",
];
await writeFile(
  ".runtime/device-isolation-verification.json",
  JSON.stringify(
    { at: new Date().toISOString(), mockDeviceId: approved.data.deviceId, checks },
    null,
    2,
  ),
);
console.log(JSON.stringify({ passed: checks.length, checks }));
