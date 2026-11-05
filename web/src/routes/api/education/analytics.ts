import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/education/analytics")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/analytics.server")).handleAnalytics(request),
    },
  },
});
