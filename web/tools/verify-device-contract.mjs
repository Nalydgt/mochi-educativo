import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createHash, createHmac } from "node:crypto";
import postgres from "postgres";
const s = JSON.parse(await readFile(".runtime/pilot-secrets.json", "utf8"));
const cloud = JSON.parse(await readFile(".runtime/cloud-public.json", "utf8"));
const config = JSON.parse(await readFile(".runtime/cloud-database.json", "utf8"));
const browser = JSON.parse(await readFile(".runtime/student-browser.json", "utf8"));
const cookie = browser.cookies
  .filter((x) => x.name === "peluqo_student")
  .map((x) => x.name + "=" + x.value)
  .join("; ");
assert.ok(cookie);
async function api(body, headers = {}) {
  const r = await fetch("http://localhost:3000/api/education/", {
    method: body ? "POST" : "GET",
    headers: { ...headers, ...(body ? { "Content-Type": "application/json" } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await r.json();
  assert.equal(r.status, 200, JSON.stringify(data));
  return data;
}
const state = await api(null, { Cookie: cookie });
assert.equal(state.learning.phase, "practice");
const pg = postgres(config.url, { max: 1, prepare: false });
let d;
try {
  [d] = await pg.begin(async (tx) => {
    await tx`select set_config('peluqo.service','true',true)`;
    return tx`select d.id,d.token_hash,p.id as pairing_id,p.secret_hash from education.devices d join education.pairings p on p.device_id=d.id where d.learner_id=${state.learner.id} and not d.revoked order by d.created_at desc limit 1`;
  });
} finally {
  await pg.end();
}
assert.ok(d);
const token = createHmac("sha256", s.pairing)
  .update(d.secret_hash + d.pairing_id)
  .digest("base64url");
assert.equal(createHash("sha256").update(token).digest("hex"), d.token_hash);
await writeFile(
  ".runtime/demo-device.json",
  JSON.stringify({ id: d.id, token, sessionId: state.learning.id, cookie }, null, 2),
);
async function connector(path, body = {}) {
  const r = await fetch("http://localhost:54321/v1/education/" + path, {
    method: "POST",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(20000),
  });
  const data = await r.json();
  assert.equal(r.status, 200, JSON.stringify(data));
  return data;
}
let connected = await connector("events");
console.log(JSON.stringify({ credentialValid: true, sessionInitially: connected.sessionId }));
const login = await fetch(cloud.url + "/auth/v1/token?grant_type=password", {
  method: "POST",
  headers: { apikey: cloud.key, "Content-Type": "application/json" },
  body: JSON.stringify({ email: "docente@peluqo.local", password: s.teacher_password }),
});
assert.equal(login.status, 200);
const teacher = (await login.json()).access_token;
await api(
  { action: "bind-device", deviceId: d.id, sessionId: state.learning.id },
  { Authorization: "Bearer " + teacher },
);
connected = await connector("events");
assert.equal(connected.sessionId, state.learning.id);
assert.equal(connected.companion.name, state.learner.companion.name);
await api(
  { action: "hint", sessionId: state.learning.id, activityId: state.learning.activities[0].id },
  { Cookie: cookie },
);
const events = await connector("events");
assert.ok(events.events.length);
assert.ok(events.events.every((e) => typeof e.seq === "number"));
const event = events.events.at(-1);
await connector("ack", { seq: event.seq, sessionId: state.learning.id });
await connector("ack", { seq: event.seq, sessionId: state.learning.id });
console.log(
  JSON.stringify({
    boundToExactSession: true,
    sharedName: true,
    numericSequences: true,
    repeatedAcknowledgementSafe: true,
  }),
);
const speech = await fetch("http://localhost:54321/v1/education/say", {
  method: "POST",
  headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
  body: JSON.stringify({ eventId: event.id }),
  signal: AbortSignal.timeout(80000),
});
assert.equal(
  speech.status,
  200,
  await speech
    .clone()
    .text()
    .then((x) => x.slice(0, 200)),
);
assert.equal(speech.headers.get("x-mochi-sample-rate"), "16000");
const audio = Buffer.from(await speech.arrayBuffer());
assert.ok(audio.length > 3200 && audio.length % 2 === 0);
await writeFile(".runtime/educational-voice.pcm", audio);
await writeFile(
  ".runtime/device-verification.json",
  JSON.stringify(
    {
      at: new Date().toISOString(),
      deviceId: d.id,
      sessionId: state.learning.id,
      pcmBytes: audio.length,
      checks: [
        "credential",
        "explicit_session",
        "appearance_name",
        "numeric_events",
        "idempotent_ack",
        "elevenlabs_pcm_after_ack",
      ],
    },
    null,
    2,
  ),
);
console.log(JSON.stringify({ elevenLabs: true, pcm16000: true, bytes: audio.length }));
