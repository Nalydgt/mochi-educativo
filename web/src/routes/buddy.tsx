import { createFileRoute, redirect } from "@tanstack/react-router";
export const Route = createFileRoute("/buddy")({
  beforeLoad: () => {
    throw redirect({ to: "/expedicion" });
  },
});
