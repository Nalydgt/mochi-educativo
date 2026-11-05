import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import type { TransactionSql } from "postgres";
import { db } from "./db.server";

export type InferenceContext = { classId?: string; learnerId?: string };

export class InferenceUnavailable extends Error {
  constructor(readonly reason: "usage_limit" | "unavailable") {
    super("Educational inference unavailable");
  }
}

export async function queueInference(
  path: string,
  payload: unknown,
  context: InferenceContext = {},
) {
  const kind = path.slice(1);
  if (!["generate", "tutor", "curiosity", "proposal"].includes(kind))
    throw new Error("Unsupported inference job");
  const id = randomUUID();
  const service = <T>(work: (q: TransactionSql) => Promise<T>) =>
    db().begin(async (q) => {
      await q`select set_config('peluqo.service', 'true', true)`;
      return work(q);
    });
  await service(
    (q) => q`
      insert into education.inference_jobs (id, kind, payload, class_id, learner_id)
      values (${id}, ${kind}, ${JSON.stringify(payload)}::text::jsonb, ${context.classId ?? null}, ${context.learnerId ?? null})
    `,
  );
  try {
    const deadline = Date.now() + 175_000;
    while (Date.now() < deadline) {
      const [job] = await service(
        (q) => q<{ status: string; result: unknown }[]>`
          select status, result from education.inference_jobs where id=${id}
        `,
      );
      if (job?.status === "ready") return job.result;
      if (!job || job.status === "failed") {
        const limit =
          job?.result &&
          typeof job.result === "object" &&
          "error" in job.result &&
          job.result.error === "education_ai_usage_limit";
        throw new InferenceUnavailable(limit ? "usage_limit" : "unavailable");
      }
      await delay(1500);
    }
    throw new Error("Educational inference timed out");
  } finally {
    await service((q) => q`delete from education.inference_jobs where id=${id}`).catch(
      () => undefined,
    );
  }
}
