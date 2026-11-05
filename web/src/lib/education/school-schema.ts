import { z } from "zod";
import { deviceLessonAssignmentSchema } from "./device-lessons";

const identity = z.string().uuid();
const request = { requestId: identity };
const recipients = {
  classId: identity.optional(),
  learnerIds: z.array(identity).min(1).max(200).optional(),
};
const clock = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Hora no válida");
const iso = z.string().datetime({ offset: true });
const timezone = z
  .string()
  .min(3)
  .max(64)
  .refine((value) => {
    try {
      new Intl.DateTimeFormat("es", { timeZone: value });
      return true;
    } catch {
      return false;
    }
  }, "Zona horaria no válida");
const target = (value: { classId?: string | undefined; learnerIds?: string[] | undefined }) =>
  !!value.classId || !!value.learnerIds?.length;

export const schoolSettingsSchema = z.object({
  learnerId: identity,
  dailyMinutes: z.number().int().min(5).max(120),
  startTime: clock,
  endTime: clock,
  timezone: timezone.default("Europe/Madrid"),
  language: z.enum(["es", "en", "pt"]),
  voiceEnabled: z.boolean(),
  captionsEnabled: z.boolean().default(true),
  textFirst: z.boolean().default(false),
  sharePractice: z.boolean(),
  reminderMinutes: z.number().int().min(5).max(60).nullable().optional(),
  familySupportAlertsEnabled: z.boolean().optional(),
});

const groupMemberSchema = z.object({
  learnerId: identity,
  peerRole: z.enum(["member", "helper"]),
  voluntary: z.boolean(),
  buddyAlias: z
    .string()
    .trim()
    .min(1)
    .max(16)
    .regex(/^[\p{L}\p{N} _-]+$/u)
    .optional(),
});
export const supportSignalSchema = z
  .object({
    action: z.literal("support-signal"),
    signalId: identity,
    category: z.literal("possible_peer_bullying"),
    source: z.enum(["daily_voice", "lesson_voice"]),
    schoolPeerContext: z.literal(true),
    childConfirmed: z.literal(true),
  })
  .strict();

const assignmentFields = deviceLessonAssignmentSchema.omit({ action: true, learnerId: true });
export const suggestedAssignmentSchema = assignmentFields
  .omit({ dueAt: true })
  .extend({ suggested: z.literal(true) });

export const schoolCommandSchema = z
  .discriminatedUnion("action", [
    assignmentFields.extend({ ...request, ...recipients, action: z.literal("batch-assign") }),
    z.object({
      ...request,
      action: z.literal("review-lesson"),
      assignmentId: identity,
      status: z.enum(["reviewed", "needs_support"]),
      observation: z.string().trim().min(1).max(2000),
      publish: z.boolean(),
    }),
    z.object({
      ...request,
      action: z.literal("save-grade"),
      gradeId: identity.optional(),
      learnerId: identity,
      assignmentId: identity.nullable().optional(),
      subject: z.string().trim().min(2).max(80),
      title: z.string().trim().min(3).max(120),
      value: z.number().min(0).max(10),
      feedback: z.string().trim().max(2000),
      publish: z.boolean(),
      expectedRevision: z.number().int().positive().optional(),
    }),
    z.object({
      ...request,
      ...recipients,
      action: z.literal("send-message"),
      title: z.string().trim().min(3).max(160),
      body: z.string().trim().min(1).max(6000),
      allowReplies: z.boolean(),
    }),
    z.object({
      ...request,
      action: z.literal("reply-message"),
      messageId: identity,
      learnerId: identity,
      body: z.string().trim().min(1).max(3000),
    }),
    z.object({ ...request, action: z.literal("mark-message-read"), messageId: identity }),
    z.object({
      ...request,
      ...recipients,
      action: z.literal("save-event"),
      eventId: identity.optional(),
      title: z.string().trim().min(3).max(160),
      description: z.string().trim().max(3000),
      kind: z.enum(["meeting", "exam", "outing", "school"]),
      startsAt: iso,
      endsAt: iso.nullable().optional(),
    }),
    schoolSettingsSchema.extend({
      ...request,
      action: z.literal("save-settings"),
      expectedRevision: z.number().int().nonnegative().optional(),
    }),
    z.object({
      ...request,
      action: z.literal("save-profile"),
      learnerId: identity,
      ageBand: z.enum(["6–8", "9–12", "13–15", "16–18"]),
      gradeLabel: z.string().trim().max(80),
    }),
    z.object({ ...request, action: z.literal("delete-event"), eventId: identity }),
    z.object({ ...request, action: z.literal("withdraw-message"), messageId: identity }),
    z.object({ ...request, action: z.literal("withdraw-grade"), gradeId: identity }),
    z.object({
      ...request,
      action: z.literal("suggest-assignment"),
      classId: identity,
      topic: z.string().trim().min(4).max(400),
      count: z.number().int().min(1).max(5).default(3),
    }),
    z.object({
      ...request,
      action: z.literal("review-care-alert"),
      alertId: identity,
      status: z.enum(["reviewed", "dismissed"]),
    }),
    z.object({
      ...request,
      action: z.literal("save-group"),
      groupId: identity.optional(),
      classId: identity,
      name: z.string().trim().min(2).max(60),
      members: z.array(groupMemberSchema).min(2).max(8),
      expectedRevision: z.number().int().positive().optional(),
    }),
    z.object({
      ...request,
      action: z.literal("archive-group"),
      groupId: identity,
      expectedRevision: z.number().int().positive(),
    }),
    assignmentFields.extend({ ...request, action: z.literal("assign-group"), groupId: identity }),
    z.object({
      ...request,
      action: z.literal("confirm-help"),
      assignmentId: identity,
      helpedLearnerId: identity,
    }),
  ])
  .superRefine((value, ctx) => {
    if (
      (value.action === "batch-assign" ||
        value.action === "send-message" ||
        value.action === "save-event") &&
      !target(value)
    )
      ctx.addIssue({
        code: "custom",
        path: ["learnerIds"],
        message: "Selecciona una clase o al menos un alumno.",
      });
    if (
      value.action === "save-event" &&
      value.endsAt &&
      new Date(value.endsAt) <= new Date(value.startsAt)
    )
      ctx.addIssue({
        code: "custom",
        path: ["endsAt"],
        message: "La fecha de fin debe ser posterior al inicio.",
      });
    if (value.action === "save-grade" && value.gradeId && !value.expectedRevision)
      ctx.addIssue({
        code: "custom",
        path: ["expectedRevision"],
        message: "Recarga la calificación antes de editarla.",
      });
    if (value.action === "save-settings" && value.startTime === value.endTime)
      ctx.addIssue({
        code: "custom",
        path: ["endTime"],
        message: "Elige un horario con inicio y fin diferentes.",
      });
    if (value.action === "save-group") {
      if (value.groupId && !value.expectedRevision)
        ctx.addIssue({
          code: "custom",
          path: ["expectedRevision"],
          message: "Recarga el grupo antes de editarlo.",
        });
      if (new Set(value.members.map((member) => member.learnerId)).size !== value.members.length)
        ctx.addIssue({
          code: "custom",
          path: ["members"],
          message: "Cada alumno debe aparecer una sola vez.",
        });
      if (value.members.some((member) => member.peerRole === "helper" && !member.voluntary))
        ctx.addIssue({
          code: "custom",
          path: ["members"],
          message: "El papel de ayuda requiere participación voluntaria.",
        });
    }
  });

export type SchoolCommand = z.infer<typeof schoolCommandSchema>;
export type SchoolSettings = z.infer<typeof schoolSettingsSchema> & {
  revision: number;
  updatedAt: string | null;
  updatedBy: string | null;
};
export type SchoolReview = {
  status: "reviewed" | "needs_support";
  observation: string;
  reviewedAt: string;
  publishedAt: string | null;
  authorName: string;
};
export type SchoolResult = {
  resultId: string;
  attempts: number;
  hints: number;
  elapsedSeconds: number;
  correctCount: number;
  receivedAt: string;
  completedCount: number;
  detailsShared: boolean;
  clientReported: boolean;
  answers: { a: number; b: number; choice: number; correct: boolean }[];
};
export type SchoolLesson = {
  id: string;
  lessonId: string;
  learnerId: string;
  classId: string;
  learnerName: string;
  title: string;
  subject: string;
  goal: string;
  instructions: string;
  dueAt: string;
  factors: [number, number][];
  createdAt: string;
  result: SchoolResult | null;
  review: SchoolReview | null;
  groupId?: string | null;
  groupBatchId?: string | null;
  peerRole?: "member" | "helper" | null;
  childBuddyAlias?: string | null;
};
export type SchoolCareAlert = {
  id: string;
  learnerId: string;
  category: "possible_peer_bullying";
  createdAt: string;
  status: "pending_review" | "reviewed" | "dismissed";
  reviewedAt: string | null;
};
export type SchoolGroup = {
  id: string;
  classId: string;
  name: string;
  revision: number;
  archivedAt: string | null;
  members: {
    learnerId: string;
    peerRole: "member" | "helper";
    voluntary: boolean;
    buddyAlias: string | null;
  }[];
};
export type SchoolPoint = {
  id: string;
  learnerId: string;
  points: 10 | 20 | 5;
  reason: "review" | "group" | "help";
  sourceId: string;
  createdAt: string;
};
export type SchoolGrade = {
  id: string;
  learnerId: string;
  assignmentId: string | null;
  subject: string;
  title: string;
  value: number;
  scale: 10;
  feedback: string;
  authorName: string;
  publishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  revision: number;
};
export type SchoolMessage = {
  id: string;
  title: string;
  body: string;
  authorName: string;
  createdAt: string;
  allowReplies: boolean;
  learnerIds: string[];
  readAt: string | null;
  readCount: number;
  withdrawnAt: string | null;
  replies: {
    id: string;
    learnerId: string;
    body: string;
    authorName: string;
    own: boolean;
    createdAt: string;
  }[];
};
export type SchoolEvent = {
  id: string;
  classId: string | null;
  learnerIds: string[];
  title: string;
  description: string;
  kind: "meeting" | "exam" | "outing" | "school";
  startsAt: string;
  endsAt: string | null;
  createdAt: string;
  authorName: string;
  cancelledAt: string | null;
};
export type SchoolSnapshot = {
  role: "teacher" | "family";
  adult: { id: string; name: string };
  classes: { id: string; name: string }[];
  learners: {
    id: string;
    name: string;
    classId: string;
    ageBand: "6–8" | "9–12" | "13–15" | "16–18";
    gradeLabel: string;
  }[];
  lessons: SchoolLesson[];
  grades: SchoolGrade[];
  messages: SchoolMessage[];
  events: SchoolEvent[];
  devices: { id: string; learnerId: string | null; revoked: boolean; lastSeenAt: string | null }[];
  settings: SchoolSettings[];
  materials: { id: string; classId: string; name: string; createdAt: string }[];
  careAlerts?: SchoolCareAlert[];
  groups?: SchoolGroup[];
  points?: SchoolPoint[];
};
