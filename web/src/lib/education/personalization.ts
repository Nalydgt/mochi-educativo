import { z } from "zod";
import { activityTypes } from "./schema";

export const learnerAgeBands = ["6–8", "9–12", "13–15", "16–18"] as const;
export const learnerGuides = {
  peluqo: "Peluqo",
  frog: "Rana de la reserva",
  fish: "Pez del río",
} as const;
export const learnerGoals = {
  explore: { label: "Resuelve tres retos", total: 3 },
  practice: { label: "Resuelve tres retos sin pistas", total: 3 },
  finish: { label: "Termina una aventura", total: 1 },
} as const;

export const learnerPreferencesSchema = z.object({
  ageBand: z.enum(learnerAgeBands).default("9–12"),
  theme: z.enum(["reserve", "space", "workshop"]).default("reserve"),
  guide: z.enum(["peluqo", "frog", "fish"]).default("peluqo"),
  goal: z.enum(["explore", "practice", "finish"]).default("explore"),
  mechanics: z
    .array(z.enum(activityTypes))
    .max(3)
    .refine((items) => new Set(items).size === items.length)
    .default([]),
});
export type LearnerPreferences = z.infer<typeof learnerPreferencesSchema>;
export const defaultLearnerPreferences = learnerPreferencesSchema.parse({});

export type LearnerMilestones = { discoveries: number; completed: number; unaided?: number };

export function personalGoalProgress(
  goal: LearnerPreferences["goal"],
  progress: LearnerMilestones,
) {
  const metrics = {
    explore: progress.discoveries,
    practice: progress.unaided,
    finish: progress.completed,
  };
  const { label, total } = learnerGoals[goal];
  const actual = metrics[goal];
  return { label, total, completed: actual === undefined ? null : Math.min(actual, total) };
}
