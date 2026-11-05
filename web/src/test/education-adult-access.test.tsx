import { afterEach, expect, it, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Pilot } from "@/components/education/Pilot";
import { supabase } from "@/integrations/supabase/client";

const account = vi.hoisted(() => ({ id: null as string | null }));

vi.mock("@/lib/education/adult-client", () => ({
  useAdultAccountId: () => account.id,
  adultRequest: vi.fn(),
}));
vi.mock("@/integrations/supabase/client", () => ({
  supabase: { auth: { getSession: vi.fn(), signInWithPassword: vi.fn() } },
}));
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
}));
vi.mock("@/components/education/StudentAdventure", () => ({
  StudentAdventure: () => <p>Zona infantil</p>,
}));
vi.mock("@/components/education/FieldGuide", () => ({ FieldGuide: () => null }));

afterEach(() => {
  cleanup();
  account.id = null;
  vi.unstubAllGlobals();
  document.cookie = "peluqo_student=; Max-Age=0; Path=/";
});

it("shows adult sign-in and never fetches an old learner cookie without an adult session", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  document.cookie = "peluqo_student=old-fictitious-learner; Path=/";
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={query}>
      <Pilot />
    </QueryClientProvider>,
  );
  expect(screen.getByRole("heading", { name: "Entrada docente" })).toBeInTheDocument();
  expect(screen.getByLabelText("Correo docente")).toBeInTheDocument();
  expect(screen.queryByText("Zona infantil")).toBeNull();
  expect(screen.queryByRole("button", { name: /soy alumno|entrar con código/i })).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});

it("does not fall back to a learner cookie when an adult token expires", async () => {
  account.id = "77777777-7777-4777-8777-777777777777";
  vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: null }, error: null });
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  document.cookie = "peluqo_student=old-fictitious-learner; Path=/";
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  query.setQueryData(["education", account.id, 0, false], {
    role: "learner",
    learner: { id: "old-student" },
  });
  render(
    <QueryClientProvider client={query}>
      <Pilot />
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("heading", { name: "Entrada docente" })).toBeInTheDocument();
  expect(screen.queryByText("Zona infantil")).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});
