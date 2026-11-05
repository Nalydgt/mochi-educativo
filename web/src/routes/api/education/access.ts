import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/education/access")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/student-access.server")).handleStudentAccess(request),
      POST: async ({ request }) =>
        (await import("@/lib/education/student-access.server")).handleStudentAccess(request),
    },
  },
});
