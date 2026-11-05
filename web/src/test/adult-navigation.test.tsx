import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { Shell } from "@/components/Layout";

const context = vi.hoisted(() => ({ role: undefined as string | undefined }));
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => vi.fn(),
  useRouterState: ({ select }: { select: (value: unknown) => unknown }) =>
    select({
      location: { pathname: "/familia" },
      matches: [{ routeId: "/_authenticated" }],
    }),
}));
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ clear: vi.fn(), cancelQueries: vi.fn() }),
  useQuery: ({ queryKey }: { queryKey: string[] }) => ({
    data: queryKey[0] === "session-user" ? { id: "adult-account" } : context.role,
    isPending: false,
  }),
}));
vi.mock("@/integrations/supabase/client", () => ({ supabase: { auth: {} } }));
afterEach(() => {
  cleanup();
  context.role = undefined;
});

describe("adult workspace integration", () => {
  it("leaves the autonomous family workspace free of legacy navigation and child links", () => {
    context.role = "family";
    render(
      <Shell>
        <p>Contenido adulto</p>
      </Shell>,
    );
    expect(screen.getByText("Contenido adulto")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Mi espacio Peluqo" })).toBeNull();
    expect(screen.queryByRole("link", { name: /mi aventura|mundos|cuadernos/i })).toBeNull();
  });
});
