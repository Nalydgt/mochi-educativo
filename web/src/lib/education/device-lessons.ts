import { z } from "zod";

const factor = z.number().int().min(1).max(12);
export const deviceLessonAssignmentSchema = z.object({
  action: z.literal("assign-device-lesson"),
  learnerId: z.string().uuid(),
  title: z
    .string()
    .trim()
    .min(3)
    .max(80, "El título es demasiado largo para Mochi. Prueba con un título más breve.")
    .refine(
      (value) => new TextEncoder().encode(value).length <= 80,
      "El título es demasiado largo para Mochi. Prueba con un título más breve.",
    ),
  subject: z.literal("matematicas"),
  goal: z.string().trim().min(8).max(300),
  instructions: z
    .string()
    .trim()
    .min(8)
    .max(200, "Las instrucciones son demasiado largas para Mochi. Resume la consigna.")
    .refine(
      (value) => new TextEncoder().encode(value).length <= 200,
      "Las instrucciones son demasiado largas para Mochi. Resume la consigna.",
    ),
  dueAt: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .refine((v) => {
      const date = new Date(v + "T00:00:00Z");
      return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === v;
    }, "Fecha no válida"),
  factors: z
    .array(z.tuple([factor, factor]))
    .min(1)
    .max(5),
});

export const deviceLessonResultSchema = z
  .object({
    resultId: z.string().uuid(),
    lessonId: z.string().uuid(),
    assignmentId: z.string().uuid(),
    completed: z.literal(true),
    attempts: z.number().int().min(1).max(40),
    hints: z.number().int().min(0).max(40),
    elapsedSeconds: z.number().int().min(0).max(86400),
    detailsShared: z.boolean().optional(),
    completedCount: z.number().int().min(1).max(5).optional(),
    answers: z
      .array(
        z.object({
          a: factor,
          b: factor,
          choice: z.number().int().min(0).max(144),
          correct: z.boolean(),
        }),
      )
      .min(0)
      .max(40),
  })
  .superRefine((value, ctx) => {
    if (value.detailsShared === false) {
      if (value.answers.length || !value.completedCount || value.attempts < value.completedCount)
        ctx.addIssue({
          code: "custom",
          path: ["answers"],
          message: "La entrega privada debe incluir sólo el número de ejercicios completados.",
        });
    } else if (value.attempts !== value.answers.length || !value.answers.length)
      ctx.addIssue({
        code: "custom",
        path: ["attempts"],
        message: "Los intentos no coinciden con las respuestas",
      });
  });

export type DeviceLessonResult = z.infer<typeof deviceLessonResultSchema>;

/** Recompute evidence against the assigned exercise order. Client correctness is never authoritative. */
export function evaluateDeviceLesson(factors: [number, number][], result: DeviceLessonResult) {
  if (result.detailsShared === false) {
    if (
      result.completedCount !== factors.length ||
      result.attempts < factors.length ||
      result.answers.length
    )
      throw new Error("La actividad aún no está completada.");
    return {
      ...result,
      answers: [],
      correctCount: factors.length,
      completedCount: factors.length,
      clientReported: true,
      detailsShared: false,
    };
  }
  let exercise = 0;
  const answers = result.answers.map((answer) => {
    const pair = factors[exercise];
    if (!pair || pair[0] !== answer.a || pair[1] !== answer.b)
      throw new Error("La respuesta no corresponde al ejercicio asignado.");
    const correct = answer.choice === answer.a * answer.b;
    if (correct) exercise++;
    return { a: answer.a, b: answer.b, choice: answer.choice, correct };
  });
  if (exercise !== factors.length) throw new Error("La actividad aún no está completada.");
  return {
    ...result,
    answers,
    correctCount: answers.filter((a) => a.correct).length,
    completedCount: factors.length,
    clientReported: false,
    detailsShared: true,
  };
}

export type DeviceLessonReport = {
  role: "teacher" | "family";
  lessons: {
    id: string;
    learnerId: string;
    learnerName: string;
    classId: string;
    title: string;
    goal: string;
    instructions: string;
    dueAt: string;
    createdAt: string;
    exerciseCount: number;
    result: null | {
      resultId: string;
      attempts: number;
      hints: number;
      elapsedSeconds: number;
      correctCount: number;
      receivedAt: string;
      answers: { a: number; b: number; choice: number; correct: boolean }[];
    };
  }[];
};
