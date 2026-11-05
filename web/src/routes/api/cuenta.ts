import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/cuenta")({
  server: {
    handlers: {
      POST: async ({ request }) =>
        (await import("@/lib/registration.server")).handleRegistration(request),
    },
  },
});
