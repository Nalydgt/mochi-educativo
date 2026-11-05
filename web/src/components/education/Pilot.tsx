import { useState } from "react";
import { Link } from "@tanstack/react-router";
import "./education.css";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpen, Compass, Globe2, LogOut, MessageCircle, Ticket } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { BrandMark } from "@/components/BrandMark";
import { FieldGuide } from "./FieldGuide";
import { MissionEditor } from "./MissionEditor";
import { StudentAdventure, type LearnerData } from "./StudentAdventure";
import { AulaProgress } from "./AulaProgress";
import { DeviceLessons } from "./DeviceLessons";
import { StudentAccessManager } from "./StudentAccess";
import { PupilPriority } from "./PupilPriority";
import { defaultLearnerPreferences } from "@/lib/education/personalization";
import { useAdultAccountId } from "@/lib/education/adult-client";
import { noteStudyFailure } from "@/hooks/use-study-telemetry";
import type { Mission, Phase } from "@/lib/education/schema";

type TeacherData = {
  role: "teacher";
  home: boolean;
  classes: { id: string; name: string; draft: Mission | null }[];
  learners: {
    id: string;
    class_id: string;
    name: string;
    support: boolean;
    family_count: number;
  }[];
  documents: { id: string; class_id: string; name: string }[];
  versions: { id: string; class_id: string; title: string; created_at: string }[];
  sessions: { id: string; learner_id: string; phase: Phase; created_at: string }[];
  devices: {
    id: string;
    learner_id: string | null;
    session_id: string | null;
    revoked: boolean;
    last_seen_at: string | null;
  }[];
};
type Data = TeacherData | (LearnerData & { role: "learner" });
type Source = { id: string; page: number | null; content: string };
type TeacherReply<Command> = Command extends FormData
  ? { documentId: string }
  : Command extends { action: "create-class" }
    ? { id: string }
    : Command extends { action: "issue-family-code" }
      ? { code: string }
      : Command extends { action: "generate" }
        ? { draft: Mission }
        : Command extends { action: "document-source" }
          ? Source[]
          : Record<string, unknown>;
class EducationError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}
function needsLogin(error: unknown) {
  return error instanceof EducationError && [401, 403, 404].includes(error.status);
}
const phaseNames: Record<string, string> = {
  diagnostic: "Antes de explorar",
  practice: "La expedición",
  final: "Demuestra lo que sabes",
  completed: "Tus descubrimientos",
  retention: "Lo que recuerdas",
};
async function call(body?: unknown, pupilMode = false, home = false) {
  const session = pupilMode ? null : (await supabase.auth.getSession()).data.session;
  if (!session) throw new EducationError("Inicia sesión con tu cuenta adulta autorizada.", 401);
  const headers: Record<string, string> = {};
  if (session) headers["Authorization"] = `Bearer ${session.access_token}`;
  if (home) headers["X-Peluqo-Space"] = "home";
  if (body && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch("/api/education/", {
    method: body ? "POST" : "GET",
    headers,
    credentials: "same-origin",
    ...(body ? { body: body instanceof FormData ? body : JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok)
    throw new EducationError(data.error ?? "No se pudo completar la operación.", response.status);
  return data;
}

export function Pilot({ home = false }: { home?: boolean }) {
  const qc = useQueryClient();
  const account = useAdultAccountId();
  const [epoch, setEpoch] = useState(0);
  const [tab, setTab] = useState("aula");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const q = useQuery({
    queryKey: ["education", account, epoch, home],
    queryFn: () => call(undefined, false, home),
    enabled: !!account,
    retry: false,
    refetchInterval: (query) => (query.state.data && !needsLogin(query.state.error) ? 8000 : false),
  });
  async function run(body: unknown) {
    const action = (body as { action?: string })?.action;
    const conversation = action === "tutor" || action === "ask";
    if (!conversation) setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await call(body, action === "login", home);
      if (!["focus", "login", "logout"].includes(action ?? ""))
        await qc.invalidateQueries({ queryKey: ["education"] });
      return result;
    } catch (e) {
      if (q.data?.role === "learner" && (!(e instanceof EducationError) || e.status >= 500))
        noteStudyFailure();
      setError(e instanceof Error ? e.message : "No se pudo completar");
      return null;
    } finally {
      if (!conversation) setBusy(false);
    }
  }
  async function logout() {
    await run({ action: "logout" });
    if (teacher) await supabase.auth.signOut({ scope: "local" });
    qc.clear();
    setError("");
    setEpoch((v) => v + 1);
  }
  const data =
    !account || needsLogin(q.error) || q.data?.role !== "teacher"
      ? undefined
      : (q.data as Data | undefined);
  const teacher = data?.["role"] === "teacher";
  const preferences =
    data?.["role"] === "learner"
      ? ((data as LearnerData).learner.web_preferences ?? defaultLearnerPreferences)
      : undefined;
  const activeTab = teacher
    ? ["studio", "progreso", "device", "deberes"].includes(tab)
      ? tab
      : "aula"
    : ["peluqo", "mundos", "preguntas"].includes(tab)
      ? tab
      : "aventura";
  function navigate(id: string) {
    setTab(id);
    setNotice("");
  }
  return (
    <div
      className={`edu-app is-expedition${preferences ? " student-experience" : ""}`}
      data-study-age={preferences?.ageBand}
      data-study-theme={preferences?.theme}
    >
      <a className="edu-skip" href="#edu-main">
        Ir al panel
      </a>
      <header className="edu-header">
        <Link to="/" className="edu-brand" aria-label="Volver al inicio de Peluqo">
          <BrandMark /> <small>Aula</small>
        </Link>
        {data ? (
          <>
            <nav aria-label="Espacios educativos">
              {(teacher
                ? [
                    ["aula", home ? "En casa" : "Aula"],
                    ["studio", "Studio"],
                    ["progreso", "Seguimiento"],
                    ...(!home ? [["deberes", "Deberes en Mochi"]] : []),
                    ...(!home ? [["device", "Dispositivos"]] : []),
                  ]
                : [
                    ["aventura", "Mi aventura"],
                    ["mundos", "Mundos"],
                    ["preguntas", "Preguntar"],
                    ["peluqo", "Mi Peluqo"],
                  ]
              ).map(([id, label]) => (
                <button
                  key={id}
                  aria-current={activeTab === id ? "page" : undefined}
                  onClick={() => navigate(id!)}
                >
                  {id === "aventura" && <Compass size={18} aria-hidden="true" />}
                  {id === "mundos" && <Globe2 size={18} aria-hidden="true" />}
                  {id === "preguntas" && <MessageCircle size={18} aria-hidden="true" />}
                  {id === "peluqo" && <BookOpen size={18} aria-hidden="true" />}
                  {label}
                </button>
              ))}
            </nav>
            <button className="edu-button edu-exit" onClick={() => void logout()}>
              {!teacher && <LogOut size={16} aria-hidden="true" />}
              Salir
            </button>
          </>
        ) : (
          <span className="edu-header-caption">Docentes y familias</span>
        )}
      </header>
      <main id="edu-main" className="edu-main">
        {q.isPending && account !== null ? (
          <p role="status">Abriendo el panel educativo…</p>
        ) : !data && home ? (
          <div className="edu-panel">
            <h1>Studio en casa</h1>
            <p>{q.error?.message ?? "Abre Studio desde tu cuenta familiar."}</p>
            <Link className="edu-button primary" to="/familia">
              Volver a mi perfil familiar
            </Link>
          </div>
        ) : !data ? (
          <Access
            busy={busy}
            error={error || (needsLogin(q.error) ? "" : (q.error?.message ?? ""))}
            onTeacher={async (email, password) => {
              setBusy(true);
              setError("");
              const r = await supabase.auth.signInWithPassword({ email, password });
              setBusy(false);
              if (r.error) setError("No se pudo entrar. Revisa tus credenciales docentes.");
              else {
                await qc.invalidateQueries({ queryKey: ["education"] });
                setEpoch((v) => v + 1);
                setTab("aula");
              }
            }}
          />
        ) : (
          <>
            <div className="edu-feedback" aria-live="polite">
              {busy && teacher && <p>Guardando los cambios…</p>}
              {error && (
                <p role="alert">
                  {error} <button onClick={() => void q.refetch()}>Volver a cargar</button>
                </p>
              )}
              {notice && <p>{notice}</p>}
            </div>
            {teacher ? (
              <Teacher data={data} tab={activeTab} busy={busy} run={run} notice={setNotice} />
            ) : (
              <StudentAdventure
                key={data["learner"]["id"]}
                data={data as LearnerData}
                tab={activeTab}
                busy={busy}
                run={run}
                notice={setNotice}
                navigate={navigate}
              />
            )}
          </>
        )}
      </main>
      <footer className="edu-footer">
        MOCHI <span>Aprendizaje conectado con el aula</span>
      </footer>
    </div>
  );
}
function Access({
  busy,
  error,
  onTeacher,
}: {
  busy: boolean;
  error: string;
  onTeacher: (email: string, password: string) => Promise<void>;
}) {
  return (
    <div className="edu-access">
      <div className="edu-access-cover">
        <div className="edu-access-copy">
          <span className="edu-cover-mark">
            <BookOpen size={18} aria-hidden="true" /> Mochi y Peluqo Aula
          </span>
          <h1>El aula continúa en Mochi</h1>
          <p>
            Asigna actividades, revisa la práctica y acompaña su aprendizaje. El niño aprende con su
            dispositivo; este panel es para docentes y familias.
          </p>
        </div>
        <FieldGuide mood="wow" className="edu-welcome-mascot" />
      </div>
      <section className="edu-login">
        <span className="edu-entry-icon">
          <Ticket size={24} aria-hidden="true" />
        </span>
        <h2>Entrada docente</h2>
        <p>Entra con tu cuenta adulta autorizada.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void onTeacher(String(f.get("email")), String(f.get("password")));
          }}
        >
          <label>
            Correo docente
            <input name="email" type="email" autoComplete="username" required />
          </label>
          <label>
            Contraseña
            <input name="password" type="password" autoComplete="current-password" required />
          </label>
          <button className="edu-button primary" disabled={busy}>
            {busy ? "Entrando…" : "Entrar al aula"}
          </button>
        </form>
        {error && (
          <p role="alert" className="edu-help">
            {error}
          </p>
        )}
        <Link className="edu-text-button" to="/registro" search={{ tipo: "docente" }}>
          Crear cuenta docente
        </Link>
        <Link className="edu-text-button" to="/familia">
          Seguimiento familiar
        </Link>
      </section>
    </div>
  );
}

function Teacher({
  data: d,
  tab,
  busy,
  run,
  notice,
}: {
  data: TeacherData;
  tab: string;
  busy: boolean;
  run: <const Command>(body: Command) => Promise<TeacherReply<Command> | null>;
  notice: (s: string) => void;
}) {
  const [source, setSource] = useState<Source[]>([]);
  const [classId, setClassId] = useState("");
  const [draft, setDraft] = useState<Mission | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [documentId, setDocumentId] = useState("");
  const [worldTopic, setWorldTopic] = useState("");
  const [pairLearner, setPairLearner] = useState("");
  const [familyCode, setFamilyCode] = useState<{ pupilId: string; code: string }>();
  const home = d["home"] === true;
  const cl = d["classes"].find((c) => c["id"] === classId) ?? d["classes"][0];
  const pupils = d["learners"].filter((l) => l["class_id"] === cl?.id);
  const docs = d["documents"].filter((x) => x["class_id"] === cl?.id);
  const current = draft ?? cl?.draft;
  const selectedId = cl?.id;
  return (
    <>
      <div className="edu-title">
        <div>
          <p className="edu-tag">{home ? "Peluqo en casa" : "Peluqo Aula"}</p>
          <h1>
            {tab === "studio"
              ? "De tus materiales a una aventura"
              : tab === "progreso"
                ? "Qué están aprendiendo"
                : tab === "deberes"
                  ? "Aprender con Mochi en casa"
                  : tab === "device"
                    ? "Un compañero conectado"
                    : home
                      ? "Un estudio para tu familia"
                      : "Tu aula, sus descubrimientos"}
          </h1>
        </div>
        {home && (
          <Link to="/familia" className="edu-text-button">
            Volver a mi perfil familiar
          </Link>
        )}
        {cl && (
          <label>
            Clase activa
            <select
              value={selectedId}
              onChange={(e) => {
                setClassId(e.target.value);
                setDraft(null);
                setReviewed(false);
                setDocumentId("");
                setWorldTopic("");
                setSource([]);
              }}
            >
              {d["classes"].map((c) => (
                <option value={c["id"]} key={c["id"]}>
                  {c["name"]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {cl && tab === "deberes" && !home && (
        <DeviceLessons key={cl.id} role="teacher" pupils={pupils} classId={cl.id} />
      )}
      {(!cl || tab === "aula") && (
        <form
          className="edu-inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            const f = e.currentTarget;
            void run({ action: "create-class", name: new FormData(f).get("name") }).then((r) => {
              if (r) {
                setClassId(r.id);
                f.reset();
              }
            });
          }}
        >
          <label>
            Nombre de una nueva clase
            <input name="name" required maxLength={180} placeholder="Exploradores de 5.º" />
          </label>
          <button className="edu-button" disabled={busy}>
            Crear clase
          </button>
        </form>
      )}
      {cl && tab === "aula" && (
        <>
          <section className="edu-panel">
            <h2>Exploradores de {cl.name}</h2>
            <form
              className="edu-inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                const f = e.currentTarget;
                void run({
                  action: "create-learner",
                  classId: cl.id,
                  name: new FormData(f).get("name"),
                }).then((r) => {
                  if (r) f.reset();
                });
              }}
            >
              <label>
                Nombre o alias del alumno
                <input name="name" required maxLength={60} />
              </label>
              <button className="edu-button primary" disabled={busy}>
                Añadir alumno
              </button>
            </form>
            <p className="edu-help">
              Cada alumno tiene su propio acceso. Puedes elegir su duración y cerrarlo cuando haga
              falta.
            </p>
            {!pupils.length && <p>Añade el primer alumno para preparar su acceso.</p>}
            {pupils.map((l) => (
              <div className="edu-list-row" key={l["id"]}>
                <strong>{l["name"]}</strong>
                <StudentAccessManager learnerId={l["id"]} name={l["name"]} />
                {!home && (
                  <details className="edu-family-access">
                    <summary>Acceso familiar · {l["family_count"]} vinculados</summary>
                    <button
                      type="button"
                      className="edu-button"
                      disabled={busy}
                      onClick={async () => {
                        const r = await run({ action: "issue-family-code", learnerId: l["id"] });
                        if (r) setFamilyCode({ pupilId: l["id"], code: r.code });
                      }}
                    >
                      Crear código familiar
                    </button>
                    <button
                      type="button"
                      className="edu-text-button"
                      disabled={busy}
                      onClick={async () => {
                        const r = await run({ action: "revoke-family-access", learnerId: l["id"] });
                        if (r) {
                          setFamilyCode(undefined);
                          notice(
                            "Se han retirado los vínculos y códigos familiares de este alumno.",
                          );
                        }
                      }}
                    >
                      Retirar accesos familiares
                    </button>
                    {familyCode && familyCode.pupilId === l["id"] && (
                      <p role="status">
                        Código <strong>{familyCode.code}</strong> · válido 24 horas.
                      </p>
                    )}
                  </details>
                )}
                <label className="edu-check">
                  <input
                    type="checkbox"
                    checked={l["support"]}
                    onChange={(e) =>
                      void run({
                        action: "override",
                        learnerId: l["id"],
                        support: e.target.checked,
                      })
                    }
                  />
                  Refuerzo guiado
                </label>
              </div>
            ))}
          </section>
          <section className="edu-panel">
            <h2>Misiones publicadas</h2>
            {d["versions"]
              .filter((v) => v["class_id"] === cl.id)
              .map((v) => (
                <p key={v["id"]}>
                  {v["title"]} · {new Date(v["created_at"]).toLocaleDateString("es")}
                </p>
              ))}
            <p>En Studio puedes crear y revisar la próxima expedición.</p>
          </section>
        </>
      )}
      {cl && tab === "studio" && (
        <div className="edu-studio">
          <section className="edu-panel">
            <h2>1. Materiales de la clase</h2>
            <p>PDF digital o TXT, hasta 10 MB. Conservamos la referencia de cada página.</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                form.set("classId", cl.id);
                void run(form).then((r) => {
                  if (r) {
                    setDocumentId(r.documentId);
                    notice("Material procesado. Ya puedes generar una propuesta.");
                  }
                });
              }}
            >
              <label>
                Documento educativo
                <input name="file" type="file" accept=".pdf,.txt" required />
              </label>
              <button className="edu-button" disabled={busy}>
                Subir y extraer texto
              </button>
            </form>
            <label>
              Material para la propuesta
              <select
                value={documentId || docs[0]?.id || ""}
                onChange={(e) => setDocumentId(e.target.value)}
              >
                {docs.map((x) => (
                  <option value={x["id"]} key={x["id"]}>
                    {x["name"]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Tema del mundo
              <input
                value={worldTopic}
                maxLength={220}
                onChange={(event) => setWorldTopic(event.target.value)}
                placeholder="Por ejemplo, las fases de la Luna"
              />
            </label>
            <button
              className="edu-button primary"
              disabled={busy || !docs.length}
              onClick={() =>
                void run({
                  action: "generate",
                  classId: cl.id,
                  documentId: documentId || docs[0]?.id,
                  topic: worldTopic,
                }).then((r) => {
                  if (r) {
                    setDraft(r.draft);
                    setReviewed(false);
                    notice(
                      "Propuesta real del NAS. Revísala y prueba sus actividades antes de publicarla.",
                    );
                  }
                })
              }
            >
              Generar mundo y actividades
            </button>
            <button
              className="edu-button"
              disabled={busy || !docs.length}
              onClick={() =>
                void run({ action: "document-source", documentId: documentId || docs[0]?.id }).then(
                  (r) => {
                    if (r) setSource(r);
                  },
                )
              }
            >
              Leer fuente extraída
            </button>
            {source.length > 0 && (
              <details open>
                <summary>Texto del material</summary>
                {source.map((c) => (
                  <p key={c["id"]}>
                    <strong>{c["page"] ? `Página ${c["page"]}` : "Texto"}</strong> {c["content"]}
                  </p>
                ))}
              </details>
            )}
          </section>
          <section className="edu-panel">
            <h2>2. Revisar y probar</h2>
            {current ? (
              <>
                <MissionEditor
                  key={cl.id}
                  mission={current}
                  sourceOptions={source as { id: string; page: number | null; content: string }[]}
                  onChange={(m) => {
                    setDraft(m);
                    setReviewed(false);
                  }}
                />
                <button
                  className="edu-button"
                  disabled={busy}
                  onClick={() =>
                    void run({ action: "save-draft", classId: cl.id, mission: current }).then(
                      (r) => {
                        if (r) notice("Borrador guardado.");
                      },
                    )
                  }
                >
                  Guardar borrador
                </button>
                <label className="edu-check">
                  <input
                    type="checkbox"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                  />
                  He comprobado las paradas, los retos y las fuentes
                </label>
                <button
                  className="edu-button primary"
                  disabled={busy || !reviewed}
                  onClick={() =>
                    void run({ action: "save-draft", classId: cl.id, mission: current })
                      .then((r) => r && run({ action: "publish", classId: cl.id }))
                      .then((r) => {
                        if (r) {
                          setReviewed(false);
                          notice("Misión publicada. Las sesiones usarán esta versión sin cambios.");
                        }
                      })
                  }
                >
                  Publicar una versión para la clase
                </button>
              </>
            ) : (
              <p>
                Sube un material y genera una propuesta. No se publicará contenido automáticamente.
              </p>
            )}
          </section>
        </div>
      )}
      {cl && tab === "progreso" && (
        <AulaProgress
          classId={cl.id}
          role={home ? "family" : "teacher"}
          renderControls={(pupil) => <PupilPriority key={pupil.id} learnerId={pupil.id} />}
        />
      )}
      {cl && !home && tab === "device" && (
        <section className="edu-panel">
          <h2>Vincular la placa</h2>
          <p>Abre «Aprender con Peluqo» en la placa e introduce el código que muestra.</p>
          <form
            className="edu-inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              void run({
                action: "approve-pair",
                code: String(new FormData(e.currentTarget).get("code")).toUpperCase(),
                learnerId: pairLearner || pupils[0]?.id,
              }).then((r) => {
                if (r) notice("Dispositivo vinculado. Elige una sesión para acompañar al alumno.");
              });
            }}
          >
            <label>
              Código de la placa
              <input name="code" minLength={8} maxLength={8} required autoComplete="off" />
            </label>
            <label>
              Alumno
              <select
                value={pairLearner || pupils[0]?.id || ""}
                onChange={(e) => setPairLearner(e.target.value)}
              >
                {pupils.map((l) => (
                  <option key={l["id"]} value={l["id"]}>
                    {l["name"]}
                  </option>
                ))}
              </select>
            </label>
            <button className="edu-button primary" disabled={busy || !pupils.length}>
              Confirmar vínculo
            </button>
          </form>
          {d["devices"].map((device) => (
            <div className="edu-device" key={device["id"]}>
              <h3>
                {d["learners"].find((l) => l["id"] === device["learner_id"])?.name ?? "Sin alumno"}
              </h3>
              <p>
                {device["revoked"]
                  ? "Vínculo revocado"
                  : device["last_seen_at"] &&
                      Date.now() - new Date(device["last_seen_at"]).getTime() < 15000
                    ? "Conectado"
                    : "Sin conexión reciente"}
              </p>
              {!device["revoked"] && (
                <>
                  <label>
                    Sesión que acompaña
                    <select
                      value={device["session_id"] ?? ""}
                      onChange={(e) =>
                        void run({
                          action: "bind-device",
                          deviceId: device["id"],
                          sessionId: e.target.value || null,
                        })
                      }
                    >
                      <option value="">Sin sesión activa</option>
                      {d["sessions"]
                        .filter((s) => s["learner_id"] === device["learner_id"])
                        .map((s) => (
                          <option value={s["id"]} key={s["id"]}>
                            {phaseNames[s["phase"]]} ·{" "}
                            {new Date(s["created_at"]).toLocaleTimeString("es")}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button
                    className="edu-button"
                    disabled={busy}
                    onClick={() => void run({ action: "revoke-device", deviceId: device["id"] })}
                  >
                    Revocar dispositivo
                  </button>
                </>
              )}
            </div>
          ))}
        </section>
      )}
    </>
  );
}
