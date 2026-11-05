import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/api/education/adult-onboarding")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        (await import("@/lib/education/adult-onboarding.server")).handleAdultOnboarding(request),
      POST: async ({ request }) =>
        (await import("@/lib/education/adult-onboarding.server")).handleAdultOnboarding(request),
    },
  },
});
