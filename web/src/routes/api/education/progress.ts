import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/education/progress")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/progress.server")).handleProgress(request),
      POST: async ({ request }) =>
        (await import("@/lib/education/progress.server")).handleProgress(request),
    },
  },
});
