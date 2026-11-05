import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/api/education/device")({
  server: {
    handlers: {
      POST: async ({ request }) =>
        (await import("@/lib/education/api.server")).handleEducation(request, true),
    },
  },
});
