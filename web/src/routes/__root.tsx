import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import { EmptyState, Section, Shell } from "@/components/Layout";
import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { supabase } from "@/integrations/supabase/client";

function NotFoundComponent() {
  return (
    <Section className="platform-error-page">
      <h1 className="sr-only">Página no encontrada</h1>
      <EmptyState
        title="Esta página no está disponible"
        action={
          <Link to="/" className="btn btn-primary">
            Volver al panel
          </Link>
        }
      >
        La dirección que abriste ya no está disponible.
      </EmptyState>
    </Section>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <Section className="platform-error-page">
      <h1 className="sr-only">Error al cargar la página</h1>
      <EmptyState
        title="La página no se pudo abrir"
        action={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                router.invalidate();
                reset();
              }}
              className="btn btn-primary"
            >
              Volver a intentar
            </button>
            <Link to="/" className="btn">
              Ir al inicio
            </Link>
          </div>
        }
      >
        Intenta abrirla otra vez o regresa a tu panel de Mochi.
      </EmptyState>
    </Section>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "MOCHI · Profesores y familias" },
      {
        name: "description",
        content:
          "Actividades, revisión docente y comunicación con las familias, conectadas al dispositivo Mochi.",
      },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
      { rel: "icon", href: "/mochi-mark.svg", type: "image/svg+xml" },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Bowlby+One&display=swap",
      },
      {
        rel: "stylesheet",
        href: "https://api.fontshare.com/v2/css?f[]=general-sans@500,700&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const router = useRouter();
  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (!["SIGNED_IN", "SIGNED_OUT", "USER_UPDATED"].includes(event)) return;
      router.invalidate();
      if (event !== "SIGNED_OUT") queryClient.invalidateQueries();
    });
    return () => data.subscription.unsubscribe();
  }, [router, queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
      <Shell>
        <Outlet />
      </Shell>
    </QueryClientProvider>
  );
}
