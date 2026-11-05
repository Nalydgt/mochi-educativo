import type { Phase, StudyFormat } from "./schema";

export type ProgressRole = "teacher" | "family";
export type ProgressStatus = "not_started" | "working" | "support" | "inactive" | "complete";

type Pupil = {
  id: string;
  name: string;
  class_id: string;
  class_name: string;
  support: boolean;
};
type World = {
  id: string;
  class_id: string;
  title: string;
  published_at: string;
  diagnostic_total: number;
  practice_total: number;
  final_total: number;
  retention_total: number;
};
type Session = {
  id: string;
  learner_id: string;
  version_id: string;
  phase: Phase;
  created_at: string;
  completed_at: string | null;
  retention_completed_at: string | null;
  aids: number;
};
type Evidence = {
  session_id: string;
  activity_id: string;
  competency: string;
  phase: Phase;
  hints: number;
  study_format: StudyFormat;
  correct: boolean | null;
  created_at: string;
};
export type ProgressSnapshot = {
  role: ProgressRole | null;
  pupils: Pupil[];
  worlds: World[];
  sessions: Session[];
  evidence: Evidence[];
};

type Score = { correct: number; total: number };
export type SkillEvidence = {
  name: string;
  attempts: number;
  solved: number;
  unaided: number;
  needsSupport: boolean;
};
export type LearningAlert = {
  kind:
    "repeated_errors" | "frequent_hints" | "sustained_drop" | "stalled" | "inactive" | "transfer";
  title: string;
  detail: string;
  action: string;
};
export type WorldProgress = {
  worldId: string;
  status: ProgressStatus;
  phase: Phase | null;
  percent: number;
  discoveries: number;
  practiceTotal: number;
  responses: number;
  aids: number;
  lastActivity: string | null;
  diagnostic: Score | null;
  final: Score | null;
  retention: Score | null;
  retentionAt: string | null;
  skills: SkillEvidence[];
  formats: { format: StudyFormat; attempts: number; correct: number }[];
  alerts: LearningAlert[];
};
export type ProgressDashboardData = {
  role: ProgressRole;
  worlds: { id: string; classId: string; title: string; publishedAt: string }[];
  pupils: {
    id: string;
    name: string;
    classId: string;
    className: string;
    guided: boolean;
    progress: WorldProgress[];
  }[];
};

const day = 86_400_000;
const week = 7 * day;

function groupBy<T>(items: readonly T[], key: (item: T) => string) {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const k = key(item);
    const group = groups.get(k);
    if (group) group.push(item);
    else groups.set(k, [item]);
  }
  return groups;
}

function assessment(attempts: Evidence[], phase: Phase, total: number, closed: boolean) {
  const rows = [
    ...new Map(
      attempts
        .filter((a) => a.phase === phase && a.correct !== null)
        .map((a) => [a.activity_id, a]),
    ).values(),
  ];
  if (!closed || !total || rows.length !== total) return null;
  return {
    score: { total, correct: rows.filter((a) => a.correct).length },
    // Only compare stages with the same competency coverage.
    coverage: JSON.stringify(
      [...groupBy(rows, (a) => a.competency).entries()]
        .map(([competency, group]) => [competency, group.length])
        .sort(),
    ),
  };
}

function practiceSignals(practice: Evidence[], bySkill: Map<string, Evidence[]>, start: string) {
  const alerts: LearningAlert[] = [];
  for (const [name, attempts] of bySkill) {
    const unresolved = [...groupBy(attempts, (a) => a.activity_id).values()].filter(
      (rows) => rows.length >= 2 && rows.every((a) => a.correct === false),
    );
    if (unresolved.length) {
      const misses = unresolved.reduce((count, rows) => count + rows.length, 0);
      alerts.push({
        kind: "repeated_errors",
        title: `Reforzar ${name}`,
        detail: `${misses} intentos sin acierto en ${unresolved.length === 1 ? "un reto pendiente" : `${unresolved.length} retos pendientes`} de esta competencia.`,
        action:
          "Revisad un ejemplo paso a paso. Después, probad otro reto sobre el mismo concepto.",
      });
    }
  }

  const solved = [
    ...groupBy(
      practice.filter((a) => a.correct),
      (a) => a.activity_id,
    ).values(),
  ];
  const aided = solved.filter((rows) => rows.every((a) => a.hints > 0)).length;
  if (solved.length >= 3 && aided * 3 >= solved.length * 2) {
    alerts.push({
      kind: "frequent_hints",
      title: "Practicar con menos ayuda",
      detail: `Se usaron pistas en ${aided} de ${solved.length} retos resueltos.`,
      action:
        "Haced un ejemplo juntos y plantead un reto parecido que pueda intentar primero sin ayuda.",
    });
  }

  const lastDiscovery = practice.reduce(
    (latest, a) => (a.correct ? Math.max(latest, Date.parse(a.created_at)) : latest),
    Date.parse(start),
  );
  const pending = practice.filter(
    (a) => a.correct === false && Date.parse(a.created_at) >= lastDiscovery,
  );
  const span = pending.reduce(
    (range, a) => {
      const date = Date.parse(a.created_at);
      return { first: Math.min(range.first, date), last: Math.max(range.last, date) };
    },
    { first: Infinity, last: -Infinity },
  );
  if (
    pending.length >= 3 &&
    new Set(pending.map((a) => a.activity_id)).size >= 2 &&
    span.last - span.first >= week
  ) {
    alerts.push({
      kind: "stalled",
      title: "Retomar un objetivo pequeño",
      detail: `Hay ${pending.length} intentos en una semana o más desde el último avance registrado.`,
      action:
        "Elegid un único reto pendiente. Divididlo en dos pasos y comprobad juntos el primero.",
    });
  }
  return alerts;
}

function worldProgress(
  world: World,
  session: Session | undefined,
  evidence: Evidence[],
  now: number,
): WorldProgress {
  const practice = evidence.filter((a) => a.phase === "practice");
  const discoveries = new Set(practice.filter((a) => a.correct).map((a) => a.activity_id)).size;
  const answered = new Set(
    evidence
      .filter((a) => a.phase === "diagnostic" || a.phase === "final")
      .map((a) => a.activity_id),
  ).size;
  const bySkill = groupBy(practice, (a) => a.competency);
  const skills = [...bySkill.entries()].map(([name, rows]) => {
    const activities = [...groupBy(rows, (a) => a.activity_id).values()];
    return {
      name,
      attempts: rows.length,
      solved: activities.filter((attempts) => attempts.some((a) => a.correct)).length,
      unaided: activities.filter((attempts) => attempts.some((a) => a.correct && a.hints === 0))
        .length,
      needsSupport: activities.some(
        (attempts) => attempts.length >= 2 && attempts.every((a) => a.correct === false),
      ),
    };
  });
  const lastActivity = evidence.reduce<string | null>(
    (latest, entry) =>
      !latest || Date.parse(entry.created_at) > Date.parse(latest) ? entry.created_at : latest,
    session?.created_at ?? null,
  );
  const diagnostic = assessment(
    evidence,
    "diagnostic",
    world.diagnostic_total,
    !!session && session.phase !== "diagnostic",
  );
  const final = assessment(evidence, "final", world.final_total, !!session?.completed_at);
  const retention = assessment(
    evidence,
    "retention",
    world.retention_total,
    !!session?.retention_completed_at,
  );
  const alerts = session ? practiceSignals(practice, bySkill, session.created_at) : [];
  let status: ProgressStatus = "working";
  if (!session) status = "not_started";
  else if (session.completed_at) status = "complete";
  else if (alerts.length) status = "support";
  if (session && !session.completed_at && lastActivity && now - Date.parse(lastActivity) >= week) {
    if (status === "working") status = "inactive";
    const quietDays = Math.floor((now - Date.parse(lastActivity)) / day);
    alerts.push({
      kind: "inactive",
      title: "Una pausa en esta aventura",
      detail: evidence.length
        ? `Han pasado ${quietDays} días desde el último intento registrado.`
        : `Se abrió hace ${quietDays} días y todavía no hay respuestas registradas.`,
      action:
        "Proponed retomar un reto breve. Comprobad si el horario o el acceso están dificultando la participación.",
    });
  }

  if (
    diagnostic &&
    final &&
    retention &&
    diagnostic.score.total >= 4 &&
    diagnostic.coverage === final.coverage &&
    final.coverage === retention.coverage &&
    diagnostic.score.correct > final.score.correct &&
    final.score.correct > retention.score.correct
  ) {
    alerts.push({
      kind: "sustained_drop",
      title: "Revisar un descenso en los aciertos",
      detail: `Con las mismas competencias y ${diagnostic.score.total} preguntas por etapa, hubo ${diagnostic.score.correct} aciertos al inicio, ${final.score.correct} en el reto final y ${retention.score.correct} en el repaso.`,
      action:
        "Repasad una de esas competencias con otro ejemplo. Usad un ejercicio equivalente unos días después para ver si se mantiene el avance.",
    });
  }
  if (
    final &&
    final.score.total >= 4 &&
    final.score.correct * 2 < final.score.total &&
    discoveries >= 3 &&
    discoveries * 4 >= world.practice_total * 3
  ) {
    alerts.push({
      kind: "transfer",
      title: "Aplicar lo practicado a retos nuevos",
      detail: `Resolvió ${discoveries} de ${world.practice_total} retos de práctica y acertó ${final.score.correct} de ${final.score.total} preguntas en la evaluación final.`,
      action:
        "Pedidle explicar cómo resolvió un reto. Después, plantead dos ejemplos nuevos sobre el mismo concepto.",
    });
  }
  const formats = [...groupBy(practice, (a) => a.study_format).values()].map((rows) => ({
    format: rows[0]!.study_format,
    attempts: rows.length,
    correct: rows.filter((a) => a.correct).length,
  }));
  const total = world.diagnostic_total + world.practice_total + world.final_total;

  return {
    worldId: world.id,
    status,
    phase: session?.phase ?? null,
    percent: session?.completed_at
      ? 100
      : Math.min(100, Math.round((100 * (answered + discoveries)) / Math.max(1, total))),
    discoveries,
    practiceTotal: world.practice_total,
    responses: evidence.length,
    aids: session?.aids ?? 0,
    lastActivity,
    diagnostic: diagnostic?.score ?? null,
    final: final?.score ?? null,
    retention: retention?.score ?? null,
    retentionAt: session?.completed_at
      ? new Date(Date.parse(session.completed_at) + week).toISOString()
      : null,
    skills,
    formats,
    alerts,
  };
}

export function buildProgressDashboard(
  snapshot: ProgressSnapshot,
  role: ProgressRole,
  now = Date.now(),
): ProgressDashboardData {
  const bySession = groupBy(snapshot.evidence, (a) => a.session_id);
  const worldsByClass = groupBy(snapshot.worlds, (w) => w.class_id);
  const sessions = new Map(snapshot.sessions.map((s) => [`${s.learner_id}:${s.version_id}`, s]));
  return {
    role,
    worlds: snapshot.worlds.map((w) => ({
      id: w.id,
      title: w.title,
      classId: w.class_id,
      publishedAt: w.published_at,
    })),
    pupils: snapshot.pupils.map((p) => ({
      id: p.id,
      name: p.name,
      classId: p.class_id,
      className: p.class_name,
      guided: p.support,
      progress: (worldsByClass.get(p.class_id) ?? []).map((w) => {
        const session = sessions.get(`${p.id}:${w.id}`);
        return worldProgress(w, session, session ? (bySession.get(session.id) ?? []) : [], now);
      }),
    })),
  };
}
