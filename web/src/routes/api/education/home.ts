import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/education/home")({
  server: {
    handlers: {
      POST: async ({ request }) =>
        (await import("@/lib/education/home-studio.server")).activateHomeStudio(request),
    },
  },
});
