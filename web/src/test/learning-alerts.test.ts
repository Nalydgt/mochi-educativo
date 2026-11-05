import { describe, expect, it } from "vitest";
import { buildProgressDashboard, type ProgressSnapshot } from "@/lib/education/progress";

const day = (date: number) => new Date(Date.UTC(2026, 10, date)).toISOString();

const snapshot: ProgressSnapshot = {
  role: "teacher",
  pupils: [{ id: "child", name: "Iris", class_id: "class", class_name: "Aula", support: false }],
  worlds: [
    {
      id: "world",
      class_id: "class",
      title: "La reserva",
      published_at: day(1),
      diagnostic_total: 4,
      practice_total: 4,
      final_total: 4,
      retention_total: 4,
    },
  ],
  sessions: [
    {
      id: "session",
      learner_id: "child",
      version_id: "world",
      phase: "practice",
      created_at: day(1),
      completed_at: null,
      retention_completed_at: null,
      aids: 0,
    },
  ],
  evidence: [],
};
type Attempt = ProgressSnapshot["evidence"][number];
type Session = ProgressSnapshot["sessions"][number];

function attempt(
  id: string,
  correct: boolean | null,
  date: number,
  more: Partial<Attempt> = {},
): Attempt {
  return {
    session_id: "session",
    activity_id: id,
    correct,
    phase: "practice",
    competency: "Vertebrados",
    hints: 0,
    study_format: "board",
    created_at: day(date),
    ...more,
  };
}

function progress(evidence: Attempt[], session: Partial<Session> = {}, date = 6) {
  return buildProgressDashboard(
    { ...snapshot, sessions: [{ ...snapshot.sessions[0]!, ...session }], evidence },
    "teacher",
    Date.parse(day(date)),
  ).pupils[0]!.progress[0]!;
}

function examination(phase: "diagnostic" | "final" | "retention", correct: number, date: number) {
  return Array.from({ length: 4 }, (_, index) =>
    attempt(`${phase}-${index}`, index < correct, date, { phase }),
  );
}

describe("orientative learning signals", () => {
  it("uses repeated misses on an unresolved activity and removes the signal once it is resolved", () => {
    const evidence = [attempt("a", false, 1), attempt("a", false, 2)];
    expect(progress(evidence).status).toBe("support");
    expect(progress(evidence).alerts).toEqual([
      expect.objectContaining({ kind: "repeated_errors", title: "Reforzar Vertebrados" }),
    ]);
    expect(progress([...evidence, attempt("a", true, 3)]).alerts).toEqual([]);
  });

  it("counts aided practices separately and distinguishes a pause from recent stuck progress", () => {
    const aided = [
      attempt("a", true, 1, { hints: 2 }),
      attempt("b", true, 2, { hints: 1 }),
      attempt("c", true, 3),
    ];
    expect(progress(aided).alerts.map((alert) => alert.kind)).toEqual(["frequent_hints"]);
    expect(progress(aided, {}, 11).alerts.map((alert) => alert.kind)).toEqual([
      "frequent_hints",
      "inactive",
    ]);
    const unresolved = [attempt("a", false, 1), attempt("b", false, 5), attempt("b", false, 8)];
    expect(progress(unresolved, {}, 9).alerts.map((alert) => alert.kind)).toEqual([
      "repeated_errors",
      "stalled",
    ]);
  });

  it("waits for three completed stages with comparable competency coverage to flag a sustained drop", () => {
    const evidence = [
      ...examination("diagnostic", 4, 1),
      ...examination("final", 3, 2),
      ...examination("retention", 2, 9),
    ];
    const session = { phase: "retention" as const, completed_at: day(2) };
    expect(progress(evidence, session, 10).retention).toBeNull();
    expect(progress(evidence, session, 10).alerts).toEqual([]);
    const closed = { ...session, phase: "completed" as const, retention_completed_at: day(9) };
    expect(progress(evidence, closed, 10).alerts.map((alert) => alert.kind)).toEqual([
      "sustained_drop",
    ]);
    evidence[11] = { ...evidence[11]!, competency: "Otro concepto" };
    expect(progress(evidence, closed, 10).alerts).toEqual([]);
  });

  it("reports the difference between practice and a completed independent assessment", () => {
    const evidence = [
      attempt("a", true, 1),
      attempt("b", true, 1),
      attempt("c", true, 1),
      ...examination("final", 1, 2),
    ];
    expect(progress(evidence, { phase: "final" }).final).toBeNull();
    expect(progress(evidence, { phase: "final" }).alerts).toEqual([]);
    expect(
      progress(evidence, { phase: "completed", completed_at: day(2) }).alerts.map(
        (alert) => alert.kind,
      ),
    ).toEqual(["transfer"]);
  });
});
