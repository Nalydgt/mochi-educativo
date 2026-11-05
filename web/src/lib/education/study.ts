import type { LearnerPreferences } from "./personalization";
import type { StudyPriority } from "./priority";
import type { PublicActivity, StudyFormat } from "./schema";

export type StudyAttempt = {
  session_id: string;
  activity_id: string;
  correct: boolean;
  hints: number;
  study_format: StudyFormat;
  competency?: string;
  game?: PublicActivity["type"];
};

export type StudyRecommendation = {
  format: StudyFormat;
  reason: "start" | "guided" | "retry" | "unassisted";
};

export function recommendStudyFormat(
  sessionId: string,
  activityId: string,
  guided: boolean,
  recent: readonly StudyAttempt[],
): StudyRecommendation {
  if (guided) return { format: "cards", reason: "guided" };
  const own = recent.filter((a) => a.session_id === sessionId && a.activity_id === activityId);
  const [latest, previous] = own;
  if (
    latest?.correct === false &&
    previous?.correct === false &&
    latest.study_format === previous.study_format
  ) {
    return { format: latest.study_format === "board" ? "cards" : "board", reason: "retry" };
  }
  const distinctUnassisted = new Set(
    recent
      .filter((a) => a.correct && a.hints === 0 && a.study_format === "cards")
      .map((a) => `${a.session_id}:${a.activity_id}`),
  );
  if (distinctUnassisted.size >= 2) return { format: "cards", reason: "unassisted" };
  return { format: "board", reason: "start" };
}

export type SuggestedActivity = { activityId: string; reason: string };

export function recommendActivities(
  sessionId: string,
  available: readonly PublicActivity[],
  recent: readonly StudyAttempt[],
  preferences: LearnerPreferences,
  priorities: readonly StudyPriority[],
  guided: boolean,
): SuggestedActivity[] {
  const current = recent.filter((a) => a.session_id === sessionId);
  const done = new Set(current.filter((a) => a.correct).map((a) => a.activity_id));
  const latestGame = recent[0]?.game;
  const repetition =
    latestGame !== undefined &&
    recent.slice(0, 3).filter((a) => a.game === latestGame).length === 3;
  const support = guided || priorities.some((p) => p.goal === "support");
  const stretch = !support && priorities.some((p) => p.goal === "stretch");
  const distinctUnaided = new Set(
    recent.filter((a) => a.correct && a.hints === 0).map((a) => `${a.session_id}:${a.activity_id}`),
  );
  const canStretch = distinctUnaided.size >= 2;

  const scored = available
    .filter((a) => !done.has(a.id))
    .map((activity) => {
      const same = recent.filter((a) => a.competency === activity.competency);
      const tried = current.filter((a) => a.activity_id === activity.id);
      const hasErrors = tried.length >= 2 && tried.every((a) => !a.correct);
      const reinforce = same.slice(0, 3).filter((a) => !a.correct || a.hints > 0).length >= 2;
      const favorite = preferences.mechanics.includes(activity.type);
      const skilled =
        new Set(
          recent
            .filter((a) => a.game === activity.type && a.correct && a.hints === 0)
            .map((a) => `${a.session_id}:${a.activity_id}`),
        ).size >= 2;
      const easier = activity.difficulty === "intro" && (support || preferences.ageBand === "6–8");
      const harder = activity.difficulty === "challenge" && canStretch && !support;
      const diversity = repetition && activity.type !== latestGame;
      let reason = "Continúa la aventura con un reto que todavía no has completado.";
      if (reinforce && !hasErrors)
        reason = "Practica un concepto que te costó en un reto diferente.";
      else if (hasErrors)
        reason = "Puedes volver a probar este reto con una pista o con otro formato.";
      else if (easier) reason = "Empieza por una práctica paso a paso para afianzar el tema.";
      else if (harder)
        reason = "Ya resolviste varios retos sin pistas. Prueba un desafío más exigente.";
      else if (skilled) reason = "Has completado varios retos con esta mecánica sin pistas.";
      else if (favorite) reason = "Elegiste este tipo de juego entre tus favoritos.";
      else if (diversity) reason = "Cambia de mecánica para practicar de otra manera.";
      const points =
        Number(reinforce && !hasErrors) * 7 +
        Number(hasErrors) * 3 +
        Number(easier) * 5 +
        Number(harder) * (stretch ? 6 : 3) +
        Number(skilled) * 3 +
        Number(favorite) * 2 +
        Number(diversity) * 2 -
        Number(activity.difficulty === "challenge" && !harder) * 4;
      return { activityId: activity.id, type: activity.type, reason, points };
    })
    .sort((a, b) => b.points - a.points);
  const first = scored[0];
  if (!first) return [];
  const second = scored.find((a) => a.type !== first.type) ?? scored[1];
  return [first, second].flatMap((item) =>
    item ? [{ activityId: item.activityId, reason: item.reason }] : [],
  );
}

type RecommendedWorld = {
  id: string;
  subject: string | null;
  theme: string;
  age_band: string | null;
};

export function recommendWorld(
  available: readonly RecommendedWorld[],
  started: readonly string[],
  preferences: LearnerPreferences,
  priorities: readonly StudyPriority[],
) {
  const assigned = new Set(priorities.flatMap((p) => (p.subject ? [p.subject] : [])));
  return (
    available
      .filter((w) => !started.includes(w.id))
      .map((w) => {
        const prioritized =
          w.subject !== null && assigned.has(w.subject as NonNullable<StudyPriority["subject"]>);
        const level = w.age_band === preferences.ageBand;
        const liked = w.theme === preferences.theme;
        return {
          versionId: w.id,
          reason: prioritized
            ? "Esta aventura trabaja una asignatura que tu adulto ha priorizado."
            : liked
              ? "Esta aventura usa uno de tus escenarios preferidos."
              : level
                ? "Esta aventura está preparada para tu tramo de edad."
                : "Tienes una aventura nueva disponible.",
          points: 6 * Number(prioritized) + 3 * Number(level) + 2 * Number(liked),
        };
      })
      .sort((a, b) => b.points - a.points)[0] ?? null
  );
}
