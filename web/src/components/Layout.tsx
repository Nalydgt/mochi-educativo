import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useQueryClient, useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  Compass,
  House,
  LogOut,
  Route,
  Star,
  UsersRound,
} from "lucide-react";
import type { ReactNode, InputHTMLAttributes } from "react";
import { supabase } from "@/integrations/supabase/client";
import { BrandMark, presentationArt, presentationSprite } from "./BrandMark";
import { Button } from "./ui/button";
import "./platform.css";

const destinations = {
  classroom: { to: "/expedicion", label: "Panel docente", icon: Compass },
  dashboard: { to: "/dashboard", label: "Mi aventura", icon: House },
  family: { to: "/familia", label: "Panel familiar", icon: UsersRound },
  worlds: { to: "/mundos", label: "Mundos", icon: Route },
  study: { to: "/estudio", label: "Cuadernos", icon: BookOpen },
  progress: { to: "/progreso", label: "Seguimiento", icon: Star },
} as const;

const publicRoutesWithOwnShell = new Set([
  "/",
  "/registro",
  "/entrar",
  "/auth",
  "/reset-password",
  "/expedicion",
  "/familia",
]);

export function Shell({ children }: { children: ReactNode }) {
  const path = useRouterState({ select: (state) => state.location.pathname });
  const workspace = useRouterState({
    select: (state) => state.matches.some((match) => match.routeId === "/_authenticated"),
  });
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const standalone = publicRoutesWithOwnShell.has(path.replace(/\/$/, "") || "/");
  const { data: user, isPending } = useQuery({
    queryKey: ["session-user"],
    queryFn: async () => (await supabase.auth.getUser()).data.user,
    enabled: !standalone,
  });
  const { data: accountType } = useQuery({
    queryKey: ["layout-role", user?.id],
    enabled: !!user && workspace,
    queryFn: async () => {
      if (!user) return null;
      const { data } = await supabase
        .from("profiles")
        .select("account_type")
        .eq("id", user.id)
        .maybeSingle();
      return data?.account_type ?? null;
    },
  });
  if (standalone) return <>{children}</>;

  const { classroom, family, progress } = destinations;
  const nav =
    accountType === "teacher"
      ? [classroom, family, progress]
      : accountType === "family"
        ? [family, progress]
        : [];
  const accountHome = accountType === "teacher" ? classroom : family;
  const roleLabel =
    accountType === "teacher" ? "Docente" : accountType === "family" ? "Familia" : "Tu espacio";

  return (
    <div className="platform">
      <a className="platform-skip" href="#platform-main">
        Ir al contenido
      </a>
      <header className="platform-header">
        <div className="platform-width platform-header-inner">
          <Link to="/" aria-label="Peluqo, inicio">
            <BrandMark />
          </Link>
          {!workspace && (
            <nav className="platform-public-nav" aria-label="Explorar Peluqo">
              <Link to="/mundos">Mundos</Link>
              <Link to="/expedicion">
                Peluqo Aula <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
            </nav>
          )}
          <div className="platform-account">
            {user ? (
              <>
                {!workspace && (
                  <Link to={accountHome.to} className="btn">
                    Mi espacio
                  </Link>
                )}
                <Button
                  variant="outline"
                  onClick={async () => {
                    await supabase.auth.signOut();
                    await queryClient.cancelQueries();
                    queryClient.clear();
                    await navigate({ to: "/entrar", replace: true });
                  }}
                >
                  <LogOut aria-hidden="true" /> Salir
                </Button>
              </>
            ) : !workspace || !isPending ? (
              <>
                <Link to="/entrar" className="platform-login">
                  Iniciar sesión
                </Link>
                <Link to="/registro" className="btn platform-register">
                  Crear cuenta
                </Link>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <div className={workspace ? "platform-workspace" : "platform-public"}>
        {workspace && (
          <aside className="platform-sidebar">
            <p>{roleLabel}</p>
            <nav aria-label="Mi espacio Peluqo">
              {nav.map(({ to, label, icon: Icon }) => (
                <Link key={to} to={to} activeProps={{ "aria-current": "page" }}>
                  <Icon size={18} aria-hidden="true" /> {label}
                </Link>
              ))}
            </nav>
          </aside>
        )}
        <main id="platform-main" tabIndex={-1}>
          {children}
        </main>
      </div>
      <footer className="platform-footer">
        <div className="platform-width">
          <p>
            <strong>Peluqo</strong> <span>Aprender explorando</span>
          </p>
          <Link to="/expedicion">
            Peluqo Aula <ArrowUpRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </footer>
    </div>
  );
}

export function Section({
  tone = "white",
  children,
  className = "",
}: {
  tone?: "sky" | "white" | "gray" | "lavender";
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`platform-section ${className}`} data-tone={tone}>
      <div className="platform-section-inner">{children}</div>
    </section>
  );
}

export function PageTitle({
  kicker,
  title,
  sub,
  art,
}: {
  kicker: string;
  title: string;
  sub?: string | undefined;
  art?: "reserva" | "observatorio" | "taller";
}) {
  return (
    <div className="platform-page-title" data-illustrated={!!art}>
      <div>
        <p className="platform-kicker">{kicker}</p>
        <h1>{title}</h1>
        {sub && <p className="platform-subtitle">{sub}</p>}
      </div>
      {art && (
        <img
          className="platform-page-art"
          src={`${presentationArt}/${art}.webp`}
          width={1680}
          height={746}
          alt=""
        />
      )}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="platform-empty">
      <img src={presentationSprite("peluqo-alerta")} width={96} height={96} alt="" />
      <div>
        <h2>{title}</h2>
        <p>{children}</p>
        {action && <div className="platform-empty-action">{action}</div>}
      </div>
    </div>
  );
}

export function Tag({ children, color = "bg-mint" }: { children: ReactNode; color?: string }) {
  return <span className={`platform-tag ${color}`}>{children}</span>;
}

export function meta(title: string, description: string) {
  return {
    meta: [
      { title: `${title} · Peluqo` },
      { name: "description", content: description },
      { property: "og:title", content: `${title} · Peluqo` },
      { property: "og:description", content: description },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  };
}

export function Field({
  label,
  className,
  ...p
}: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="platform-field">
      <span className="label">{label}</span>
      <input {...p} className={["platform-input", className].filter(Boolean).join(" ")} />
    </label>
  );
}
