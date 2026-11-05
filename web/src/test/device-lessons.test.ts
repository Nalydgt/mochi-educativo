import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  deviceLessonAssignmentSchema,
  deviceLessonResultSchema,
  evaluateDeviceLesson,
} from "@/lib/education/device-lessons";
import { db } from "@/lib/education/db.server";
import { handleEducation } from "@/lib/education/api.server";

vi.mock("@/lib/education/db.server", () => ({ db: vi.fn() }));
vi.mock("@/lib/education/adult-auth.server", async (original) => ({
  ...(await original<typeof import("@/lib/education/adult-auth.server")>()),
  adultAccount: vi.fn(async () => "66666666-6666-4666-8666-666666666666"),
}));

const assignmentId = "11111111-1111-4111-8111-111111111111";
const lessonId = "22222222-2222-4222-8222-222222222222";
const resultId = "33333333-3333-4333-8333-333333333333";
const deviceId = "44444444-4444-4444-8444-444444444444";
const learnerId = "55555555-5555-4555-8555-555555555555";
const teacherId = "66666666-6666-4666-8666-666666666666";
const token = "paired-device-token";
const factors: [number, number][] = [
  [3, 4],
  [4, 3],
];
const result = {
  resultId,
  lessonId,
  assignmentId,
  completed: true as const,
  attempts: 3,
  hints: 1,
  elapsedSeconds: 40,
  answers: [
    { a: 3, b: 4, choice: 7, correct: true },
    { a: 3, b: 4, choice: 12, correct: false },
    { a: 4, b: 3, choice: 12, correct: true },
  ],
};

describe("device practice evidence", () => {
  it("recomputes correctness and preserves unsuccessful attempts", () => {
    const evidence = evaluateDeviceLesson(factors, deviceLessonResultSchema.parse(result));
    expect(evidence.answers.map((a) => a.correct)).toEqual([false, true, true]);
    expect(evidence.correctCount).toBe(2);
  });
  it("rejects completion without all assigned exercises and reordered evidence", () => {
    expect(() =>
      evaluateDeviceLesson(factors, { ...result, answers: result.answers.slice(0, 2) }),
    ).toThrow("completada");
    expect(() =>
      evaluateDeviceLesson(factors, { ...result, answers: result.answers.slice(2) }),
    ).toThrow("asignado");
  });
  it("accepts minimal private completion without pretending responses were verified", () => {
    const minimal = deviceLessonResultSchema.parse({
      ...result,
      answers: [],
      detailsShared: false,
      completedCount: 2,
    });
    expect(evaluateDeviceLesson(factors, minimal)).toMatchObject({
      answers: [],
      completedCount: 2,
      detailsShared: false,
      clientReported: true,
    });
    expect(() => evaluateDeviceLesson(factors, { ...minimal, completedCount: 1 })).toThrow(
      "completada",
    );
    expect(
      deviceLessonResultSchema.safeParse({ ...minimal, answers: result.answers }).success,
    ).toBe(false);
  });
  it("bounds storage, counts, dates and factors", () => {
    expect(deviceLessonResultSchema.safeParse({ ...result, attempts: 2 }).success).toBe(false);
    expect(
      deviceLessonResultSchema.safeParse({ ...result, answers: Array(41).fill(result.answers[0]) })
        .success,
    ).toBe(false);
    expect(deviceLessonResultSchema.safeParse({ ...result, elapsedSeconds: 86401 }).success).toBe(
      false,
    );
    const task = {
      action: "assign-device-lesson",
      learnerId,
      subject: "matematicas",
      title: "Multiplica",
      goal: "Comprender los grupos iguales",
      instructions: "Enséñame a formar los grupos",
      dueAt: "2026-11-08",
      factors,
    };
    expect(deviceLessonAssignmentSchema.safeParse(task).success).toBe(true);
    expect(deviceLessonAssignmentSchema.safeParse({ ...task, dueAt: "2026-02-30" }).success).toBe(
      false,
    );
    expect(deviceLessonAssignmentSchema.safeParse({ ...task, factors: [[1, 13]] }).success).toBe(
      false,
    );
    expect(deviceLessonAssignmentSchema.safeParse({ ...task, title: "á".repeat(40) }).success).toBe(
      true,
    );
    expect(deviceLessonAssignmentSchema.safeParse({ ...task, title: "á".repeat(41) }).success).toBe(
      false,
    );
    expect(
      deviceLessonAssignmentSchema.safeParse({ ...task, instructions: "á".repeat(100) }).success,
    ).toBe(true);
    expect(
      deviceLessonAssignmentSchema.safeParse({ ...task, instructions: "á".repeat(101) }).success,
    ).toBe(false);
  });
});

describe("paired-device endpoint authorization and retries", () => {
  let saved: Record<string, unknown> | undefined;
  let revoked: boolean;
  let foreignLesson: boolean;
  let insertions: number;
  let supportCalls: unknown[][];
  let supportDenied: boolean;
  beforeEach(() => {
    vi.stubEnv("PELUQO_INTEGRATION_KEY", "integration-test-key");
    saved = undefined;
    revoked = false;
    foreignLesson = false;
    insertions = 0;
    supportCalls = [];
    supportDenied = false;
    const q = {
      begin: async (fn: (tx: unknown) => unknown) => fn(q),
      unsafe: vi.fn(async (sql: string, args: unknown[]) => {
        if (sql.includes("set_config")) return [];
        if (sql.includes("education.device_school_context"))
          return [{ context: { deviceSettings: { sharePractice: true } } }];
        if (sql.includes("education.device_group_context")) return [{ context: {} }];
        if (sql.includes("education.ingest_support_signal")) {
          supportCalls.push(args);
          if (supportDenied) throw { code: "42501", detail: "private consent state" };
          return [{ result: { accepted: true, signalId: args[1], visibleToFamily: true } }];
        }
        if (sql.includes("SELECT id FROM education.teachers")) return [{ id: teacherId }];
        if (sql.includes("SELECT l.* FROM education.learners")) return [{ id: learnerId }];
        if (sql.includes("INSERT INTO education.device_lessons(")) {
          expect(args[7]).toEqual(factors);
          expect(Array.isArray(args[7])).toBe(true);
          return [{ id: assignmentId, lesson_id: lessonId }];
        }
        if (sql.includes("SELECT * FROM education.devices"))
          return revoked
            ? []
            : [{ id: deviceId, learner_id: learnerId, teacher_id: teacherId, session_id: null }];
        if (sql.includes("UPDATE education.devices")) return [];
        if (sql.includes("SELECT id FROM education.devices"))
          return revoked ? [] : [{ id: deviceId }];
        if (sql.includes("SELECT a.* FROM education.device_lessons"))
          return foreignLesson ? [] : [{ id: assignmentId, lesson_id: lessonId, factors }];
        if (sql.includes("INSERT INTO education.device_lesson_results")) {
          if (!saved) {
            insertions++;
            saved = {
              result_id: args[0],
              assignment_id: args[1],
              device_id: args[2],
              payload: args[3],
              request_hash: args[4],
            };
          }
          return [];
        }
        if (sql.includes("SELECT result_id,assignment_id")) return saved ? [saved] : [];
        if (sql.includes("education.minimize_device_receipt")) {
          const payload = args[4] as typeof result & {
            detailsShared: boolean;
            completedCount: number;
          };
          const previous = saved?.["payload"] as typeof result;
          if (
            !saved ||
            payload.attempts !== previous.attempts ||
            payload.hints !== previous.hints ||
            payload.elapsedSeconds !== previous.elapsedSeconds
          )
            return [{ accepted: false }];
          saved["payload"] = payload;
          saved["request_hash"] = args[3];
          return [{ accepted: true }];
        }
        if (sql.includes("SELECT a.id,a.lesson_id"))
          return [
            {
              id: assignmentId,
              lesson_id: lessonId,
              title: "Multiplicamos",
              instructions: "Agrupamos las fichas",
              factors,
            },
          ];
        if (sql.includes("SELECT name,companion"))
          return [{ name: "Alumno ficticio", companion: { name: "Mochi" } }];
        throw new Error("Unexpected query: " + sql);
      }),
    };
    vi.mocked(db).mockReturnValue(q as unknown as ReturnType<typeof db>);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  async function request(body: Record<string, unknown>, integration = true) {
    return handleEducation(
      new Request("https://school.test/api/education/device", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          ...(integration ? { "X-Integration-Key": "integration-test-key" } : {}),
        },
        body: JSON.stringify(body),
      }),
      true,
    );
  }
  it("delivers assigned practice without an active web learner session", async () => {
    const response = await request({ action: "events" });
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      sessionId: null,
      localLesson: { id: lessonId, assignmentId, kind: "multiplication", factors },
    });
  });
  it("accepts only confirmed minimized support signals through both connector and paired-device authentication", async () => {
    const signal = {
      action: "support-signal",
      signalId: resultId,
      category: "possible_peer_bullying",
      source: "daily_voice",
      schoolPeerContext: true,
      childConfirmed: true,
    };
    expect((await request(signal, false)).status).toBe(401);
    revoked = true;
    expect((await request(signal)).status).toBe(404);
    revoked = false;
    expect((await request({ ...signal, transcript: "private speech" })).status).toBe(400);
    expect((await request({ ...signal, childConfirmed: false })).status).toBe(400);
    expect(supportCalls).toHaveLength(0);
    const response = await request(signal);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      accepted: true,
      signalId: resultId,
      visibleToFamily: true,
    });
    expect(supportCalls).toEqual([
      [deviceId, resultId, "possible_peer_bullying", "daily_voice", true, true],
    ]);
    supportDenied = true;
    const denied = await request({ ...signal, signalId: lessonId });
    expect(denied.status).toBe(403);
    expect(await denied.text()).not.toContain("private consent state");
  });
  it("passes native JSON arrays to postgres when a teacher assigns work", async () => {
    const response = await handleEducation(
      new Request("https://school.test/api/education/", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer adult-test" },
        body: JSON.stringify({
          action: "assign-device-lesson",
          learnerId,
          title: "Enseñar multiplicaciones",
          subject: "matematicas",
          goal: "Comprender los grupos iguales",
          instructions: "Forma los grupos con Mochi.",
          dueAt: "2026-11-08",
          factors,
        }),
      }),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ id: assignmentId, lesson_id: lessonId });
  });
  it("denies connectors, revoked devices and another learner's lesson", async () => {
    expect((await request({ action: "events" }, false)).status).toBe(401);
    revoked = true;
    expect((await request({ action: "events" })).status).toBe(404);
    revoked = false;
    foreignLesson = true;
    expect((await request({ action: "lesson-result", ...result })).status).toBe(404);
    expect(insertions).toBe(0);
  });
  it("acknowledges exact retries once and rejects changed result payloads", async () => {
    const first = await request({ action: "lesson-result", ...result });
    expect(first.status).toBe(200);
    expect(await first.json()).toEqual({ accepted: true, resultId });
    expect((await request({ action: "lesson-result", ...result })).status).toBe(200);
    expect(insertions).toBe(1);
    expect((saved?.["payload"] as typeof result).answers[0]?.correct).toBe(false);
    expect((await request({ action: "lesson-result", ...result, hints: 2 })).status).toBe(409);
  });
  it("accepts privacy downgrade after a lost acknowledgement and never upgrades it back", async () => {
    expect((await request({ action: "lesson-result", ...result })).status).toBe(200);
    const minimal = { ...result, answers: [], detailsShared: false, completedCount: 2 };
    expect((await request({ action: "lesson-result", ...minimal })).status).toBe(200);
    expect(saved?.["payload"]).toMatchObject({
      answers: [],
      detailsShared: false,
      clientReported: true,
    });
    expect((await request({ action: "lesson-result", ...result })).status).toBe(409);
    expect(saved?.["payload"]).toMatchObject({ answers: [], detailsShared: false });
    expect((await request({ action: "lesson-result", ...minimal, hints: 2 })).status).toBe(409);
  });
});
