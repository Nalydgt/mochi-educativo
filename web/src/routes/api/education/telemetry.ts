import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/education/telemetry")({
  server: {
    handlers: {
      POST: async ({ request }) =>
        (await import("@/lib/education/analytics.server")).handleTelemetry(request),
    },
  },
});
