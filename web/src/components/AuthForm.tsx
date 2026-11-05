import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpen,
  GraduationCap,
  Link2,
  Monitor,
  ShieldCheck,
  Users,
} from "lucide-react";
import type { AuthError } from "@supabase/supabase-js";
import { supabase } from "@/integrations/supabase/client";
import "./education/adult-workspace.css";

const messages: Record<string, string> = {
  email_address_not_authorized: "El centro todavía no ha habilitado este correo para el registro.",
  invalid_credentials: "Revisa tu correo y tu contraseña.",
  over_email_send_rate_limit: "Espera unos minutos antes de solicitar otro correo.",
  over_request_rate_limit: "Espera unos minutos antes de volver a intentarlo.",
};
const genericError = "No se pudo completar la solicitud. Inténtalo de nuevo.";
const authMessage = (error: AuthError) => messages[error.code ?? ""] ?? genericError;
async function requestAccount(fields: Record<string, string>) {
  const response = await fetch("/api/cuenta", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  const body = await response.json().catch(() => null);
  return {
    ok: response.ok,
    status: response.status,
    message: typeof body?.error === "string" ? body.error : genericError,
  };
}
export function AdultAuthHeader() {
  return (
    <header className="mw-auth-header">
      <Link to="/" className="mw-wordmark" aria-label="Mochi, acceso a los paneles">
        <span className="mw-mark" aria-hidden="true">
          <span />
        </span>
        <span>mochi</span>
      </Link>
      <nav aria-label="Acceso adulto">
        <Link to="/expedicion">Profesores</Link>
        <Link to="/familia">Familias</Link>
      </nav>
    </header>
  );
}

export function AuthForm({
  signup = false,
  defaultType = "family",
}: {
  signup?: boolean;
  defaultType?: "family" | "teacher";
}) {
  const navigate = useNavigate();
  const [notice, setNotice] = useState<{ text: string; error: boolean }>();
  const [busy, setBusy] = useState(false);
  const fail = (text: string) => setNotice({ text, error: true });
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const email = String(fields.get("email") ?? "")
      .trim()
      .toLowerCase();
    const password = String(fields.get("password") ?? "");
    setBusy(true);
    setNotice(undefined);
    try {
      let existing = false;
      if (signup) {
        const type = String(fields.get("type"));
        if (!["family", "teacher"].includes(type) || !fields.has("adult")) {
          fail("La cuenta debe pertenecer a un docente o familiar mayor de edad.");
          return;
        }
        const created = await requestAccount({
          action: "register",
          email,
          password,
          display_name: String(fields.get("name") ?? "").trim(),
          account_type: type,
          age_band: "18+",
        });
        existing = created.status === 409;
        if (!created.ok && !existing) {
          fail(created.message);
          return;
        }
      }
      let login = await supabase.auth.signInWithPassword({ email, password });
      if (login.error?.code === "email_not_confirmed") {
        const activated = await requestAccount({ action: "activate", email, password });
        if (!activated.ok) {
          fail(activated.message);
          return;
        }
        login = await supabase.auth.signInWithPassword({ email, password });
      }
      if (login.error || !login.data.user || !login.data.session) {
        fail(
          existing
            ? "Ese correo ya tiene una cuenta. Inicia sesión con tu contraseña."
            : login.error
              ? authMessage(login.error)
              : genericError,
        );
        return;
      }
      const response = await fetch("/api/education/adult-onboarding", {
        headers: { Authorization: `Bearer ${login.data.session.access_token}` },
      });
      const verified = await response.json().catch(() => null);
      await navigate({
        to: response.ok && verified?.role === "teacher" ? "/expedicion" : "/familia",
      });
    } catch {
      fail(genericError);
    } finally {
      setBusy(false);
    }
  }
  async function recover(email: string) {
    if (!email) {
      fail("Introduce tu correo para recibir el enlace.");
      return;
    }
    setBusy(true);
    setNotice(undefined);
    try {
      const result = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: window.location.origin + "/reset-password",
      });
      if (result.error) fail(authMessage(result.error));
      else
        setNotice({
          text: "Si el correo corresponde a una cuenta, recibirás las instrucciones para restablecer la contraseña.",
          error: false,
        });
    } catch {
      fail(genericError);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mochi-auth">
      <AdultAuthHeader />
      <main className="mw-auth-main">
        <section className="mw-auth-context">
          <p className="mw-auth-label">
            <Link2 size={16} />
            El aprendizaje, bien acompañado
          </p>
          <h1>
            El colegio y el hogar,
            <br />
            en la misma página.
          </h1>
          <p>
            Un espacio para que docentes y familias acompañen lo que cada niño aprende con su Mochi.
          </p>
          <div className="mw-auth-flow">
            <span>
              <GraduationCap size={17} />
              El docente orienta
            </span>
            <ArrowRight size={13} />
            <span>
              <Monitor size={17} />
              Mochi acompaña
            </span>
            <ArrowRight size={13} />
            <span>
              <Users size={17} />
              La familia comprende
            </span>
          </div>
          <div className="mw-auth-privacy">
            <ShieldCheck size={18} />
            <span>
              Acceso exclusivo para adultos autorizados.
              <br />
              La experiencia infantil sucede en el dispositivo.
            </span>
          </div>
        </section>
        <section className="mw-auth-form" aria-labelledby="adult-access-title">
          <h2 id="adult-access-title">{signup ? "Crea tu cuenta" : "Entra en tu espacio"}</h2>
          <p>
            {signup
              ? "Para docentes, padres y tutores legales."
              : "Utiliza la cuenta adulta vinculada a tu centro."}
          </p>
          <form onSubmit={submit} aria-busy={busy}>
            {signup && (
              <>
                <label>
                  Nombre
                  <input name="name" required minLength={2} maxLength={60} autoComplete="name" />
                </label>
                <label>
                  Tipo de cuenta
                  <select name="type" defaultValue={defaultType}>
                    <option value="family">Padre, madre o tutor legal</option>
                    <option value="teacher">Docente</option>
                  </select>
                </label>
              </>
            )}
            <label>
              Correo
              <input
                name="email"
                type="email"
                required
                maxLength={254}
                autoComplete={signup ? "email" : "username"}
              />
            </label>
            <label>
              Contraseña
              <input
                name="password"
                type="password"
                minLength={signup ? 8 : undefined}
                maxLength={signup ? 72 : undefined}
                required
                autoComplete={signup ? "new-password" : "current-password"}
              />
            </label>
            {signup && (
              <label className="mw-check" style={{ flexDirection: "row", fontWeight: 400 }}>
                <input type="checkbox" name="adult" required />
                <span>Soy mayor de edad y utilizaré este espacio como adulto responsable.</span>
              </label>
            )}
            {notice && (
              <p
                className="mw-auth-message"
                role={notice.error ? "alert" : "status"}
                data-error={notice.error}
              >
                {notice.text}
              </p>
            )}
            <button className="mw-button primary" disabled={busy}>
              {busy ? "Un momento…" : signup ? "Crear cuenta adulta" : "Iniciar sesión"}
              {!busy && <ArrowRight size={16} />}
            </button>
            {!signup && (
              <button
                className="mw-text-button"
                type="button"
                disabled={busy}
                onClick={(event) =>
                  void recover(
                    String(
                      new FormData(event.currentTarget.form ?? undefined).get("email") ?? "",
                    ).trim(),
                  )
                }
              >
                Recuperar contraseña
              </button>
            )}
          </form>
          <div className="mw-auth-links">
            <span>{signup ? "¿Ya tienes cuenta?" : "¿Necesitas una cuenta?"}</span>
            <Link to={signup ? "/entrar" : "/registro"}>
              {signup ? "Iniciar sesión" : "Crear cuenta adulta"}
            </Link>
          </div>
        </section>
      </main>
      <footer className="mw-auth-footer">
        <BookOpen
          size={13}
          style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }}
        />
        Mochi · Acompañamos el aprendizaje, respetamos cada ritmo.
      </footer>
    </div>
  );
}
