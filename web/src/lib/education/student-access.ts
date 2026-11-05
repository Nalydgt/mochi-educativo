import { z } from "zod";
import { colors } from "./schema";

export const accessDurations = {
  unlimited: "Sin caducidad",
  "24h": "24 horas",
  "7d": "7 días",
  "30d": "30 días",
  custom: "Fecha personalizada",
} as const;
const durationSchema = z.enum(["unlimited", "24h", "7d", "30d", "custom"]);
export type AccessDuration = z.infer<typeof durationSchema>;

const learnerId = z.string().uuid();
export const studentAccessCommand = z
  .object({
    learnerId,
    action: z.enum(["issue", "pause", "enable", "revoke"]),
    duration: durationSchema.optional(),
    expiresAt: z.string().datetime({ offset: true }).optional(),
  })
  .superRefine((value, context) => {
    if (
      value.action === "issue" &&
      (!value.duration || (value.duration === "custom" && !value.expiresAt))
    ) {
      context.addIssue({ code: "custom", message: "Elige la duración del código." });
    }
  });

export const studentAccessStatus = z.object({
  status: z.enum(["none", "active", "paused", "revoked", "expired", "used"]),
  expiresAt: z.string().nullable(),
  createdAt: z.string().nullable(),
});
export type StudentAccessStatus = z.infer<typeof studentAccessStatus>;

export const studentAccessProfile = z.object({
  id: learnerId,
  name: z.string().trim().min(1).max(60),
  color: z.enum(colors).catch("sunburst"),
});
export type StudentAccessProfile = z.infer<typeof studentAccessProfile>;
export type StudentAccessOptions = { remember: boolean; learnerId?: string };

export const normalizeStudentCode = (value: string) => value.replace(/[\s-]/g, "").toUpperCase();
export const displayStudentCode = (value: string) => value.match(/.{1,4}/g)?.join("-") ?? value;
