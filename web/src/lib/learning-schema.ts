import { z } from "zod";
export const learnerInput = z.object({
  id: z.string().uuid().optional(),
  display_name: z.string().trim().min(1).max(60),
  education_level: z.enum(["Primaria", "Secundaria", "Bachillerato", "Universidad"]),
  grade_level: z.string().max(30),
  age_band: z.enum(["6–8", "9–12", "12–13", "14–17", "18+"]),
  color: z.enum(["sunburst", "mint", "lavender", "ember"]),
  ia: z.boolean().default(false),
});
export const signupAge = z.literal("18+");
export const sceneSchema = z.object({
  version: z.literal(1),
  intro: z.string(),
  goal: z.string(),
  hints: z.array(z.string()),
  planets: z.array(z.object({ name: z.string(), detail: z.string() })).optional(),
});
export const activityConfig = z.object({
  total: z.number().int().min(2).max(12).optional(),
  target: z.string().optional(),
  options: z.array(z.string()).optional(),
});
export const tones: Record<string, string> = {
  sunburst: "bg-sunburst",
  mint: "bg-mint",
  lavender: "bg-lavender",
  ember: "bg-ember",
};
