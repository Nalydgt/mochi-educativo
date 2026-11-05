import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/api/education/")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/api.server")).handleEducation(request),
      POST: async ({ request }) =>
        (await import("@/lib/education/api.server")).handleEducation(request),
    },
  },
});
