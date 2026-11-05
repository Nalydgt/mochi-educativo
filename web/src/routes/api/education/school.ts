import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/education/school")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/school.server")).handleSchool(request),
      POST: async ({ request }) =>
        (await import("@/lib/education/school.server")).handleSchool(request),
    },
  },
});
