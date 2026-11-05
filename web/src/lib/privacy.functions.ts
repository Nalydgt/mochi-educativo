import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

export const removeLearningData = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator(z.object({ confirmation: z.literal("ELIMINAR"), requestId: z.string().uuid() }))
  .handler(async ({ data, context }) => {
    const { resetLearningData } = await import("./education/privacy.server");
    return resetLearningData(context.userId, context.supabase, data.requestId);
  });

export const retryLearningCleanup = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { cleanupLearningFiles } = await import("./education/privacy.server");
    return { pendingFiles: await cleanupLearningFiles(context.userId, context.supabase) };
  });

export const learningPrivacyState = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { learningFileQueue } = await import("./education/privacy.server");
    const queue = await learningFileQueue(context.userId);
    return { pendingFiles: queue.pendingFiles };
  });

export const exportLearningData = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { exportLearningSummary } = await import("./education/privacy.server");
    return exportLearningSummary(context.userId);
  });
