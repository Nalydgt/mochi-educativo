import { createServerFn } from "@tanstack/react-start";
import { createClient } from "@supabase/supabase-js";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import type { Database } from "@/integrations/supabase/types";
import { learnerInput, sceneSchema, activityConfig } from "./learning-schema";
export const catalogue = createServerFn({ method: "GET" }).handler(async () => {
  const key = process.env["SUPABASE_PUBLISHABLE_KEY"];
  const url = process.env["SUPABASE_URL"];
  if (!key || !url) throw new Error("Cloud no disponible");
  const db = createClient<Database>(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: {
      fetch: (input, init) => {
        const h = new Headers(init?.headers);
        if (h.get("Authorization") === `Bearer ${key}`) h.delete("Authorization");
        h.set("apikey", key);
        return fetch(input, { ...init, headers: h });
      },
    },
  });
  const [s, t, l, a] = await Promise.all([
    db.from("subjects").select("*").order("display_order"),
    db.from("topics").select("*").order("display_order"),
    db.from("lessons").select("*").eq("status", "published"),
    db.from("activities").select("*").order("display_order"),
  ]);
  for (const r of [s, t, l, a]) if (r.error) throw new Error("No se pudo cargar el catálogo");
  return {
    subjects: s.data ?? [],
    topics: t.data ?? [],
    lessons: (l.data ?? []).map((x) => ({ ...x, content: sceneSchema.parse(x.content) })),
    activities: (a.data ?? []).map((x) => ({
      ...x,
      public_config: activityConfig.parse(x.public_config),
    })),
  };
});
export const accountData = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const db = context.supabase;
    const [p, l, r, b, at, roles] = await Promise.all([
      db.from("profiles").select("*").eq("id", context.userId).single(),
      db.from("learners").select("*").order("created_at"),
      db.from("lesson_progress").select("*,lessons(title,slug)"),
      db.from("learner_achievements").select("*,achievements(title)"),
      db
        .from("activity_attempts")
        .select("id,learner_id,score,created_at")
        .order("created_at", { ascending: false })
        .limit(1000),
      db.from("user_roles").select("role"),
    ]);
    for (const x of [p, l, r, b, at, roles])
      if (x.error) throw new Error("No se pudo cargar tu cuenta");
    return {
      profile: p.data,
      learners: l.data ?? [],
      progress: r.data ?? [],
      badges: b.data ?? [],
      attempts: at.data ?? [],
      admin: roles.data?.some((x) => x.role === "admin") ?? false,
    };
  });
export const saveLearner = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(learnerInput)
  .handler(async ({ data, context }) => {
    const row = {
      display_name: data.display_name,
      education_level: data.education_level,
      grade_level: data.grade_level,
      age_band: data.age_band,
      avatar_config: { color: data.color },
      preferences: { ia: data.ia },
      owner_user_id: context.userId,
    };
    const q = data.id
      ? context.supabase.from("learners").update(row).eq("id", data.id)
      : context.supabase.from("learners").insert(row);
    const r = await q.select().single();
    if (r.error) throw new Error("No se pudo guardar el perfil");
    return r.data;
  });
export const selectLearner = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(z.object({ id: z.string().uuid() }))
  .handler(async ({ data, context }) => {
    const r = await context.supabase
      .from("profiles")
      .update({ active_learner_id: data.id })
      .eq("id", context.userId);
    if (r.error) throw new Error("Perfil no autorizado");
    return { ok: true };
  });
export const saveAccount = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(z.object({ display_name: z.string().trim().min(1).max(60) }))
  .handler(async ({ data, context }) => {
    const r = await context.supabase.from("profiles").update(data).eq("id", context.userId);
    if (r.error) throw new Error("No se pudo guardar");
    return { ok: true };
  });
export const evaluate = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(
    z.object({
      learner: z.string().uuid(),
      activity: z.string().uuid(),
      answer: z.union([
        z.object({ selected: z.number().int().min(0).max(12) }).strict(),
        z.object({ option: z.number().int().min(0).max(20) }).strict(),
      ]),
    }),
  )
  .handler(async ({ data, context }) => {
    const r = await context.supabase.rpc("evaluate_activity", {
      p_learner: data.learner,
      p_activity: data.activity,
      p_answer: data.answer,
    });
    if (r.error) throw new Error(r.error.message);
    return z
      .object({
        correct: z.boolean(),
        points: z.number(),
        progress: z.number(),
        explanation: z.string(),
      })
      .parse(r.data);
  });
