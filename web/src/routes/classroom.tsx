import { createFileRoute, redirect } from "@tanstack/react-router";
export const Route = createFileRoute("/classroom")({
  beforeLoad: () => {
    throw redirect({ to: "/expedicion" });
  },
});
