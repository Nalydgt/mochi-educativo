import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { sceneSchema, activityConfig } from "./learning-schema";
export const adminData = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const role = await context.supabase.rpc("has_role", {
      _user_id: context.userId,
      _role: "admin",
    });
    if (!role.data) throw new Error("Acceso reservado a administradores");
    const [s, t, l, a] = await Promise.all([
      context.supabase.from("subjects").select("*").order("display_order"),
      context.supabase.from("topics").select("*").order("display_order"),
      context.supabase.from("lessons").select("*"),
      context.supabase.from("activities").select("*").order("display_order"),
    ]);
    for (const r of [s, t, l, a]) if (r.error) throw new Error("No se pudo cargar administración");
    return {
      subjects: s.data ?? [],
      topics: t.data ?? [],
      lessons: l.data ?? [],
      activities: a.data ?? [],
    };
  });
export const saveContent = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(
    z.object({
      kind: z.enum(["subject", "topic", "lesson", "activity"]),
      id: z.string().uuid().optional(),
      body: z.record(z.unknown()),
    }),
  )
  .handler(async ({ data, context }) => {
    const role = await context.supabase.rpc("has_role", {
      _user_id: context.userId,
      _role: "admin",
    });
    if (!role.data) throw new Error("No autorizado");
    const { supabaseAdmin: admin } = await import("@/integrations/supabase/client.server");
    const b = data.body;
    let id = data.id;
    if (data.kind === "subject") {
      const row = z
        .object({
          name: z.string().min(1),
          slug: z.string().regex(/^[a-z0-9-]+$/),
          description: z.string(),
          color: z.enum(["sunburst", "mint", "lavender", "ember"]),
          display_order: z.number().int(),
          is_active: z.boolean(),
        })
        .parse(b);
      const r = await (
        id
          ? context.supabase.from("subjects").update(row).eq("id", id)
          : context.supabase.from("subjects").insert(row)
      )
        .select()
        .single();
      if (r.error) throw new Error(r.error.message);
      id = r.data.id;
    }
    if (data.kind === "topic") {
      const row = z
        .object({
          title: z.string().min(1),
          slug: z.string(),
          subject_id: z.string().uuid(),
          description: z.string(),
          display_order: z.number().int(),
        })
        .parse(b);
      const r = await (
        id
          ? context.supabase.from("topics").update(row).eq("id", id)
          : context.supabase.from("topics").insert(row)
      )
        .select()
        .single();
      if (r.error) throw new Error(r.error.message);
      id = r.data.id;
    }
    if (data.kind === "lesson") {
      const row = z
        .object({
          title: z.string().min(1),
          slug: z.string(),
          topic_id: z.string().uuid(),
          description: z.string(),
          education_level: z.string(),
          estimated_minutes: z.number().int().min(1),
          status: z.enum(["draft", "published"]),
          content: sceneSchema,
        })
        .parse(b);
      if (row.status === "published") {
        if (!id) throw new Error("Guarda el borrador y añade actividades primero");
        const a = await admin.from("activities").select("id").eq("lesson_id", id);
        if (!a.data?.length) throw new Error("Añade una actividad antes de publicar");
        const sol = await admin
          .from("activity_solutions")
          .select("activity_id")
          .in(
            "activity_id",
            a.data.map((x) => x.id),
          );
        if (sol.data?.length !== a.data.length) throw new Error("Hay actividades sin solución");
      }
      const r = await (
        id
          ? context.supabase.from("lessons").update(row).eq("id", id)
          : context.supabase.from("lessons").insert(row)
      )
        .select()
        .single();
      if (r.error) throw new Error(r.error.message);
      id = r.data.id;
    }
    if (data.kind === "activity") {
      const row = z
        .object({
          lesson_id: z.string().uuid(),
          title: z.string().min(1),
          activity_type: z.enum(["multiple_choice", "interactive_fractions"]),
          instructions: z.string(),
          public_config: activityConfig,
          points: z.number().int().min(0).max(100),
          display_order: z.number().int(),
        })
        .parse(b);
      const solution = z
        .object({
          answer_config: z.union([
            z.object({ selected: z.number().int() }).strict(),
            z.object({ option: z.number().int() }).strict(),
          ]),
          explanation: z.string().min(1),
        })
        .parse(b);
      const r = await (
        id
          ? context.supabase.from("activities").update(row).eq("id", id)
          : context.supabase.from("activities").insert(row)
      )
        .select()
        .single();
      if (r.error) throw new Error(r.error.message);
      id = r.data.id;
      const s = await admin.from("activity_solutions").upsert({ activity_id: id, ...solution });
      if (s.error) throw new Error(s.error.message);
    }
    return { id };
  });
