import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/api/tutor")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const { handleTutor } = await import("@/lib/tutor.server");
        return handleTutor(request);
      },
    },
  },
});
