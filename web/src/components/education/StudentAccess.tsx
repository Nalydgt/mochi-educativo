import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Copy, KeyRound, X } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import {
  accessDurations,
  normalizeStudentCode,
  studentAccessProfile,
  type AccessDuration,
  type StudentAccessOptions,
  type StudentAccessProfile,
  type StudentAccessStatus,
} from "@/lib/education/student-access";
import { FieldGuide } from "./FieldGuide";
import "./student-access.css";

const profileKey = "peluqo.student-picker.v1";
const profileLifetime = 30 * 24 * 60 * 60 * 1_000;
type LocalProfile = StudentAccessProfile & { seenAt: number };

function recentProfiles(): LocalProfile[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(profileKey) ?? "[]");
    if (!Array.isArray(stored)) return [];
    return stored
      .flatMap((raw) => {
        const profile = studentAccessProfile.safeParse(raw);
        const seenAt: unknown = raw?.seenAt;
        return profile.success &&
          typeof seenAt === "number" &&
          seenAt > Date.now() - profileLifetime
          ? [{ ...profile.data, seenAt }]
          : [];
      })
      .slice(0, 5);
  } catch {
    return [];
  }
}

function saveProfiles(profiles: LocalProfile[]) {
  try {
    if (profiles.length) localStorage.setItem(profileKey, JSON.stringify(profiles));
    else localStorage.removeItem(profileKey);
  } catch {
    // Browser privacy settings can disable this optional shortcut.
  }
}

export function StudentCodeEntry({
  busy,
  error,
  onCode,
}: {
  busy: boolean;
  error: string;
  onCode: (code: string, options: StudentAccessOptions) => Promise<StudentAccessProfile | null>;
}) {
  const [profiles, setProfiles] = useState<LocalProfile[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [remember, setRemember] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const selected = profiles.find((profile) => profile.id === selectedId);

  useEffect(() => {
    const current = recentProfiles();
    setProfiles(current);
    saveProfiles(current);
  }, []);

  function choose(profile: LocalProfile) {
    setSelectedId(profile.id);
    setRemember(true);
    if (input.current) input.current.value = "";
    input.current?.focus();
  }

  function forget(id: string) {
    const next = profiles.filter((profile) => profile.id !== id);
    setProfiles(next);
    saveProfiles(next);
    if (selectedId === id) {
      setSelectedId(undefined);
      setRemember(false);
      input.current?.focus();
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = normalizeStudentCode(String(new FormData(event.currentTarget).get("code")));
    const profile = await onCode(code, {
      remember,
      ...(selected ? { learnerId: selected.id } : {}),
    });
    if (!profile) return;
    const others = recentProfiles().filter((item) => item.id !== profile.id);
    saveProfiles(remember ? [{ ...profile, seenAt: Date.now() }, ...others].slice(0, 5) : others);
  }

  return (
    <div className="student-code-entry">
      {profiles.length > 0 && (
        <div className="student-code-profiles" aria-label="Perfiles recordados">
          <p>Elige tu perfil en este dispositivo</p>
          <ul>
            {profiles.map((profile) => (
              <li key={profile.id}>
                <button
                  type="button"
                  className="student-code-profile"
                  onClick={() => choose(profile)}
                  aria-pressed={selectedId === profile.id}
                  disabled={busy}
                >
                  <FieldGuide color={profile.color} />
                  <span>{profile.name}</span>
                </button>
                <button
                  type="button"
                  className="student-code-forget"
                  onClick={() => forget(profile.id)}
                  disabled={busy}
                  aria-label={`Olvidar el perfil de ${profile.name}`}
                >
                  <X size={16} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
          {selected && (
            <button
              type="button"
              className="edu-text-button"
              disabled={busy}
              onClick={() => {
                setSelectedId(undefined);
                setRemember(false);
                if (input.current) input.current.value = "";
                input.current?.focus();
              }}
            >
              Usar otro perfil
            </button>
          )}
        </div>
      )}
      <form onSubmit={(event) => void submit(event)}>
        <label>
          {selected ? `Código de ${selected.name}` : "Tu código de explorador"}
          <input
            ref={input}
            className="student-code-input"
            name="code"
            required
            minLength={8}
            maxLength={40}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="XXXX-XXXX-XXXX"
          />
        </label>
        <label className="student-code-remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
          />
          <span>Recordarme en este dispositivo privado</span>
        </label>
        <button className="edu-button primary" disabled={busy}>
          {busy ? "Entrando…" : "Abrir mi mundo"}
          {!busy && <ArrowRight size={18} aria-hidden="true" />}
        </button>
      </form>
      {error && (
        <p role="alert" className="edu-help">
          {error}
        </p>
      )}
    </div>
  );
}

const statusText: Record<StudentAccessStatus["status"], string> = {
  none: "Sin código",
  active: "Activo",
  paused: "Pausado",
  revoked: "Revocado",
  expired: "Caducado",
  used: "Usado",
};
type AccessAction = "issue" | "pause" | "enable" | "revoke";
type AccessRequest = {
  learnerId: string;
  action: AccessAction;
  duration?: AccessDuration;
  expiresAt?: string;
};
type AccessResponse = StudentAccessStatus & { code?: string };

async function fetchAccess(learnerId: string, command?: AccessRequest): Promise<AccessResponse> {
  const session = (await supabase.auth.getSession()).data.session;
  if (!session) throw new Error("Inicia sesión con tu cuenta adulta.");
  const query = new URLSearchParams({ learnerId });
  const response = await fetch(`/api/education/access?${query}`, {
    method: command ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      ...(command ? { "Content-Type": "application/json" } : {}),
    },
    ...(command ? { body: JSON.stringify(command) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "No se pudo gestionar el código.");
  return data;
}

const codeDate = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" });

export function StudentAccessManager({ learnerId, name }: { learnerId: string; name: string }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [duration, setDuration] = useState<AccessDuration>("7d");
  const [date, setDate] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [dateError, setDateError] = useState("");
  const queryKey = ["student-access", learnerId] as const;
  const query = useQuery({
    queryKey,
    queryFn: () => fetchAccess(learnerId),
    enabled: open,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: (body: AccessRequest) => fetchAccess(learnerId, body),
    onSuccess: ({ code: nextCode, ...status }, command) => {
      client.setQueryData(queryKey, status);
      if (nextCode) setCode(nextCode);
      else if (command.action === "revoke") setCode("");
      setMessage(
        command.action === "issue" ? "Código listo para compartir." : "Acceso actualizado.",
      );
    },
  });
  const state = query.data;

  function update(action: AccessAction) {
    setDateError("");
    setMessage("");
    if (action !== "issue") {
      mutation.mutate({ learnerId, action });
      return;
    }
    const expiresAt = date && duration === "custom" ? new Date(date) : null;
    if (duration === "custom" && (!expiresAt || !(expiresAt.getTime() > Date.now()))) {
      setDateError("Elige una fecha futura.");
      return;
    }
    mutation.mutate({
      learnerId,
      action,
      duration,
      ...(expiresAt ? { expiresAt: expiresAt.toISOString() } : {}),
    });
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setMessage("Código copiado.");
    } catch {
      setMessage("Selecciona el código para copiarlo.");
    }
  }

  return (
    <details
      className="student-access-manager"
      onToggle={(event) => {
        const next = event.currentTarget.open;
        setOpen(next);
        if (!next) setCode("");
      }}
    >
      <summary aria-label={`Acceso de ${name}`}>
        <KeyRound size={17} aria-hidden="true" /> Acceso de estudiante
      </summary>
      <div className="student-access-body">
        {query.isPending && <p role="status">Comprobando el acceso…</p>}
        {(query.error || mutation.error || dateError) && (
          <p role="alert" className="student-access-error">
            {query.error?.message || mutation.error?.message || dateError}
          </p>
        )}
        {state && (
          <>
            <div className="student-access-status">
              <span data-status={state.status}>{statusText[state.status]}</span>
              {state.status !== "none" && (
                <small>
                  {state.expiresAt
                    ? `Caducidad · ${codeDate.format(new Date(state.expiresAt))}`
                    : "Sin caducidad"}
                </small>
              )}
            </div>
            <form
              className="student-access-controls"
              onSubmit={(event) => {
                event.preventDefault();
                update("issue");
              }}
            >
              <label>
                Duración del código
                <select
                  value={duration}
                  onChange={(event) => setDuration(event.target.value as AccessDuration)}
                >
                  {Object.entries(accessDurations).map(([value, title]) => (
                    <option key={value} value={value}>
                      {title}
                    </option>
                  ))}
                </select>
              </label>
              {duration === "custom" && (
                <label>
                  Válido hasta
                  <input
                    type="datetime-local"
                    value={date}
                    onChange={(event) => setDate(event.target.value)}
                    required
                  />
                </label>
              )}
              <button className="student-access-primary" disabled={mutation.isPending}>
                {state.status === "none" ? "Generar código" : "Regenerar código"}
              </button>
            </form>
            <div className="student-access-actions">
              {state.status === "active" && (
                <button type="button" disabled={mutation.isPending} onClick={() => update("pause")}>
                  Pausar código
                </button>
              )}
              {state.status === "paused" && (
                <button
                  type="button"
                  disabled={mutation.isPending}
                  onClick={() => update("enable")}
                >
                  Reactivar código
                </button>
              )}
              {state.status !== "none" && state.status !== "revoked" && (
                <button
                  type="button"
                  disabled={mutation.isPending}
                  onClick={() => update("revoke")}
                >
                  Revocar código
                </button>
              )}
            </div>
            <small>
              Al pausar, regenerar o revocar, se cierra el acceso abierto en otros dispositivos.
            </small>
          </>
        )}
        {code && state?.status === "active" && (
          <div className="student-access-result">
            <code aria-label="Código del alumno">{code}</code>
            <button type="button" onClick={() => void copyCode()} aria-label="Copiar el código">
              <Copy size={16} aria-hidden="true" /> Copiar
            </button>
          </div>
        )}
        {message && (
          <p className="student-access-message" role="status">
            {message}
          </p>
        )}
      </div>
    </details>
  );
}
