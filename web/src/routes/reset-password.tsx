import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { AdultAuthHeader } from "@/components/AuthForm";
import { Field, meta } from "@/components/Layout";

export const Route = createFileRoute("/reset-password")({
  head: () =>
    meta("Restablecer contraseña", "Elige una nueva contraseña para tu cuenta de Peluqo."),
  component: Reset,
});

function Reset() {
  const [valid, setValid] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean }>();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => {
    setValid(new URLSearchParams(window.location.hash.slice(1)).get("type") === "recovery");
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") setValid(true);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  return (
    <div className="mochi-auth">
      <AdultAuthHeader />
      <main className="mw-error-page">
        <section className="mw-auth-form" aria-labelledby="recuperar-titulo">
          <h1 id="recuperar-titulo">Nueva contraseña</h1>
          {valid && !done ? (
            <form
              className="mw-form"
              aria-busy={busy}
              onSubmit={async (event) => {
                event.preventDefault();
                setBusy(true);
                const password = String(new FormData(event.currentTarget).get("password"));
                try {
                  const result = await supabase.auth.updateUser({ password });
                  if (result.error) {
                    setNotice({ text: result.error.message, error: true });
                  } else {
                    setDone(true);
                    setNotice({ text: "Contraseña actualizada. Ya puedes entrar." });
                  }
                } catch {
                  setNotice({
                    text: "No se pudo guardar la contraseña. Inténtalo de nuevo.",
                    error: true,
                  });
                } finally {
                  setBusy(false);
                }
              }}
            >
              <Field
                label="Nueva contraseña"
                name="password"
                type="password"
                minLength={8}
                maxLength={72}
                autoComplete="new-password"
                required
              />
              <button className="mw-button primary" disabled={busy}>
                {busy ? "Guardando…" : "Guardar contraseña"}
              </button>
            </form>
          ) : (
            !done && (
              <p className="acceso-intro">
                Abre el enlace de recuperación que recibiste por correo.
              </p>
            )
          )}
          <p className="acceso-mensaje mt-3" role="status" data-error={notice?.error}>
            {notice?.text}
          </p>
          <Link className="mw-text-button" to="/entrar">
            Volver al inicio de sesión
          </Link>
        </section>
      </main>
    </div>
  );
}
