import type { StudyFormat } from "./schema";

export type StudySurface = "aventura" | "mundos" | "preguntas" | "peluqo";
export type StudyContext = {
  surface: StudySurface;
  sessionId: string | null;
  activityId: string | null;
  format: StudyFormat | null;
};
export type AnalyticsMetrics = {
  visible_seconds: number;
  active_seconds: number;
  started: number;
  completed: number;
  attempts: number;
  graded: number;
  correct: number;
  exits: number;
  hints: number;
  tutor: number;
  logins: number;
  logouts: number;
  variants: number;
  visits: number;
  errors: number;
};
export type AnalyticsRow = AnalyticsMetrics & {
  day: string;
  hour: number;
  subject: string;
  game: string | null;
  difficulty: string | null;
  title?: string | null;
  version_id?: string | null;
  activity_id?: string | null;
};
export type AnalyticsCatalog = {
  version_id: string;
  subject: string;
  id: string;
  title: string;
  game: string;
  difficulty: string | null;
};
export type AnalyticsData = {
  role: "teacher" | "family" | "admin";
  rows: AnalyticsRow[];
  catalog: AnalyticsCatalog[];
};
