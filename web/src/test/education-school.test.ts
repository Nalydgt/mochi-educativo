import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, adultAccount } from "@/lib/education/adult-auth.server";
import { db } from "@/lib/education/db.server";
import { InferenceUnavailable, queueInference } from "@/lib/education/inference.server";
import { schoolCommandSchema, supportSignalSchema } from "@/lib/education/school-schema";
import { handleSchool } from "@/lib/education/school.server";

vi.mock("@/lib/education/db.server", () => ({ db: vi.fn() }));
vi.mock("@/lib/education/adult-auth.server", async (original) => ({
  ...(await original<typeof import("@/lib/education/adult-auth.server")>()),
  adultAccount: vi.fn(),
}));
vi.mock("@/lib/education/inference.server", async (original) => ({
  ...(await original<typeof import("@/lib/education/inference.server")>()),
  queueInference: vi.fn(),
}));

const adult = "11111111-1111-4111-8111-111111111111";
const learner = "22222222-2222-4222-8222-222222222222";
const classroom = "33333333-3333-4333-8333-333333333333";
const nonce = "44444444-4444-4444-8444-444444444444";
const task = {
  action: "batch-assign",
  requestId: nonce,
  classId: classroom,
  subject: "matematicas",
  title: "Agrupaciones iguales",
  goal: "Comprender los grupos iguales",
  instructions: "Cuenta los objetos en cada grupo.",
  dueAt: "2026-11-07",
  factors: [
    [2, 3],
    [3, 2],
  ],
};
const grade = {
  action: "save-grade",
  requestId: nonce,
  learnerId: learner,
  subject: "Matemáticas",
  title: "Evaluación docente",
  value: 7.5,
  feedback: "Ha explicado cómo agrupó los objetos.",
  publish: false,
};
const settings = {
  action: "save-settings",
  requestId: nonce,
  learnerId: learner,
  dailyMinutes: 30,
  startTime: "08:00",
  endTime: "20:00",
  timezone: "Europe/Madrid",
  language: "es",
  voiceEnabled: true,
  sharePractice: false,
  expectedRevision: 0,
};

describe("adult school command boundaries", () => {
  it("bounds parent reminders, deliberate alert consent and minimized child-confirmed support signals", () => {
    expect(
      schoolCommandSchema.safeParse({
        ...settings,
        reminderMinutes: null,
        familySupportAlertsEnabled: false,
      }).success,
    ).toBe(true);
    expect(schoolCommandSchema.safeParse({ ...settings, reminderMinutes: 5 }).success).toBe(true);
    expect(schoolCommandSchema.safeParse({ ...settings, reminderMinutes: 60 }).success).toBe(true);
    for (const reminderMinutes of [0, 4, 61, 10.5])
      expect(schoolCommandSchema.safeParse({ ...settings, reminderMinutes }).success).toBe(false);
    const signal = {
      action: "support-signal",
      signalId: nonce,
      category: "possible_peer_bullying",
      source: "daily_voice",
      schoolPeerContext: true,
      childConfirmed: true,
    };
    expect(supportSignalSchema.safeParse(signal).success).toBe(true);
    expect(supportSignalSchema.safeParse({ ...signal, source: "lesson_voice" }).success).toBe(true);
    for (const unsafe of [
      { source: "family_harm" },
      { childConfirmed: false },
      { schoolPeerContext: false },
      { transcript: "private text" },
      { learnerId: learner },
    ])
      expect(supportSignalSchema.safeParse({ ...signal, ...unsafe }).success).toBe(false);
  });
  it("requires distinct bounded classmates, voluntary helpers and explicit revision for group edits", () => {
    const group = {
      action: "save-group",
      requestId: nonce,
      classId: classroom,
      name: "Equipo Cometa",
      members: [
        { learnerId: learner, peerRole: "helper", voluntary: true, buddyAlias: "Cometa" },
        { learnerId: adult, peerRole: "member", voluntary: true },
      ],
    };
    expect(schoolCommandSchema.safeParse(group).success).toBe(true);
    expect(
      schoolCommandSchema.safeParse({
        ...group,
        members: [{ ...group.members[0], voluntary: false }, group.members[1]],
      }).success,
    ).toBe(false);
    expect(
      schoolCommandSchema.safeParse({ ...group, members: [group.members[0], group.members[0]] })
        .success,
    ).toBe(false);
    expect(schoolCommandSchema.safeParse({ ...group, groupId: nonce }).success).toBe(false);
    expect(
      schoolCommandSchema.safeParse({
        ...task,
        action: "assign-group",
        classId: undefined,
        groupId: nonce,
      }).success,
    ).toBe(true);
  });
  it("requires deliberate publication and revision when editing an official manual grade", () => {
    expect(schoolCommandSchema.safeParse(grade).success).toBe(true);
    expect(schoolCommandSchema.safeParse({ ...grade, publish: undefined }).success).toBe(false);
    expect(schoolCommandSchema.safeParse({ ...grade, value: 10.1 }).success).toBe(false);
    expect(schoolCommandSchema.safeParse({ ...grade, gradeId: learner }).success).toBe(false);
    expect(
      schoolCommandSchema.safeParse({ ...grade, gradeId: learner, expectedRevision: 1 }).success,
    ).toBe(true);
  });
  it("requires explicit recipients and a bounded device-compatible task", () => {
    expect(schoolCommandSchema.safeParse(task).success).toBe(true);
    expect(schoolCommandSchema.safeParse({ ...task, classId: undefined }).success).toBe(false);
    expect(schoolCommandSchema.safeParse({ ...task, factors: [[13, 2]] }).success).toBe(false);
    expect(schoolCommandSchema.safeParse({ ...task, title: "á".repeat(41) }).success).toBe(false);
    expect(
      schoolCommandSchema.safeParse({ ...task, learnerIds: Array(201).fill(learner) }).success,
    ).toBe(false);
  });
  it("validates real timezones, usable schedules and chronological calendar events", () => {
    expect(schoolCommandSchema.safeParse(settings).success).toBe(true);
    expect(
      schoolCommandSchema.safeParse({ ...settings, timezone: "invented/timezone" }).success,
    ).toBe(false);
    expect(schoolCommandSchema.safeParse({ ...settings, endTime: "08:00" }).success).toBe(false);
    const event = {
      action: "save-event",
      requestId: nonce,
      classId: classroom,
      title: "Reunión de tutoría",
      description: "Seguimiento del trimestre",
      kind: "meeting",
      startsAt: "2026-11-07T16:00:00+01:00",
      endsAt: "2026-11-07T15:00:00+01:00",
    };
    expect(schoolCommandSchema.safeParse(event).success).toBe(false);
    expect(
      schoolCommandSchema.safeParse({ ...event, endsAt: "2026-11-07T16:30:00+01:00" }).success,
    ).toBe(true);
  });
});

describe("school HTTP adapter", () => {
  const query = vi.fn();
  beforeEach(() => {
    vi.mocked(adultAccount).mockImplementation(async (request) => {
      if (!request.headers.get("authorization")) throw new ApiError(401, "Inicia sesión.");
      return adult;
    });
    query.mockReset();
    query.mockImplementation(async (strings: TemplateStringsArray) => {
      if (strings.join("").includes("school_read"))
        return [{ snapshot: { role: "family", lessons: [] } }];
      if (strings.join("").includes("school_proposal_context"))
        return [{ context: { sources: [] } }];
      return [{ result: { saved: true } }];
    });
    vi.mocked(db).mockReturnValue(query as unknown as ReturnType<typeof db>);
    vi.mocked(queueInference).mockReset();
  });
  afterEach(() => vi.unstubAllEnvs());

  function request(body?: unknown, origin = "https://school.test") {
    return new Request("https://school.test/api/education/school", {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: "Bearer fictitious-adult",
        Origin: origin,
        "Content-Type": "application/json",
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  }
  it("authenticates before reading and passes only the verified identity to the database", async () => {
    const response = await handleSchool(request());
    expect(response.status).toBe(200);
    expect(query.mock.calls[0]?.[1]).toBe(adult);
    const rejected = await handleSchool(new Request("https://school.test/api/education/school"));
    expect(rejected.status).toBe(401);
    expect(query).toHaveBeenCalledTimes(1);
  });
  it("strips actor impersonation, preserves request id and sends exactly one atomic command", async () => {
    const response = await handleSchool(
      request({ ...grade, adultId: learner, teacherId: learner }),
    );
    expect(response.status).toBe(200);
    expect(query).toHaveBeenCalledTimes(1);
    expect(query.mock.calls[0]?.[1]).toBe(adult);
    const body = JSON.parse(query.mock.calls[0]?.[2] as string);
    expect(body.requestId).toBe(nonce);
    expect(body.publish).toBe(false);
    expect(body).not.toHaveProperty("adultId");
    expect(body).not.toHaveProperty("teacherId");
    expect(queueInference).not.toHaveBeenCalled();
  });
  it("rejects cross-origin and invalid forms before a database mutation", async () => {
    expect((await handleSchool(request(grade, "https://foreign.test"))).status).toBe(403);
    expect((await handleSchool(request({ ...task, factors: [[0, 1]] }))).status).toBe(400);
    expect(query).not.toHaveBeenCalled();
  });
  it.each([
    ["42501", 403],
    ["P0002", 404],
    ["40001", 409],
    ["23505", 409],
    ["54000", 429],
  ])(
    "maps authoritative database rejection %s without exposing internals",
    async (code, status) => {
      query.mockRejectedValueOnce({ code, detail: "private-database-internals" });
      const response = await handleSchool(request(grade));
      expect(response.status).toBe(status);
      expect(await response.text()).not.toContain("private-database-internals");
    },
  );
  it("returns AI drafts only after scoped authorization and never publishes them", async () => {
    vi.mocked(queueInference).mockResolvedValue({
      title: task.title,
      goal: task.goal,
      instructions: task.instructions,
      factors: task.factors,
      subject: "matematicas",
      suggested: true,
    });
    const response = await handleSchool(
      request({
        action: "suggest-assignment",
        requestId: nonce,
        classId: classroom,
        topic: "Comprender grupos iguales",
        count: 2,
      }),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ suggested: true, factors: task.factors });
    expect(query.mock.calls.some((call) => call[0].join("").includes("school_command("))).toBe(
      false,
    );
    expect(queueInference).toHaveBeenCalledWith(
      "/proposal",
      expect.objectContaining({ count: 2 }),
      { classId: classroom },
    );
  });
  it("does not fabricate a draft or assignment when inference is unavailable", async () => {
    vi.mocked(queueInference).mockRejectedValue(new InferenceUnavailable("unavailable"));
    const response = await handleSchool(
      request({
        action: "suggest-assignment",
        requestId: nonce,
        classId: classroom,
        topic: "Agrupaciones iguales",
      }),
    );
    expect(response.status).toBe(503);
    expect(query).toHaveBeenCalledTimes(1);
    expect(await response.text()).toContain("no se ha publicado nada");
  });
});
