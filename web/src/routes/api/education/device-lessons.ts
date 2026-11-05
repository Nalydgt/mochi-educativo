import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/api/education/device-lessons")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/device-lessons.server")).handleDeviceLessons(request),
    },
  },
});
