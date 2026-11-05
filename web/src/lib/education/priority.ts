import { z } from "zod";
import { subjectSchema } from "./schema";

export const prioritySchema = z.object({
  subject: subjectSchema.nullable(),
  goal: z.enum(["balanced", "support", "stretch"]),
});
export type StudyPriority = z.infer<typeof prioritySchema>;
