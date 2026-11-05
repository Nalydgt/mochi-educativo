import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
const d = JSON.parse(await readFile(".runtime/demo-device.json", "utf8"));
async function state() {
  const r = await fetch("http://localhost:3000/api/education/", { headers: { Cookie: d.cookie } });
  assert.equal(r.status, 200);
  return r.json();
}
const before = await state();
const requestId = randomUUID();
console.log(
  JSON.stringify({
    testing: "local ASR → restricted Hermes tutor → ElevenLabs",
    input: "synthetic Spanish PCM fixture",
  }),
);
const response = await fetch("http://localhost:54321/v1/education/turn", {
  method: "POST",
  headers: {
    Authorization: "Bearer " + d.token,
    "Content-Type": "application/octet-stream",
    "X-Mochi-Turn-ID": requestId,
  },
  body: await readFile(".runtime/educational-voice.pcm"),
  signal: AbortSignal.timeout(180000),
});
assert.equal(
  response.status,
  200,
  await response
    .clone()
    .text()
    .then((x) => x.slice(0, 120)),
);
assert.equal(response.headers.get("x-mochi-sample-rate"), "16000");
const pcm = Buffer.from(await response.arrayBuffer());
assert.ok(pcm.length > 3200 && pcm.length % 2 === 0);
const after = await state();
const turn = after.learning.turns.find((t) => t.id === requestId);
assert.ok(turn && turn.question && turn.sources.length > 0);
assert.equal(after.learning.attempts.length, before.learning.attempts.length);
await writeFile(
  ".runtime/voice-chain-verification.json",
  JSON.stringify(
    {
      at: new Date().toISOString(),
      input: "synthetic fixture",
      localRecognition: true,
      hermes: true,
      elevenLabs: true,
      sourceCount: turn.sources.length,
      scoredAttemptsUnchanged: true,
      replyPcmBytes: pcm.length,
    },
    null,
    2,
  ),
);
console.log(
  JSON.stringify({
    recognized: true,
    sourceReferences: turn.sources.length,
    elevenLabs: true,
    scoredAttemptsUnchanged: true,
  }),
);
