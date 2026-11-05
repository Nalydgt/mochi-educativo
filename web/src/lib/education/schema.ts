import { z } from "zod";
import { deviceLessonAssignmentSchema } from "./device-lessons";

export const colors = ["sunburst", "mint", "lavender", "ember"] as const;
export const assets = [
  "fish",
  "frog",
  "turtle",
  "bird",
  "dolphin",
  "cat",
  "moon",
  "plant",
  "shapes",
  "timeline",
  "human",
] as const;
export const worldThemes = {
  reserve: "Reserva natural",
  space: "Observatorio",
  workshop: "Taller de ideas",
} as const;
export const activityTypes = [
  "question",
  "classification",
  "anatomy",
  "matching",
  "sequence",
  "memory",
  "puzzle",
  "listening",
  "manipulatives",
  "lab",
] as const;
export const activityLabels: Record<(typeof activityTypes)[number], string> = {
  question: "Observa y responde",
  classification: "Clasifica el mundo",
  anatomy: "Coloca las piezas",
  matching: "Une y relaciona",
  sequence: "Ordena la secuencia",
  memory: "Memoria de parejas",
  puzzle: "Reconstruye el puzle",
  listening: "Escucha y descubre",
  manipulatives: "Matemáticas manipulativas",
  lab: "Laboratorio científico",
};
export const subjects = {
  ciencias: "Ciencias",
  matematicas: "Matemáticas",
  lengua: "Lengua e idiomas",
  historia: "Historia",
  geografia: "Geografía",
  otros: "Otras materias",
} as const;
export const difficulties = {
  intro: "Introducción",
  core: "Práctica",
  challenge: "Desafío",
} as const;
export const educationAgeBands = ["6–8", "9–12", "13–15", "16–18"] as const;
export const subjectSchema = z.enum([
  "ciencias",
  "matematicas",
  "lengua",
  "historia",
  "geografia",
  "otros",
]);
export const difficultySchema = z.enum(["intro", "core", "challenge"]);
export const puzzlePictures = {
  reserve: "La reserva",
  space: "El observatorio",
  workshop: "El taller",
} as const;
export const puzzleTiles = ["hoja", "luna", "rio", "sol"] as const;
export const puzzleSlots = ["noroeste", "noreste", "suroeste", "sureste"] as const;
export const circuitParts = ["battery", "switch"] as const;
export const audioSamples = ["a17", "b29", "c43"] as const;
export const audioLabels: Record<(typeof audioSamples)[number], string> = {
  a17: "Llamada de rana",
  b29: "Lluvia",
  c43: "Flauta",
};
const activityId = z.string().regex(/^[a-z0-9_-]{1,48}$/);
export const referenceSchema = z.object({
  chunkId: z.string().uuid(),
  page: z.number().int().positive().nullable(),
});
const label = z.string().trim().min(1).max(180);
export const activitySchema = z
  .object({
    id: activityId,
    type: z.enum(activityTypes),
    title: label,
    instruction: z.string().trim().min(8).max(1200),
    competency: label,
    difficulty: difficultySchema.optional(),
    asset: z.enum(assets).default("fish"),
    puzzlePicture: z.enum(["reserve", "space", "workshop"]).optional(),
    stock: z.number().int().min(1).max(24).optional(),
    experiment: z.literal("circuit").optional(),
    choices: z
      .array(
        z.object({
          id: label,
          label,
          asset: z.enum(assets).optional(),
          sample: z.enum(audioSamples).optional(),
          x: z.number().min(0).max(100).optional(),
          y: z.number().min(0).max(100).optional(),
        }),
      )
      .min(2)
      .max(25),
    pieces: z
      .array(
        z.object({
          id: label,
          label,
          asset: z.enum(assets).optional(),
          tile: z.enum(puzzleTiles).optional(),
          sample: z.enum(audioSamples).optional(),
        }),
      )
      .max(12)
      .default([]),
    answer: z
      .record(z.string().max(180))
      .refine((v) => Object.keys(v).length > 0, "Falta la solución"),
    hints: z.array(z.string().min(1).max(600)).min(1).max(4),
    explanation: z.string().min(8).max(1200),
    sources: z.array(referenceSchema).min(1).max(6),
  })
  .superRefine((a, ctx) => {
    const keys = a.type === "question" ? ["choice"] : a.pieces.map((p) => p.id);
    if (
      new Set(keys).size !== keys.length ||
      new Set(a.choices.map((c) => c.id)).size !== a.choices.length ||
      (a.type !== "question" && !keys.length) ||
      Object.keys(a.answer).length !== keys.length ||
      keys.some((k) => !Object.hasOwn(a.answer, k) || !a.choices.some((c) => c.id === a.answer[k]))
    )
      ctx.addIssue({ code: "custom", message: "Piezas, destinos y solución no coinciden" });
    if (a.type === "anatomy" && a.choices.some((c) => c.x === undefined || c.y === undefined))
      ctx.addIssue({ code: "custom", message: "Las zonas anatómicas necesitan posición" });
    if (a.type !== "manipulatives" && a.choices.length > 8)
      ctx.addIssue({ code: "custom", message: "Este juego admite hasta ocho destinos" });
    if (
      ["matching", "memory", "sequence"].includes(a.type) &&
      (a.pieces.length < 2 ||
        a.choices.length !== a.pieces.length ||
        new Set(Object.values(a.answer)).size !== a.pieces.length)
    )
      ctx.addIssue({ code: "custom", message: "Cada pieza necesita un destino distinto" });
    if (
      a.type === "puzzle" &&
      (!a.puzzlePicture ||
        a.choices.length !== 4 ||
        a.pieces.length !== 4 ||
        puzzleSlots.some((id) => !a.choices.some((c) => c.id === id)) ||
        puzzleTiles.some(
          (tile, i) => !a.pieces.some((p) => p.tile === tile && a.answer[p.id] === puzzleSlots[i]),
        ))
    )
      ctx.addIssue({
        code: "custom",
        message: "El puzle necesita las cuatro piezas de una ilustración del catálogo",
      });
    if (
      a.type === "manipulatives" &&
      (!a.stock ||
        a.choices.length !== a.stock + 1 ||
        a.choices.some((c, i) => c.id !== String(i)) ||
        Object.values(a.answer).reduce((sum, value) => sum + Number(value), 0) > a.stock)
    )
      ctx.addIssue({
        code: "custom",
        message: "La distribución debe caber en la cantidad de fichas",
      });
    if (
      a.type === "lab" &&
      (a.experiment !== "circuit" ||
        a.choices.length !== 2 ||
        !["off", "on"].every((id) => a.choices.some((c) => c.id === id)) ||
        a.pieces.length !== circuitParts.length ||
        !circuitParts.every((id) => keys.includes(id)))
    )
      ctx.addIssue({ code: "custom", message: "El circuito necesita una pila y un interruptor" });
  });
export const worldSchema = z.object({
  theme: z.enum(["reserve", "space", "workshop"]),
  view: z.enum(["map", "3d"]),
  stations: z
    .array(
      z.object({
        activityId,
        title: label,
        observation: z.string().trim().max(420).default(""),
      }),
    )
    .min(3)
    .max(9),
});
export type World = z.infer<typeof worldSchema>;

export function defaultWorld(
  activities: Pick<Activity, "id" | "title" | "type">[],
  reserve = false,
): World {
  const reserveNames = {
    classification: "Reserva de animales",
    anatomy: "Laboratorio del pez",
    question: "Laguna de las ranas",
  };
  return {
    theme: "reserve",
    view: "map",
    stations: activities.map((a) => ({
      activityId: a.id,
      title:
        reserve && a.type in reserveNames
          ? reserveNames[a.type as keyof typeof reserveNames]
          : a.title,
      observation: "",
    })),
  };
}

export const missionSchema = z
  .object({
    title: label,
    intro: z.string().min(8).max(1800),
    ageBand: z.enum(educationAgeBands),
    course: z.string().trim().min(1).max(90).optional(),
    subject: subjectSchema.optional(),
    diagnostic: z.array(activitySchema).min(2).max(6),
    practice: z.array(activitySchema).min(3).max(9),
    final: z.array(activitySchema).min(2).max(6),
    retention: z.array(activitySchema).min(2).max(6),
    world: worldSchema.optional(),
  })
  .superRefine((m, ctx) => {
    const all = [...m.diagnostic, ...m.practice, ...m.final, ...m.retention];
    if (new Set(all.map((a) => a.id)).size !== all.length)
      ctx.addIssue({
        code: "custom",
        message: "Cada actividad debe tener un identificador distinto",
      });
    if (new Set(m.practice.map((a) => a.type)).size < 2)
      ctx.addIssue({
        code: "custom",
        path: ["practice"],
        message: "La práctica necesita al menos dos mecánicas distintas",
      });
    const exams = [...m.diagnostic, ...m.final, ...m.retention];
    if (
      exams.some((a) => a.type !== "question") ||
      new Set(all.map((a) => a.instruction.toLocaleLowerCase("es").trim())).size !== all.length
    )
      ctx.addIssue({
        code: "custom",
        message: "Las evaluaciones y la práctica necesitan enunciados diferentes",
      });
    if (m.world) {
      const linked = new Set(m.world.stations.map((s) => s.activityId));
      if (
        linked.size !== m.world.stations.length ||
        linked.size !== m.practice.length ||
        m.practice.some((a) => !linked.has(a.id))
      )
        ctx.addIssue({
          code: "custom",
          path: ["world", "stations"],
          message: "Cada parada debe enlazar una actividad de práctica distinta",
        });
    }
  });
export type Mission = z.infer<typeof missionSchema>;
export type Activity = z.infer<typeof activitySchema>;
export type PublicActivity = Omit<Activity, "answer" | "hints" | "explanation">;
export function supportsCards(a: Pick<Activity, "type">) {
  return a.type === "question" || a.type === "classification" || a.type === "anatomy";
}
export type Phase = "diagnostic" | "practice" | "final" | "completed" | "retention";
export function isAssessment(phase: string | null | undefined) {
  return phase === "diagnostic" || phase === "final" || phase === "retention";
}
export type Companion = {
  name: string;
  color: (typeof colors)[number];
  accessory: "none" | "scarf" | "star";
};
export function publicActivity(a: Activity): PublicActivity {
  const { answer, hints, explanation, ...visible } = a;
  return visible;
}
export function checkAnswer(a: Activity, answer: Record<string, string>) {
  return (
    Object.keys(answer).length === Object.keys(a.answer).length &&
    Object.entries(a.answer).every(([k, v]) => Object.hasOwn(answer, k) && answer[k] === v)
  );
}
export function activitiesFor(m: Mission, phase: Phase) {
  return phase === "completed" ? [] : m[phase];
}
export function allowedAccessory(accessory: string, discoveries: number, completed: number) {
  return (
    accessory === "none" ||
    (accessory === "scarf" && discoveries >= 3) ||
    (accessory === "star" && completed >= 1)
  );
}
export const companionSchema = z.object({
  name: z.string().trim().min(1).max(32),
  color: z.enum(colors),
  accessory: z.enum(["none", "scarf", "star"]),
});
const id = z.string().uuid();
export const studyFormatSchema = z.enum(["board", "cards"]);
export type StudyFormat = z.infer<typeof studyFormatSchema>;
export const commandSchema = z.discriminatedUnion("action", [
  deviceLessonAssignmentSchema,
  z.object({
    action: z.literal("login"),
    code: z.string().trim().min(8).max(40),
    remember: z.boolean().default(false),
    learnerId: id.optional(),
  }),
  z.object({ action: z.literal("logout") }),
  z.object({ action: z.literal("create-class"), name: label }),
  z.object({
    action: z.literal("create-learner"),
    classId: id,
    name: z.string().trim().min(1).max(60),
  }),
  z.object({ action: z.literal("delete-learner"), learnerId: id }),
  z.object({ action: z.literal("document-source"), documentId: id }),
  z.object({ action: z.literal("issue-code"), learnerId: id }),
  z.object({ action: z.literal("issue-family-code"), learnerId: id }),
  z.object({ action: z.literal("revoke-family-access"), learnerId: id }),
  z.object({
    action: z.literal("generate"),
    classId: id,
    documentId: id,
    topic: z.string().trim().max(220).optional(),
  }),
  z.object({ action: z.literal("save-draft"), classId: id, mission: missionSchema }),
  z.object({ action: z.literal("publish"), classId: id }),
  z.object({ action: z.literal("start"), versionId: id }),
  z.object({
    action: z.literal("ask"),
    question: z.string().trim().min(1).max(1600),
    requestId: id,
  }),
  z.object({ action: z.literal("focus"), sessionId: id, activityId: z.string().max(48) }),
  z.object({
    action: z.literal("answer"),
    sessionId: id,
    activityId: z.string().max(48),
    requestId: id,
    answer: z.record(z.string().max(180)),
    studyFormat: studyFormatSchema.default("board"),
  }),
  z.object({ action: z.literal("hint"), sessionId: id, activityId: z.string().max(48) }),
  z.object({ action: z.literal("advance"), sessionId: id }),
  z.object({ action: z.literal("companion"), companion: companionSchema }),
  z.object({ action: z.literal("preferences"), preferences: z.unknown() }),
  z.object({
    action: z.literal("tutor"),
    sessionId: id,
    question: z.string().trim().min(1).max(1600),
    requestId: id,
  }),
  z.object({ action: z.literal("approve-pair"), code: z.string().trim().length(8), learnerId: id }),
  z.object({ action: z.literal("bind-device"), deviceId: id, sessionId: id.nullable() }),
  z.object({ action: z.literal("revoke-device"), deviceId: id }),
  z.object({ action: z.literal("override"), learnerId: id, support: z.boolean() }),
]);
