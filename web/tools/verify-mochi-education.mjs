// Live verification with existing fictitious accounts. Never prints credentials.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = async (file) => JSON.parse(await readFile(path.join(root, file), "utf8"));
const cloud = await read(".runtime/cloud-public.json");
const teacher = await read(".runtime/teacher-demo.json");
const family = await read(".runtime/qa-integral-family.json");
const local = await read(".runtime/pilot-secrets.json");
const device = await read(".runtime/mochi-education-device.json");
const base = process.env.MOCHI_WEB_URL ?? "https://peluqo-mundos.vercel.app";
async function login(account) {
  const response = await fetch(cloud.url + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: { apikey: cloud.key, "Content-Type": "application/json" },
    body: JSON.stringify({ email: account.email, password: account.password }),
    signal: AbortSignal.timeout(20000),
  });
  assert.equal(response.status, 200, "Fictitious adult authentication failed");
  return (await response.json()).access_token;
}
async function api(url, token, body) {
  const response = await fetch(base + url, {
    method: body ? "POST" : "GET",
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      Origin: base,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(30000),
  });
  const data = await response.json();
  assert.equal(response.status, 200, data.error ?? "Education API failed");
  return data;
}
const teacherToken = await login(teacher),
  familyToken = await login(family);
if (process.argv.includes("--link-family")) {
  const code = await api("/api/education/", teacherToken, {
    action: "issue-family-code",
    learnerId: device.learnerId,
  });
  await api("/api/education/progress", familyToken, { code: code.code });
  console.log(JSON.stringify({ fictitiousGuardianLinked: true, notificationsSent: false }));
} else {
  const report = await api("/api/education/device-lessons", teacherToken);
  const completed = report.lessons.find(
    (lesson) => lesson.learnerId === device.learnerId && lesson.result,
  );
  assert.ok(completed, "No completed result received from the physical Mochi");
  assert.equal(completed.result.attempts, completed.exerciseCount + 1);
  assert.ok(completed.result.hints >= 1);
  assert.ok(completed.result.answers.some((answer) => !answer.correct));
  assert.equal(completed.result.correctCount, completed.exerciseCount);
  const guardian = await api("/api/education/device-lessons", familyToken);
  assert.equal(guardian.role, "family");
  assert.deepEqual(
    guardian.lessons.find((lesson) => lesson.id === completed.id)?.result,
    completed.result,
  );
  const otherToken = await login({
    email: "docente@peluqo.local",
    password: local.teacher_password,
  });
  const other = await api("/api/education/device-lessons", otherToken);
  assert.ok(other.lessons.every((lesson) => lesson.learnerId !== device.learnerId));
  const anonymous = await fetch(base + "/api/education/device-lessons");
  assert.equal(anonymous.status, 401);
  const output = {
    passed: true,
    at: new Date().toISOString(),
    data: "fictional_demonstration",
    source: "real_physical_board_result",
    teacherCreatedInBrowser: true,
    teacherSeesResult: true,
    linkedFamilySeesSameResult: true,
    otherTeacherCannotRead: true,
    anonymousDenied: true,
    exerciseCount: completed.exerciseCount,
    attempts: completed.result.attempts,
    hints: completed.result.hints,
    containsRecordedIncorrectAttempt: true,
    officialGradeGenerated: false,
    conversationIncluded: false,
  };
  await writeFile(
    path.join(
      root,
      "..",
      "tamagochi 2",
      "docs",
      "mediciones",
      "20261105-mochi-profesor-familia.json",
    ),
    JSON.stringify(output, null, 2) + "\n",
  );
  console.log(JSON.stringify(output));
}
