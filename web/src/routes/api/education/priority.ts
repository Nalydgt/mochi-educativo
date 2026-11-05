import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/education/priority")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/priority.server")).handlePriority(request),
      POST: async ({ request }) =>
        (await import("@/lib/education/priority.server")).handlePriority(request),
    },
  },
});
