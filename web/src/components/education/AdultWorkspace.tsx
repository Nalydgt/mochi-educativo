import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Clock3,
  FileText,
  GraduationCap,
  Home,
  HeartHandshake,
  Inbox,
  Link2,
  LogOut,
  Menu,
  MessageSquare,
  Monitor,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  Users,
  Wifi,
  X,
} from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { adultRequest, useAdultAccountId } from "@/lib/education/adult-client";
import {
  schoolCommandSchema,
  type SchoolSnapshot,
  type SchoolLesson,
  type SchoolGrade,
  type SchoolMessage,
  type SchoolEvent,
  type SchoolSettings,
} from "@/lib/education/school-schema";
import { AuthForm } from "@/components/AuthForm";
import { CarePanel, CollaborationPanel, RecognitionPanel } from "./SchoolCompanionPanels";
import "./adult-workspace.css";

type View =
  | "overview"
  | "students"
  | "assignments"
  | "reviews"
  | "grades"
  | "calendar"
  | "messages"
  | "devices"
  | "settings"
  | "care"
  | "collaboration"
  | "recognition"
  | "materials";
type Pupil = SchoolSnapshot["learners"][number];
type Payload = Record<string, unknown>;
type Run = <T = Record<string, unknown>>(payload: Payload, endpoint?: string) => Promise<T | null>;
type Drawer =
  | { kind: "assignment"; lesson?: SchoolLesson | undefined; groupId?: string | undefined }
  | { kind: "grade"; grade?: SchoolGrade | undefined; lesson?: SchoolLesson | undefined }
  | { kind: "message"; message?: SchoolMessage | undefined }
  | { kind: "event"; event?: SchoolEvent | undefined }
  | { kind: "student"; pupil: Pupil }
  | null;
const titles: Record<View, string> = {
  overview: "Resumen",
  students: "Clases y alumnos",
  assignments: "Actividades",
  reviews: "Revisión",
  grades: "Calificaciones",
  calendar: "Calendario",
  messages: "Comunicaciones",
  devices: "Dispositivos",
  settings: "Configuración",
  materials: "Materiales",
  care: "Acompañamiento",
  collaboration: "Grupos y ayuda",
  recognition: "Reconocimientos",
};
const navigation = [
  { id: "overview", label: "Resumen", icon: Home },
  { id: "students", label: "Clases y alumnos", icon: Users },
  { id: "assignments", label: "Actividades", icon: BookOpen },
  { id: "reviews", label: "Revisión", icon: ClipboardCheck },
  { id: "grades", label: "Calificaciones", icon: GraduationCap },
  { id: "collaboration", label: "Grupos y ayuda", icon: Users },
  { id: "recognition", label: "Reconocimientos", icon: Sparkles },
  { id: "care", label: "Acompañamiento", icon: HeartHandshake },
  { id: "calendar", label: "Calendario", icon: CalendarDays },
  { id: "messages", label: "Comunicaciones", icon: MessageSquare },
  { id: "materials", label: "Materiales", icon: FileText },
  { id: "devices", label: "Dispositivos", icon: Monitor },
  { id: "settings", label: "Configuración", icon: Settings2 },
] as const;
const familyViews: View[] = [
  "overview",
  "assignments",
  "grades",
  "calendar",
  "messages",
  "devices",
  "settings",
  "care",
  "recognition",
];
const date = (
  value: string,
  options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" },
) =>
  new Intl.DateTimeFormat("es-ES", { timeZone: "Europe/Madrid", ...options }).format(
    new Date(value.length === 10 ? value + "T12:00:00Z" : value),
  );
const fullDate = (value: string) => date(value, { day: "numeric", month: "long", year: "numeric" });
const initials = (name: string) =>
  name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "M";
const pupilName = (data: SchoolSnapshot, id: string) =>
  data.learners.find((pupil) => pupil.id === id)?.name ?? "Alumno";
const lessonStatus = (lesson: SchoolLesson) =>
  !lesson.result
    ? { label: "Pendiente", tone: "outline" }
    : !lesson.review
      ? { label: "Por revisar", tone: "warning" }
      : lesson.review.status === "needs_support"
        ? { label: "Refuerzo recomendado", tone: "info" }
        : { label: "Revisada", tone: "success" };
const timeSpent = (seconds: number) =>
  seconds < 60 ? "Menos de 1 min" : `${Math.round(seconds / 60)} min aprox.`;

export function Badge({ children, tone = "" }: { children: ReactNode; tone?: string }) {
  return <span className={`mw-badge ${tone}`}>{children}</span>;
}
function Empty({
  icon: Icon = BookOpen,
  title,
  children,
  action,
}: {
  icon?: typeof BookOpen;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mw-empty">
      <Icon size={27} strokeWidth={1.5} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
function Field({
  label,
  children,
  full = false,
  help,
}: {
  label: string;
  children: ReactNode;
  full?: boolean;
  help?: string;
}) {
  return (
    <label className={`mw-field${full ? " full" : ""}`}>
      <span>{label}</span>
      {children}
      {help && <small>{help}</small>}
    </label>
  );
}
function Panel({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mw-panel">
      <div className="mw-panel-header">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Dialog({
  title,
  description,
  children,
  onClose,
  feedback,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
  feedback?: { text: string; error?: boolean } | undefined;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      queueMicrotask(() => {
        if (!document.querySelector("dialog[open]") && opener?.isConnected) opener.focus();
      });
    };
  }, []);
  return (
    <dialog
      className="mw-drawer"
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      aria-labelledby="mw-dialog-title"
    >
      <div className="mw-drawer-head">
        <div>
          <h2 id="mw-dialog-title">{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <button className="mw-icon-button" aria-label="Cerrar" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <div className="mw-drawer-body">
        {feedback?.error && (
          <p role="alert" className="mw-feedback error">
            {feedback.text}
          </p>
        )}
        {children}
      </div>
    </dialog>
  );
}
function Loading() {
  return (
    <div className="mochi-workspace">
      <main className="mw-content" aria-busy="true">
        <div className="mw-skeleton big" />
        <div className="mw-skeleton line" />
        <div className="mw-loading-grid">
          {[1, 2, 3].map((n) => (
            <div className="mw-panel" key={n}>
              <div className="mw-skeleton line" />
              <div className="mw-skeleton line" />
            </div>
          ))}
        </div>
        <p role="status" className="mw-subtle" style={{ marginTop: 22 }}>
          Abriendo tu espacio educativo…
        </p>
      </main>
    </div>
  );
}

function AdultConfirmation({
  busy,
  error,
  onConfirm,
  onSignOut,
}: {
  busy: boolean;
  error?: string | undefined;
  onConfirm: () => Promise<void>;
  onSignOut: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  return (
    <div className="mochi-auth">
      <main className="mw-error-page">
        <ShieldCheck size={30} />
        <h1>Tu espacio familiar</h1>
        <p>
          Antes de continuar, confirma que gestionarás esta cuenta como adulto. El centro deberá
          verificar y vincular a cada estudiante por separado.
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (confirmed) void onConfirm();
          }}
        >
          <label className="mw-check" style={{ marginBlock: 22 }}>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              required
            />
            <span>Soy mayor de edad y gestionaré mi espacio familiar.</span>
          </label>
          {error && (
            <p role="alert" className="mw-feedback error">
              {error}
            </p>
          )}
          <div className="mw-form-actions">
            <button className="mw-button primary" disabled={busy || !confirmed}>
              {busy ? "Confirmando…" : "Continuar al panel familiar"}
            </button>
            <button type="button" className="mw-button" onClick={onSignOut}>
              Cerrar sesión
            </button>
          </div>
        </form>
        <p className="mw-note">
          Esta declaración no verifica la tutela ni da acceso a datos de estudiantes. Los vínculos
          requieren autorización del centro.
        </p>
      </main>
    </div>
  );
}

export function AdultWorkspace({ initialView = "overview" }: { initialView?: string | undefined }) {
  const account = useAdultAccountId();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [view, setView] = useState<View>(
    Object.hasOwn(titles, initialView) ? (initialView as View) : "overview",
  );
  const [classId, setClassId] = useState("");
  const [learnerId, setLearnerId] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const menuToggle = useRef<HTMLButtonElement>(null);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean }>();
  const requests = useRef(new Map<string, string>());
  const onboarding = useQuery({
    queryKey: ["adult-onboarding", account],
    queryFn: () =>
      adultRequest<{ role: "teacher" | "family" | null; needsConfirmation: boolean }>(
        "/api/education/adult-onboarding",
      ),
    enabled: !!account,
    retry: false,
  });
  const report = useQuery({
    queryKey: ["school", account],
    queryFn: () => adultRequest<SchoolSnapshot>("/api/education/school"),
    enabled: !!account,
    retry: false,
    refetchInterval: 20000,
  });
  const data = report.data;
  const teacher = data?.role === "teacher";
  const available = teacher
    ? navigation.filter((item) => item.id !== "care")
    : navigation.filter((item) => familyViews.includes(item.id));
  const activeView = available.some((item) => item.id === view) ? view : "overview";
  const pupils = useMemo(
    () =>
      data?.learners.filter(
        (pupil) =>
          (!classId || pupil.classId === classId) && (!learnerId || pupil.id === learnerId),
      ) ?? [],
    [data?.learners, classId, learnerId],
  );
  const pupilIds = useMemo(() => new Set(pupils.map((pupil) => pupil.id)), [pupils]);
  const lessons = useMemo(
    () => data?.lessons.filter((lesson) => pupilIds.has(lesson.learnerId)) ?? [],
    [data?.lessons, pupilIds],
  );
  const pendingReview =
    data?.lessons.filter((lesson) => lesson.result && !lesson.review).length ?? 0;
  const unread =
    data?.messages.filter((message) => !message.readAt && !message.withdrawnAt).length ?? 0;
  const carePending = teacher
    ? 0
    : (data?.careAlerts ?? []).filter(
        (alert) =>
          alert.status === "pending_review" &&
          data?.learners.some((learner) => learner.id === alert.learnerId),
      ).length;
  useEffect(() => {
    if (initialView && Object.hasOwn(titles, initialView)) setView(initialView as View);
  }, [initialView]);
  useEffect(() => {
    if (!menuOpen || !window.matchMedia("(max-width: 760px)").matches) return;
    const toggle = menuToggle.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const controls = () =>
      Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>("a[href],button:not(:disabled)") ?? [],
      );
    controls()[0]?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
      } else if (event.key === "Tab") {
        const items = controls();
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKey);
      if (toggle?.isConnected) toggle.focus();
    };
  }, [menuOpen]);

  function go(next: View) {
    setView(next);
    setDrawer(null);
    setMenuOpen(false);
    setNotice(undefined);
    void navigate({
      to: data?.role === "family" ? "/familia" : "/expedicion",
      search: { panel: next },
    });
  }
  async function run<T = Record<string, unknown>>(
    payload: Payload,
    endpoint = "/api/education/school",
  ): Promise<T | null> {
    setBusy(true);
    setNotice(undefined);
    const key = endpoint + JSON.stringify(payload);
    let identity = requests.current.get(key);
    if (!identity) {
      identity = crypto.randomUUID();
      requests.current.set(key, identity);
    }
    try {
      const body =
        endpoint === "/api/education/school"
          ? schoolCommandSchema.parse({ ...payload, requestId: identity })
          : payload;
      const result = await adultRequest<T>(endpoint, body);
      requests.current.delete(key);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["school", account] }),
        qc.invalidateQueries({ queryKey: ["education"] }),
        qc.invalidateQueries({ queryKey: ["device-lessons"] }),
      ]);
      return result;
    } catch (error) {
      const text =
        error instanceof Error
          ? error.name === "ZodError"
            ? "Revisa los campos del formulario antes de guardar."
            : error.message
          : "No se pudo guardar. Vuelve a intentarlo.";
      setNotice({ text, error: true });
      return null;
    } finally {
      setBusy(false);
    }
  }
  function success(text: string) {
    setNotice({ text });
    setDrawer(null);
  }
  async function signOut() {
    await supabase.auth.signOut({ scope: "local" });
    qc.clear();
    void navigate({ to: "/" });
  }

  if (
    account === undefined ||
    (!!account && (onboarding.isPending || (report.isPending && onboarding.data?.role !== null)))
  )
    return <Loading />;
  if (!account) return <AuthForm />;
  if (onboarding.data?.needsConfirmation)
    return (
      <AdultConfirmation
        busy={busy}
        onConfirm={async () => {
          setBusy(true);
          setNotice(undefined);
          try {
            await adultRequest("/api/education/adult-onboarding", { confirmAdult: true });
            await Promise.all([onboarding.refetch(), report.refetch()]);
          } catch (error) {
            setNotice({
              error: true,
              text: error instanceof Error ? error.message : "No se pudo confirmar la cuenta.",
            });
          } finally {
            setBusy(false);
          }
        }}
        onSignOut={() => void signOut()}
        error={notice?.text}
      />
    );
  if (!data || report.isError)
    return (
      <div className="mochi-workspace">
        <main className="mw-error-page">
          <ShieldCheck size={30} />
          <h1>No hemos podido abrir el panel</h1>
          <p role="alert">
            {report.error?.message ?? "Tu cuenta necesita un acceso docente o familiar autorizado."}
          </p>
          <div className="mw-form-actions">
            <button className="mw-button primary" onClick={() => void report.refetch()}>
              Volver a intentar
            </button>
            <button className="mw-button" onClick={() => void signOut()}>
              Cerrar sesión
            </button>
          </div>
        </main>
      </div>
    );

  return (
    <div className="mochi-workspace">
      <a href="#mw-main" className="mw-skip">
        Ir al contenido
      </a>
      <div className="mw-shell">
        {menuOpen && (
          <button
            className="mw-menu-backdrop"
            aria-label="Cerrar navegación"
            onClick={() => setMenuOpen(false)}
          />
        )}
        <aside
          ref={sidebar}
          id="mw-sidebar"
          className={`mw-sidebar${menuOpen ? " is-open" : ""}`}
          aria-label="Navegación del panel"
        >
          <Link to="/" className="mw-wordmark">
            <span className="mw-mark" aria-hidden="true">
              <span />
            </span>
            <span>
              mochi<small>aprendizaje conectado</small>
            </span>
          </Link>
          <div className="mw-role-label">{teacher ? "ESPACIO DOCENTE" : "ESPACIO FAMILIAR"}</div>
          <nav className="mw-nav">
            {available.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                aria-current={activeView === id ? "page" : undefined}
                onClick={() => go(id)}
              >
                <Icon size={18} strokeWidth={1.7} aria-hidden="true" />
                {!teacher && id === "assignments" ? "Sus actividades" : label}
                {id === "reviews" && pendingReview > 0 && (
                  <span className="mw-nav-count">{pendingReview}</span>
                )}
                {id === "messages" && !teacher && unread > 0 && (
                  <span className="mw-nav-count">{unread}</span>
                )}
                {id === "care" && !teacher && carePending > 0 && (
                  <span className="mw-nav-count">{carePending}</span>
                )}
              </button>
            ))}
          </nav>
          <div className="mw-sidebar-footer">
            <div className="mw-side-device">
              <span className="mw-dot" />
              Datos de tu centro educativo
            </div>
            <p>
              El aprendizaje sucede en Mochi.
              <br />
              Aquí lo acompañamos.
            </p>
            <button onClick={() => void signOut()}>
              <LogOut size={15} />
              Cerrar sesión
            </button>
          </div>
        </aside>
        <div className="mw-main">
          <header className="mw-topbar">
            <button
              ref={menuToggle}
              className="mw-mobile-toggle"
              aria-label="Abrir navegación"
              aria-expanded={menuOpen}
              aria-controls="mw-sidebar"
              onClick={() => setMenuOpen(!menuOpen)}
            >
              <Menu size={18} />
            </button>
            <div className="mw-breadcrumb">
              <span>{teacher ? "Panel docente" : "Panel familiar"}</span>
              <ChevronRight size={13} />
              <strong>{titles[activeView]}</strong>
            </div>
            <div className="mw-topbar-right">
              <time>
                {date(new Date().toISOString(), { weekday: "long", day: "numeric", month: "long" })}
              </time>
              <div className="mw-profile">
                <span className="mw-avatar">{initials(data.adult.name)}</span>
                <span>{data.adult.name}</span>
              </div>
            </div>
          </header>
          <main className="mw-content" id="mw-main" tabIndex={-1}>
            <div className="mw-heading">
              <div>
                <h1>
                  {activeView === "overview"
                    ? teacher
                      ? "Tu aula, al día."
                      : "Acompañar también es comprender."
                    : titles[activeView]}
                </h1>
                <p>{descriptions[activeView][teacher ? 0 : 1]}</p>
              </div>
              <div className="mw-heading-actions">
                {teacher && (activeView === "overview" || activeView === "assignments") && (
                  <button
                    className="mw-button primary"
                    onClick={() => setDrawer({ kind: "assignment" })}
                  >
                    <Plus size={16} />
                    Asignar actividad
                  </button>
                )}
                {teacher && activeView === "grades" && (
                  <button
                    className="mw-button primary"
                    onClick={() => setDrawer({ kind: "grade" })}
                  >
                    <Plus size={16} />
                    Añadir calificación
                  </button>
                )}
                {teacher && activeView === "messages" && (
                  <button
                    className="mw-button primary"
                    onClick={() => setDrawer({ kind: "message" })}
                  >
                    <Plus size={16} />
                    Nuevo comunicado
                  </button>
                )}
                {teacher && activeView === "calendar" && (
                  <button
                    className="mw-button primary"
                    onClick={() => setDrawer({ kind: "event" })}
                  >
                    <Plus size={16} />
                    Añadir evento
                  </button>
                )}
              </div>
            </div>
            {notice && (
              <div
                className={`mw-feedback${notice.error ? " error" : ""}`}
                role={notice.error ? "alert" : "status"}
              >
                {notice.error ? <CircleHelp size={17} /> : <CheckCheck size={17} />}
                <span>{notice.text}</span>
                <button
                  className="mw-icon-button"
                  aria-label="Cerrar mensaje"
                  onClick={() => setNotice(undefined)}
                >
                  <X size={15} />
                </button>
              </div>
            )}
            {!["settings", "messages", "materials", "care", "collaboration"].includes(activeView) &&
              data.learners.length > 0 && (
                <div className="mw-toolbar">
                  <div className="mw-toolbar-left">
                    {teacher && data.classes.length > 0 && (
                      <label className="mw-filter">
                        <Users size={15} />
                        <span className="sr-only">Filtrar por clase</span>
                        <select
                          value={classId}
                          onChange={(event) => {
                            setClassId(event.target.value);
                            setLearnerId("");
                          }}
                        >
                          <option value="">Todas las clases</option>
                          {data.classes.map((item) => (
                            <option value={item.id} key={item.id}>
                              {item.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                    <label className="mw-filter">
                      <span>{teacher ? "Alumno" : "Estudiante"}</span>
                      <select
                        value={learnerId}
                        onChange={(event) => setLearnerId(event.target.value)}
                      >
                        <option value="">
                          {teacher ? "Todos los alumnos" : "Todos los estudiantes"}
                        </option>
                        {data.learners
                          .filter((pupil) => !classId || pupil.classId === classId)
                          .map((pupil) => (
                            <option value={pupil.id} key={pupil.id}>
                              {pupil.name}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                  <span className="mw-status-line">
                    <RefreshCw size={12} />
                    Actualizado{" "}
                    {report.dataUpdatedAt
                      ? date(new Date(report.dataUpdatedAt).toISOString(), {
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "ahora"}
                  </span>
                </div>
              )}
            {activeView === "overview" && (
              <>
                {!teacher && carePending > 0 && (
                  <div className="mw-feedback">
                    <HeartHandshake size={18} />
                    <span>
                      Tienes{" "}
                      {carePending === 1
                        ? "un aviso de acompañamiento pendiente"
                        : `${carePending} avisos de acompañamiento pendientes`}
                      .
                    </span>
                    <button className="mw-text-button" onClick={() => go("care")}>
                      Revisar avisos
                    </button>
                  </div>
                )}
                <Overview data={data} pupils={pupils} lessons={lessons} go={go} open={setDrawer} />
              </>
            )}
            {activeView === "students" && teacher && (
              <Students
                data={data}
                pupils={pupils}
                classId={classId}
                busy={busy}
                run={run}
                success={success}
                open={setDrawer}
              />
            )}
            {(activeView === "assignments" || activeView === "reviews") && (
              <Assignments
                data={data}
                lessons={
                  activeView === "reviews" ? lessons.filter((lesson) => !!lesson.result) : lessons
                }
                reviewOnly={activeView === "reviews"}
                open={setDrawer}
              />
            )}
            {activeView === "grades" && <Grades data={data} pupilIds={pupilIds} open={setDrawer} />}
            {activeView === "calendar" && (
              <Calendar data={data} lessons={lessons} pupilIds={pupilIds} open={setDrawer} />
            )}
            {activeView === "messages" && (
              <Messages data={data} busy={busy} run={run} success={success} open={setDrawer} />
            )}
            {activeView === "devices" && (
              <Devices data={data} pupils={pupils} busy={busy} run={run} success={success} />
            )}
            {activeView === "settings" && (
              <Settings data={data} busy={busy} run={run} success={success} />
            )}
            {activeView === "materials" && teacher && (
              <Materials data={data} run={run} busy={busy} success={success} />
            )}
            {activeView === "care" && !teacher && (
              <CarePanel
                data={data}
                run={run}
                busy={busy}
                success={success}
                configure={() => go("settings")}
              />
            )}
            {activeView === "recognition" && <RecognitionPanel data={data} pupilIds={pupilIds} />}
            {activeView === "collaboration" && teacher && (
              <CollaborationPanel
                data={data}
                run={run}
                busy={busy}
                success={success}
                assign={(groupId) => setDrawer({ kind: "assignment", groupId })}
              />
            )}
          </main>
        </div>
      </div>
      {drawer?.kind === "assignment" && (
        <Dialog
          feedback={notice}
          title={drawer.lesson ? drawer.lesson.title : "Asignar una actividad"}
          description={
            drawer.lesson
              ? `${drawer.lesson.learnerName} · Entrega ${fullDate(drawer.lesson.dueAt)}`
              : "Prepara una práctica breve. Mochi la recibirá al sincronizar."
          }
          onClose={() => setDrawer(null)}
        >
          {drawer.lesson ? (
            <LessonDetail
              lesson={
                data.lessons.find((lesson) => lesson.id === drawer.lesson!.id) ?? drawer.lesson
              }
              teacher={teacher}
              busy={busy}
              run={run}
              success={success}
              onGrade={() => setDrawer({ kind: "grade", lesson: drawer.lesson })}
            />
          ) : (
            <AssignmentForm
              data={data}
              classId={classId}
              groupId={drawer.groupId}
              run={run}
              busy={busy}
              success={success}
            />
          )}
        </Dialog>
      )}
      {drawer?.kind === "grade" && teacher && (
        <Dialog
          feedback={notice}
          title={drawer.grade ? "Editar calificación" : "Añadir calificación"}
          description="La calificación la introduce y publica el docente. Mochi no asigna notas oficiales."
          onClose={() => setDrawer(null)}
        >
          <GradeForm
            data={data}
            grade={drawer.grade}
            lesson={drawer.lesson}
            busy={busy}
            run={run}
            success={success}
          />
        </Dialog>
      )}
      {drawer?.kind === "message" && teacher && (
        <Dialog
          feedback={notice}
          title="Nuevo comunicado"
          description="Elige a qué familias se dirige y si pueden responder."
          onClose={() => setDrawer(null)}
        >
          <MessageForm data={data} classId={classId} busy={busy} run={run} success={success} />
        </Dialog>
      )}
      {drawer?.kind === "event" && teacher && (
        <Dialog
          feedback={notice}
          title={drawer.event ? "Editar evento" : "Añadir al calendario"}
          onClose={() => setDrawer(null)}
        >
          <EventForm
            data={data}
            event={drawer.event}
            classId={classId}
            busy={busy}
            run={run}
            success={success}
          />
        </Dialog>
      )}
      {drawer?.kind === "student" && teacher && (
        <Dialog
          feedback={notice}
          title={drawer.pupil.name}
          description="Perfil educativo y acceso familiar"
          onClose={() => setDrawer(null)}
        >
          <StudentForm pupil={drawer.pupil} data={data} busy={busy} run={run} success={success} />
        </Dialog>
      )}
    </div>
  );
}

const descriptions: Record<View, [string, string]> = {
  overview: [
    "Lo que necesita tu atención, para que puedas centrarte en enseñar.",
    "Su práctica, los mensajes del centro y los próximos compromisos, en un mismo lugar.",
  ],
  students: [
    "Organiza tu aula y conecta a cada estudiante con sus adultos autorizados.",
    "Perfiles educativos y vínculos con el centro.",
  ],
  assignments: [
    "Actividades que empiezan en clase y continúan en Mochi.",
    "Qué está practicando y cómo puedes acompañarle.",
  ],
  reviews: [
    "Lee las evidencias y añade tu criterio docente.",
    "Observaciones de su docente sobre la práctica.",
  ],
  grades: [
    "Calificaciones introducidas y publicadas por el docente.",
    "Las calificaciones y observaciones que ha publicado el centro.",
  ],
  calendar: [
    "Entregas, reuniones y fechas importantes para tu aula.",
    "Las próximas entregas y citas de tu familia con el centro.",
  ],
  messages: [
    "Comunicados y conversaciones con las familias de tu aula.",
    "Mensajes del centro, con respuestas cuando el docente las habilita.",
  ],
  devices: [
    "Vínculos y últimas sincronizaciones de los dispositivos.",
    "El Mochi de cada estudiante y su última conexión conocida.",
  ],
  settings: [
    "Ajustes de uso, idioma y permisos por estudiante.",
    "Decide cuándo y cómo utilizar Mochi, con control sobre los datos opcionales.",
  ],
  materials: [
    "Los documentos de tu aula, preparados para consultar y crear actividades.",
    "Materiales del centro educativo.",
  ],
  care: ["", "Avisos privados para conversar y acompañar a tu familia."],
  collaboration: ["Equipos pequeños y ayuda voluntaria, acompañados por el docente.", ""],
  recognition: [
    "Participación y colaboración registradas, sin clasificaciones.",
    "Su participación y colaboración, con un registro privado para tu familia.",
  ],
};

function Overview({
  data,
  pupils,
  lessons,
  go,
  open,
}: {
  data: SchoolSnapshot;
  pupils: Pupil[];
  lessons: SchoolLesson[];
  go: (view: View) => void;
  open: (drawer: Drawer) => void;
}) {
  const teacher = data.role === "teacher";
  const waiting = lessons.filter((lesson) => !lesson.result);
  const review = lessons.filter((lesson) => lesson.result && !lesson.review);
  const ids = new Set(pupils.map((pupil) => pupil.id));
  const grades = data.grades
    .filter((grade) => ids.has(grade.learnerId) && grade.publishedAt)
    .slice(0, 4);
  const unread = data.messages.filter((message) => !message.readAt && !message.withdrawnAt);
  const agenda = [
    ...waiting.map((lesson) => ({
      id: lesson.id,
      title: lesson.title,
      at: lesson.dueAt,
      label: "Entrega",
      description: lesson.learnerName,
    })),
    ...data.events
      .filter((event) => !event.cancelledAt && event.learnerIds.some((id) => ids.has(id)))
      .map((event) => ({
        id: event.id,
        title: event.title,
        at: event.startsAt,
        label: event.kind === "meeting" ? "Reunión" : event.kind === "exam" ? "Examen" : "Centro",
        description: event.description,
      })),
  ]
    .filter(
      (item) =>
        new Date(item.at.length === 10 ? item.at + "T23:59:59" : item.at).getTime() >=
        Date.now() - 86400000,
    )
    .sort((a, b) => a.at.localeCompare(b.at))
    .slice(0, 4);
  return (
    <>
      <div className="mw-stats">
        <div className="mw-stat">
          <strong>{pupils.length}</strong>
          <span>{teacher ? "Alumnos en tu selección" : "Estudiantes vinculados"}</span>
        </div>
        <div className="mw-stat">
          <strong>{waiting.length}</strong>
          <span>Actividades pendientes</span>
        </div>
        <div className="mw-stat">
          <strong className={review.length ? "is-attention" : ""}>
            {teacher ? review.length : lessons.filter((lesson) => !!lesson.result).length}
          </strong>
          <span>{teacher ? "Entregas por revisar" : "Actividades realizadas"}</span>
        </div>
        <div className="mw-stat">
          <strong>
            {teacher
              ? data.messages.filter((message) => !message.withdrawnAt).length
              : unread.length}
          </strong>
          <span>{teacher ? "Comunicados enviados" : "Mensajes sin leer"}</span>
        </div>
      </div>
      <div className="mw-two-column">
        <Panel
          title={teacher ? "Lo que necesita tu atención" : "Su aprendizaje reciente"}
          description={
            teacher
              ? "La práctica de Mochi aporta contexto. Tu revisión aporta criterio."
              : "Evidencias breves de lo que ha practicado con Mochi."
          }
          action={
            <button
              className="mw-text-button"
              onClick={() => go(teacher ? "reviews" : "assignments")}
            >
              Ver todo
              <ArrowRight size={14} />
            </button>
          }
        >
          {(teacher ? review : lessons.filter((lesson) => lesson.result)).length ? (
            <ul className="mw-list">
              {(teacher ? review : lessons.filter((lesson) => lesson.result))
                .slice(0, 4)
                .map((lesson) => (
                  <li key={lesson.id}>
                    <div className="mw-list-row">
                      <div className="mw-list-leading">
                        <span className="mw-list-icon">
                          <ClipboardCheck size={18} />
                        </span>
                        <div>
                          <h3>{lesson.title}</h3>
                          <p>
                            {lesson.learnerName} · {lesson.result?.attempts} intentos,{" "}
                            {lesson.result?.hints} {lesson.result?.hints === 1 ? "pista" : "pistas"}
                          </p>
                          <Badge tone={lessonStatus(lesson).tone}>
                            {lessonStatus(lesson).label}
                          </Badge>
                        </div>
                      </div>
                      <button
                        className="mw-button small"
                        onClick={() => open({ kind: "assignment", lesson })}
                      >
                        {teacher ? "Revisar" : "Consultar"}
                      </button>
                    </div>
                  </li>
                ))}
            </ul>
          ) : (
            <Empty
              icon={CheckCheck}
              title={teacher ? "Todo está al día" : "La primera práctica está por llegar"}
            >
              {teacher
                ? "Las nuevas entregas aparecerán aquí cuando Mochi sincronice los resultados."
                : "Aquí podrás consultar las actividades que complete y sincronice con su Mochi."}
            </Empty>
          )}
          <p className="mw-note">
            <ShieldCheck size={14} />
            Las evidencias de práctica se muestran separadas de las calificaciones oficiales.
          </p>
        </Panel>
        <Panel
          title="En el calendario"
          description="Próximas entregas y compromisos."
          action={
            <button className="mw-text-button" onClick={() => go("calendar")}>
              Abrir
              <ArrowRight size={14} />
            </button>
          }
        >
          {agenda.length ? (
            <ul className="mw-list">
              {agenda.map((item) => (
                <li key={item.id}>
                  <div className="mw-list-leading">
                    <div className="mw-agenda-date">
                      {date(item.at, { day: "numeric" })}
                      <small>{date(item.at, { month: "short" })}</small>
                    </div>
                    <div>
                      <h3>{item.title}</h3>
                      <p className="mw-subtle">
                        {item.description.length > 100
                          ? item.description.slice(0, 100) + "…"
                          : item.description}
                      </p>
                      <Badge>{item.label}</Badge>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty icon={CalendarDays} title="Sin próximos compromisos">
              Las fechas de entrega y eventos del centro aparecerán aquí.
            </Empty>
          )}
        </Panel>
      </div>
      <div className="mw-section mw-two-column">
        <Panel
          title={teacher ? "Últimos comunicados" : "Del centro a tu familia"}
          action={
            <button className="mw-text-button" onClick={() => go("messages")}>
              Abrir buzón
              <ArrowRight size={14} />
            </button>
          }
        >
          {data.messages.filter((message) => !message.withdrawnAt).length ? (
            <ul className="mw-list">
              {data.messages
                .filter((message) => !message.withdrawnAt)
                .slice(0, 3)
                .map((message) => (
                  <li key={message.id}>
                    <div className="mw-list-leading">
                      <Inbox size={17} />
                      <div>
                        <h3>{message.title}</h3>
                        <p className="mw-subtle">
                          {message.authorName} · {date(message.createdAt)}
                        </p>
                      </div>
                    </div>
                  </li>
                ))}
            </ul>
          ) : (
            <Empty icon={Inbox} title="El buzón está tranquilo">
              Los comunicados del centro se guardarán aquí.
            </Empty>
          )}
        </Panel>
        <Panel
          title="Calificaciones publicadas"
          description="Introducidas por el docente, con autor y fecha."
          action={
            <button className="mw-text-button" onClick={() => go("grades")}>
              Consultar
              <ArrowRight size={14} />
            </button>
          }
        >
          {grades.length ? (
            <ul className="mw-list">
              {grades.map((grade) => (
                <li key={grade.id}>
                  <div className="mw-list-row">
                    <div>
                      <h3>{grade.title}</h3>
                      <p className="mw-subtle">
                        {pupilName(data, grade.learnerId)} · {grade.subject}
                      </p>
                    </div>
                    <span className="mw-grade-value">
                      {grade.value.toLocaleString("es")}
                      <small> / 10</small>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty icon={GraduationCap} title="Todavía no hay notas publicadas">
              Las actividades de Mochi no generan una calificación automáticamente.
            </Empty>
          )}
        </Panel>
      </div>
      {data.role === "family" && (
        <FamilyLink
          runStandalone={async (code) => {
            await adultRequest("/api/education/progress", { code });
          }}
        />
      )}
    </>
  );
}

function FamilyLink({ runStandalone }: { runStandalone: (code: string) => Promise<void> }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  return (
    <section className="mw-panel mw-section">
      <details className="mw-inline-details">
        <summary>
          <Link2 size={14} style={{ display: "inline", marginRight: 6 }} />
          Vincular otro estudiante del centro
        </summary>
        <p className="mw-subtle">
          Introduce el código familiar que te ha entregado el docente. Este vínculo te permite ver
          únicamente los datos autorizados de ese estudiante.
        </p>
        <form
          className="mw-form"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            setBusy(true);
            setError("");
            setNotice("");
            try {
              await runStandalone(String(new FormData(form).get("code")));
              await qc.invalidateQueries({ queryKey: ["school"] });
              setNotice("Estudiante vinculado a tu cuenta familiar.");
              form.reset();
            } catch (reason) {
              setError(reason instanceof Error ? reason.message : "No se pudo validar el código.");
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label="Código familiar">
            <input
              name="code"
              required
              minLength={8}
              maxLength={40}
              placeholder="F-…"
              autoComplete="off"
            />
          </Field>
          <div className="mw-form-actions">
            <button className="mw-button" disabled={busy}>
              {busy ? "Vinculando…" : "Vincular estudiante"}
            </button>
          </div>
        </form>
        {error && (
          <p role="alert" className="mw-subtle">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="mw-subtle">
            {notice}
          </p>
        )}
      </details>
    </section>
  );
}

function Students({
  data,
  pupils,
  classId,
  run,
  busy,
  success,
  open,
}: {
  data: SchoolSnapshot;
  pupils: Pupil[];
  classId: string;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
  open: (drawer: Drawer) => void;
}) {
  const [creating, setCreating] = useState<"class" | "pupil" | null>(null);
  return (
    <>
      <div className="mw-toolbar">
        <p className="mw-subtle">
          {data.classes.length} {data.classes.length === 1 ? "clase" : "clases"} ·{" "}
          {data.learners.length} alumnos
        </p>
        <div className="mw-toolbar-left">
          <button
            className="mw-button"
            onClick={() => setCreating(creating === "class" ? null : "class")}
          >
            <Plus size={15} />
            Crear clase
          </button>
          <button
            className="mw-button primary"
            disabled={!data.classes.length}
            onClick={() => setCreating(creating === "pupil" ? null : "pupil")}
          >
            <Plus size={15} />
            Añadir alumno
          </button>
        </div>
      </div>
      {creating && (
        <Panel title={creating === "class" ? "Nueva clase" : "Nuevo alumno"}>
          <form
            className="mw-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const fields = new FormData(form);
              const result = await run(
                creating === "class"
                  ? { action: "create-class", name: fields.get("name") }
                  : {
                      action: "create-learner",
                      classId: fields.get("classId"),
                      name: fields.get("name"),
                    },
                "/api/education/",
              );
              if (result) {
                setCreating(null);
                success(creating === "class" ? "Clase creada." : "Alumno incorporado al aula.");
              }
            }}
          >
            <Field
              label={creating === "class" ? "Nombre de la clase" : "Nombre o alias del alumno"}
            >
              <input
                name="name"
                required
                minLength={2}
                maxLength={creating === "class" ? 180 : 60}
                placeholder={
                  creating === "class" ? "3.º de Primaria · A" : "Alias que utiliza en el aula"
                }
              />
            </Field>
            {creating === "pupil" && (
              <Field label="Clase">
                <select name="classId" defaultValue={classId || data.classes[0]?.id}>
                  {data.classes.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <div className="mw-form-actions">
              <button className="mw-button primary" disabled={busy}>
                {busy ? "Guardando…" : creating === "class" ? "Crear clase" : "Añadir alumno"}
              </button>
              <button type="button" className="mw-button" onClick={() => setCreating(null)}>
                Cancelar
              </button>
            </div>
          </form>
        </Panel>
      )}
      <Panel
        title="Tu alumnado"
        description="Acceso individual, acompañamiento familiar y perfil educativo."
      >
        {pupils.length ? (
          <div className="mw-table-wrap">
            <table className="mw-table">
              <thead>
                <tr>
                  <th>Alumno</th>
                  <th>Clase</th>
                  <th>Perfil educativo</th>
                  <th>Mochi</th>
                  <th>
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {pupils.map((pupil) => (
                  <tr key={pupil.id}>
                    <td>
                      <div className="mw-table-person">
                        <span className="mw-avatar">{initials(pupil.name)}</span>
                        <strong>{pupil.name}</strong>
                      </div>
                    </td>
                    <td>{data.classes.find((item) => item.id === pupil.classId)?.name}</td>
                    <td>
                      {pupil.gradeLabel || "Curso por definir"}
                      <small>{pupil.ageBand} años</small>
                    </td>
                    <td>
                      <Badge
                        tone={
                          data.devices.some(
                            (device) => device.learnerId === pupil.id && !device.revoked,
                          )
                            ? "success"
                            : "outline"
                        }
                      >
                        {data.devices.some(
                          (device) => device.learnerId === pupil.id && !device.revoked,
                        )
                          ? "Vinculado"
                          : "Sin vincular"}
                      </Badge>
                    </td>
                    <td>
                      <button
                        className="mw-button small"
                        onClick={() => open({ kind: "student", pupil })}
                      >
                        Gestionar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty icon={Users} title="Prepara tu primera clase">
            Crea una clase y añade a sus alumnos. Después podrás vincular sus Mochi y asignar
            actividades.
          </Empty>
        )}
      </Panel>
    </>
  );
}

function StudentForm({
  pupil,
  data,
  run,
  busy,
  success,
}: {
  pupil: Pupil;
  data: SchoolSnapshot;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  const [code, setCode] = useState("");
  return (
    <>
      <form
        className="mw-form"
        onSubmit={async (event) => {
          event.preventDefault();
          const fields = new FormData(event.currentTarget);
          if (
            await run({
              action: "save-profile",
              learnerId: pupil.id,
              ageBand: fields.get("ageBand"),
              gradeLabel: fields.get("gradeLabel"),
            })
          )
            success("Perfil educativo guardado.");
        }}
      >
        <Field label="Curso orientativo">
          <input
            name="gradeLabel"
            maxLength={80}
            defaultValue={pupil.gradeLabel}
            placeholder="3.º de Primaria"
          />
        </Field>
        <Field label="Franja de edad">
          <select name="ageBand" defaultValue={pupil.ageBand}>
            {["6–8", "9–12", "13–15", "16–18"].map((age) => (
              <option key={age}>{age}</option>
            ))}
          </select>
        </Field>
        <div className="mw-form-actions">
          <button className="mw-button primary" disabled={busy}>
            Guardar perfil
          </button>
        </div>
      </form>
      <hr style={{ border: 0, borderTop: "1px solid var(--mw-line)", margin: "25px 0" }} />
      <h3>Acceso de su familia</h3>
      <p className="mw-subtle">
        Entrega el código a un tutor legal verificado por el centro. El código caduca a las 24 horas
        y se utiliza una vez.
      </p>
      <div className="mw-form-actions">
        <button
          className="mw-button"
          disabled={busy}
          onClick={async () => {
            const result = await run<{ code: string }>(
              { action: "issue-family-code", learnerId: pupil.id },
              "/api/education/",
            );
            if (result) setCode(result.code);
          }}
        >
          Crear código familiar
        </button>
        <button
          className="mw-button danger"
          disabled={busy}
          onClick={async () => {
            if (
              window.confirm(
                `¿Retirar los accesos familiares de ${pupil.name}? Los adultos deberán vincularse de nuevo.`,
              ) &&
              (await run(
                { action: "revoke-family-access", learnerId: pupil.id },
                "/api/education/",
              ))
            ) {
              setCode("");
              success("Accesos familiares retirados.");
            }
          }}
        >
          Retirar vínculos
        </button>
      </div>
      {code && (
        <p className="mw-feedback" role="status" style={{ marginTop: 16 }}>
          Código familiar: <strong>{code}</strong>
        </p>
      )}
      <p className="mw-note">
        <ShieldCheck size={14} />
        Los permisos se comprueban por alumno. Las familias no ven los datos de otras clases.
      </p>
      <p className="mw-subtle">{data.classes.find((item) => item.id === pupil.classId)?.name}</p>
    </>
  );
}

function Assignments({
  data,
  lessons,
  reviewOnly,
  open,
}: {
  data: SchoolSnapshot;
  lessons: SchoolLesson[];
  reviewOnly: boolean;
  open: (drawer: Drawer) => void;
}) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const visible = lessons.filter(
    (lesson) =>
      (filter === "all" ||
        (filter === "pending" && !lesson.result) ||
        (filter === "review" && !!lesson.result && !lesson.review) ||
        (filter === "reviewed" && !!lesson.review)) &&
      `${lesson.title} ${lesson.learnerName}`
        .toLocaleLowerCase("es")
        .includes(search.toLocaleLowerCase("es")),
  );
  return (
    <Panel
      title={reviewOnly ? "Entregas del dispositivo" : "Actividades asignadas"}
      description={
        reviewOnly
          ? "Revisa cómo ha llegado a la respuesta, además del resultado."
          : "Una tarea descargada sigue disponible aunque el dispositivo pierda conexión."
      }
    >
      <div className="mw-toolbar">
        <label className="mw-search">
          <Search size={15} />
          <span className="sr-only">Buscar actividad o alumno</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar actividad o alumno"
          />
        </label>
        <label className="mw-filter">
          <span className="sr-only">Estado de actividad</span>
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">Todos los estados</option>
            {!reviewOnly && <option value="pending">Pendientes</option>}
            <option value="review">Por revisar</option>
            <option value="reviewed">Revisadas</option>
          </select>
        </label>
      </div>
      {visible.length ? (
        <div className="mw-table-wrap">
          <table className="mw-table">
            <thead>
              <tr>
                <th>Actividad</th>
                <th>Estudiante</th>
                <th>Entrega</th>
                <th>Estado</th>
                <th>
                  <span className="sr-only">Consultar</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((lesson) => (
                <tr key={lesson.id}>
                  <td>
                    <strong>{lesson.title}</strong>
                    <small>Matemáticas · {lesson.factors.length} ejercicios</small>
                  </td>
                  <td>{lesson.learnerName}</td>
                  <td>{date(lesson.dueAt)}</td>
                  <td>
                    <Badge tone={lessonStatus(lesson).tone}>{lessonStatus(lesson).label}</Badge>
                  </td>
                  <td>
                    <button
                      className="mw-button small"
                      onClick={() => open({ kind: "assignment", lesson })}
                    >
                      {data.role === "teacher" && lesson.result && !lesson.review
                        ? "Revisar"
                        : "Consultar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          icon={reviewOnly ? ClipboardCheck : BookOpen}
          title={
            search || filter !== "all"
              ? "No hay coincidencias"
              : reviewOnly
                ? "Sin entregas por revisar"
                : "Todavía no hay actividades"
          }
        >
          {search || filter !== "all"
            ? "Prueba otro nombre o cambia el filtro de estado."
            : reviewOnly
              ? "Las evidencias aparecerán cuando Mochi sincronice una actividad realizada."
              : data.role === "teacher"
                ? "Asigna la primera práctica a un alumno o a una clase completa."
                : "Las actividades que prepare su docente aparecerán aquí."}
        </Empty>
      )}
    </Panel>
  );
}

function Recipients({
  data,
  classId = "",
  defaultIds = [],
}: {
  data: SchoolSnapshot;
  classId?: string;
  defaultIds?: string[];
}) {
  const [mode, setMode] = useState(defaultIds.length ? "selected" : "class");
  const [selectedClass, setSelectedClass] = useState(classId || data.classes[0]?.id || "");
  return (
    <>
      <Field label="Destinatarios">
        <select name="recipientMode" value={mode} onChange={(event) => setMode(event.target.value)}>
          <option value="class">Una clase completa</option>
          <option value="selected">Alumnos seleccionados</option>
        </select>
      </Field>
      <Field label="Clase">
        <select
          name="recipientClass"
          value={selectedClass}
          onChange={(event) => setSelectedClass(event.target.value)}
        >
          {data.classes.map((item) => (
            <option value={item.id} key={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      {mode === "selected" && (
        <fieldset className="mw-recipient-list">
          <legend>Selecciona al menos un alumno</legend>
          {data.learners
            .filter((pupil) => !selectedClass || pupil.classId === selectedClass)
            .map((pupil) => (
              <label className="mw-check" key={pupil.id}>
                <input
                  type="checkbox"
                  name="learnerIds"
                  value={pupil.id}
                  defaultChecked={defaultIds.includes(pupil.id)}
                />
                {pupil.name}
              </label>
            ))}
        </fieldset>
      )}
    </>
  );
}
function recipientPayload(fields: FormData) {
  return fields.get("recipientMode") === "class"
    ? { classId: fields.get("recipientClass") }
    : { learnerIds: fields.getAll("learnerIds") };
}

function AssignmentForm({
  data,
  classId,
  groupId,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  classId: string;
  groupId?: string | undefined;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  const form = useRef<HTMLFormElement>(null);
  const [topic, setTopic] = useState("");
  const [suggested, setSuggested] = useState(false);
  const [error, setError] = useState("");
  const group = groupId
    ? data.groups?.find((item) => item.id === groupId && !item.archivedAt)
    : undefined;
  if (!data.learners.length)
    return (
      <Empty icon={Users} title="Primero incorpora a tus alumnos">
        Crea una clase y añade al menos un estudiante antes de asignar una actividad.
      </Empty>
    );
  return (
    <>
      <details className="mw-inline-details" style={{ marginTop: 0, marginBottom: 22 }}>
        <summary>
          <Sparkles size={14} style={{ display: "inline", marginRight: 5 }} />
          Preparar una propuesta con ayuda de IA
        </summary>
        <Field label="¿Qué quieres reforzar?">
          <input
            value={topic}
            minLength={4}
            maxLength={400}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Multiplicación como agrupaciones, 3.º de Primaria"
          />
        </Field>
        <button
          type="button"
          className="mw-button small"
          style={{ marginTop: 10 }}
          disabled={busy || topic.trim().length < 4}
          onClick={async () => {
            const draft = await run<{
              title: string;
              goal: string;
              instructions: string;
              factors: [number, number][];
            }>({
              action: "suggest-assignment",
              classId:
                group?.classId ??
                (form.current
                  ? new FormData(form.current).get("recipientClass")
                  : classId || data.classes[0]?.id),
              topic,
              count: 3,
            });
            if (!draft || !form.current) return;
            for (const [key, value] of Object.entries({
              title: draft.title,
              goal: draft.goal,
              instructions: draft.instructions,
              factors: draft.factors.map(([a, b]) => `${a}×${b}`).join(", "),
            })) {
              const input = form.current.elements.namedItem(key) as
                HTMLInputElement | HTMLTextAreaElement | null;
              if (input) input.value = value;
            }
            setSuggested(true);
          }}
        >
          {busy ? "Preparando propuesta…" : "Crear propuesta editable"}
        </button>
        <p className="mw-note">
          La propuesta no se asigna automáticamente. Comprueba el contenido y adapta el nivel antes
          de enviar.
        </p>
      </details>
      {suggested && (
        <p className="mw-feedback" role="status">
          <Sparkles size={16} />
          Propuesta preparada. Revisa todos los campos antes de asignarla.
        </p>
      )}
      <form
        ref={form}
        className="mw-form"
        onSubmit={async (event) => {
          event.preventDefault();
          setError("");
          const fields = new FormData(event.currentTarget);
          const factors = String(fields.get("factors"))
            .split(",")
            .map((entry) =>
              entry
                .trim()
                .split(/[x×*]/i)
                .map((value) => Number(value.trim())),
            );
          const payload = {
            ...(groupId
              ? { action: "assign-group", groupId }
              : { action: "batch-assign", ...recipientPayload(fields) }),
            title: fields.get("title"),
            subject: "matematicas",
            goal: fields.get("goal"),
            instructions: fields.get("instructions"),
            dueAt: fields.get("dueAt"),
            factors,
          };
          const checked = schoolCommandSchema.safeParse({
            ...payload,
            requestId: crypto.randomUUID(),
          });
          if (!checked.success) {
            setError(checked.error.issues[0]?.message ?? "Revisa los campos de la actividad.");
            return;
          }
          if (await run(payload))
            success("Actividad asignada. Llegará a los Mochi vinculados al sincronizar.");
        }}
      >
        {groupId ? (
          <div className="mw-field full">
            <strong>Equipo: {group?.name ?? "Grupo seleccionado"}</strong>
            <p className="mw-subtle">
              Cada integrante recibe su actividad individual. El reconocimiento del equipo espera a
              que todas las revisiones estén compartidas.
            </p>
          </div>
        ) : (
          <Recipients data={data} classId={classId} />
        )}
        <Field label="Título" full>
          <input
            name="title"
            required
            minLength={3}
            maxLength={80}
            defaultValue="Aprendemos a formar grupos"
          />
        </Field>
        <Field label="Asignatura">
          <input value="Matemáticas" readOnly />
        </Field>
        <Field label="Fecha de entrega">
          <input type="date" name="dueAt" required />
        </Field>
        <Field label="Objetivo educativo" full>
          <input
            name="goal"
            required
            minLength={8}
            maxLength={300}
            defaultValue="Comprender la multiplicación mediante grupos iguales."
          />
        </Field>
        <Field
          label="Consigna para Mochi"
          full
          help="Una instrucción breve, que el estudiante pueda comprender por voz o en la pantalla."
        >
          <textarea
            name="instructions"
            required
            minLength={8}
            maxLength={200}
            defaultValue="Enséñame cuántos objetos hay en estos grupos. Podemos contar juntos si lo necesitas."
          />
        </Field>
        <Field
          label="Ejercicios"
          full
          help="Entre 1 y 5 multiplicaciones, con factores del 1 al 12. Sepáralas con comas."
        >
          <input name="factors" required defaultValue="3×4, 4×3, 2×6" />
        </Field>
        {error && (
          <p role="alert" className="mw-field full" style={{ color: "var(--mw-error)" }}>
            {error}
          </p>
        )}
        <div className="mw-form-actions">
          <button className="mw-button primary" disabled={busy}>
            {busy ? "Asignando…" : "Asignar actividad"}
          </button>
          <p>Revisa la consigna y los destinatarios antes de asignar.</p>
        </div>
      </form>
    </>
  );
}

function LessonDetail({
  lesson,
  teacher,
  run,
  busy,
  success,
  onGrade,
}: {
  lesson: SchoolLesson;
  teacher: boolean;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
  onGrade: () => void;
}) {
  return (
    <>
      <div className="mw-list-row">
        <Badge tone={lessonStatus(lesson).tone}>{lessonStatus(lesson).label}</Badge>
        <span className="mw-subtle">Matemáticas</span>
      </div>
      <h3 style={{ marginTop: 20 }}>Objetivo educativo</h3>
      <p>{lesson.goal}</p>
      <h3>Consigna</h3>
      <p className="mw-subtle">{lesson.instructions}</p>
      {lesson.result ? (
        <>
          <div className="mw-evidence-grid">
            <div>
              <strong>{lesson.result.attempts}</strong>
              <span>Intentos registrados</span>
            </div>
            <div>
              <strong>{lesson.result.hints}</strong>
              <span>Pistas utilizadas</span>
            </div>
            <div>
              <strong style={{ fontSize: 17 }}>{timeSpent(lesson.result.elapsedSeconds)}</strong>
              <span>Tiempo aproximado</span>
            </div>
          </div>
          <h3>Evidencias de la práctica</h3>
          {!lesson.result.detailsShared && (
            <p className="mw-feedback">
              El detalle de respuestas es privado. Se muestran únicamente los totales autorizados de
              la actividad.
            </p>
          )}
          {lesson.result.clientReported && (
            <p className="mw-note">
              La finalización fue comunicada por el dispositivo. El servidor no ha comprobado las
              respuestas individuales.
            </p>
          )}
          <ol className="mw-answers">
            {lesson.result.answers.map((answer, index) => (
              <li key={index}>
                <span>
                  {answer.a} × {answer.b} = <strong>{answer.choice}</strong>
                </span>
                <Badge tone={answer.correct ? "success" : "info"}>
                  {answer.correct ? "Resuelto" : "Otro intento"}
                </Badge>
              </li>
            ))}
          </ol>
          <p className="mw-note">
            <ShieldCheck size={14} />
            Estos indicadores describen una práctica guiada. No son un diagnóstico ni una
            calificación oficial. No incluyen conversaciones privadas.
          </p>
        </>
      ) : (
        <p className="mw-feedback" style={{ marginTop: 20 }}>
          <Clock3 size={17} />
          La actividad está pendiente de realizarse o de sincronizar. No se interpreta como falta de
          participación.
        </p>
      )}
      {lesson.review && (
        <section className="mw-section">
          <h3>Observación del docente</h3>
          <p style={{ whiteSpace: "pre-wrap" }}>{lesson.review.observation}</p>
          <p className="mw-subtle">
            {lesson.review.authorName} · {date(lesson.review.reviewedAt)}
            {teacher && !lesson.review.publishedAt ? " · Borrador privado" : ""}
          </p>
        </section>
      )}
      {teacher && lesson.result && (
        <>
          <hr style={{ border: 0, borderTop: "1px solid var(--mw-line)", margin: "25px 0" }} />
          <form
            className="mw-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              if (
                await run({
                  action: "review-lesson",
                  assignmentId: lesson.id,
                  status: fields.get("status"),
                  observation: fields.get("observation"),
                  publish: fields.has("publish"),
                })
              )
                success("Revisión docente guardada.");
            }}
          >
            <Field label="Valoración de la práctica" full>
              <select name="status" defaultValue={lesson.review?.status ?? "reviewed"}>
                <option value="reviewed">Práctica revisada</option>
                <option value="needs_support">Conviene reforzar este concepto</option>
              </select>
            </Field>
            <Field label="Observación docente" full>
              <textarea
                name="observation"
                required
                maxLength={2000}
                defaultValue={lesson.review?.observation ?? ""}
                placeholder="Qué ha comprendido y qué conviene practicar a continuación."
              />
            </Field>
            <label className="mw-check mw-field full">
              <input type="checkbox" name="publish" defaultChecked={!!lesson.review?.publishedAt} />
              <span>
                Compartir la observación con su familia
                <small>
                  Si lo dejas desmarcado, se conserva como borrador privado del docente.
                </small>
                <small>
                  Una actividad completada con revisión compartida suma 10 puntos internos de
                  participación. No cambia la calificación.
                </small>
              </span>
            </label>
            <div className="mw-form-actions">
              <button className="mw-button primary" disabled={busy}>
                {busy ? "Guardando…" : "Guardar revisión"}
              </button>
              <button type="button" className="mw-button" onClick={onGrade}>
                Añadir nota manual
              </button>
            </div>
          </form>
        </>
      )}
    </>
  );
}

function Grades({
  data,
  pupilIds,
  open,
}: {
  data: SchoolSnapshot;
  pupilIds: Set<string>;
  open: (drawer: Drawer) => void;
}) {
  const grades = data.grades.filter((grade) => pupilIds.has(grade.learnerId));
  return (
    <Panel
      title="Registro de calificaciones"
      description="Cada nota tiene autor y fecha. Los resultados de práctica de Mochi están separados."
    >
      {grades.length ? (
        <div className="mw-table-wrap">
          <table className="mw-table">
            <thead>
              <tr>
                <th>Evaluación</th>
                <th>Estudiante</th>
                <th>Calificación</th>
                <th>Publicación</th>
                {data.role === "teacher" && (
                  <th>
                    <span className="sr-only">Editar</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {grades.map((grade) => (
                <tr key={grade.id}>
                  <td>
                    <strong>{grade.title}</strong>
                    <small>
                      {grade.subject} · {grade.authorName}
                    </small>
                    {grade.feedback && (
                      <p className="mw-subtle" style={{ margin: "7px 0 0", maxWidth: 300 }}>
                        {grade.feedback}
                      </p>
                    )}
                  </td>
                  <td>{pupilName(data, grade.learnerId)}</td>
                  <td>
                    <strong className="mw-grade-value">
                      {grade.value.toLocaleString("es")}
                      <small style={{ display: "inline" }}> / 10</small>
                    </strong>
                  </td>
                  <td>
                    {grade.publishedAt ? (
                      <>
                        <Badge tone="success">Publicada</Badge>
                        <small>{date(grade.publishedAt)}</small>
                      </>
                    ) : (
                      <Badge tone="outline">Borrador privado</Badge>
                    )}
                  </td>
                  {data.role === "teacher" && (
                    <td>
                      <button
                        className="mw-button small"
                        onClick={() => open({ kind: "grade", grade })}
                      >
                        Editar
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty icon={GraduationCap} title="Sin calificaciones publicadas">
          {data.role === "teacher"
            ? "Introduce una nota y publícala cuando esté preparada. Mochi nunca la calcula automáticamente."
            : "Aquí aparecerán las notas que publique el docente de su centro."}
        </Empty>
      )}
    </Panel>
  );
}
function GradeForm({
  data,
  grade,
  lesson,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  grade?: SchoolGrade | undefined;
  lesson?: SchoolLesson | undefined;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  if (!data.learners.length)
    return (
      <Empty icon={Users} title="Primero añade un alumno">
        Las calificaciones se registran por estudiante.
      </Empty>
    );
  return (
    <form
      className="mw-form"
      onSubmit={async (event) => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        const learnerId = String(fields.get("learnerId"));
        const payload = {
          action: "save-grade",
          ...(grade ? { gradeId: grade.id, expectedRevision: grade.revision } : {}),
          learnerId,
          assignmentId: grade?.assignmentId ?? lesson?.id ?? null,
          subject: fields.get("subject"),
          title: fields.get("title"),
          value: Number(fields.get("value")),
          feedback: fields.get("feedback"),
          publish: fields.has("publish"),
        };
        if (await run(payload))
          success(
            fields.has("publish")
              ? "Calificación publicada para su familia."
              : "Borrador de calificación guardado.",
          );
      }}
    >
      <Field label="Estudiante">
        <select
          name="learnerId"
          defaultValue={grade?.learnerId ?? lesson?.learnerId ?? data.learners[0]?.id}
          disabled={!!grade || !!lesson}
        >
          {data.learners.map((pupil) => (
            <option value={pupil.id} key={pupil.id}>
              {pupil.name}
            </option>
          ))}
        </select>
        {(grade || lesson) && (
          <input type="hidden" name="learnerId" value={grade?.learnerId ?? lesson?.learnerId} />
        )}
      </Field>
      <Field label="Asignatura">
        <input
          name="subject"
          required
          minLength={2}
          maxLength={80}
          defaultValue={grade?.subject ?? "Matemáticas"}
        />
      </Field>
      <Field label="Evaluación" full>
        <input
          name="title"
          required
          minLength={3}
          maxLength={120}
          defaultValue={grade?.title ?? lesson?.title ?? ""}
          placeholder="Nombre de la evaluación"
        />
      </Field>
      <Field label="Calificación (0 a 10)">
        <input
          type="number"
          name="value"
          min={0}
          max={10}
          step={0.1}
          required
          defaultValue={grade?.value}
          placeholder="Introduce la nota"
        />
      </Field>
      <Field label="Observación para la familia" full>
        <textarea name="feedback" maxLength={2000} defaultValue={grade?.feedback ?? ""} />
      </Field>
      <label className="mw-check mw-field full">
        <input type="checkbox" name="publish" defaultChecked={!!grade?.publishedAt} />
        <span>
          Publicar para la familia
          <small>Si no lo marcas, la nota sigue siendo un borrador privado.</small>
        </span>
      </label>
      <div className="mw-form-actions">
        <button className="mw-button primary" disabled={busy}>
          Guardar calificación
        </button>
        {grade?.publishedAt && (
          <button
            type="button"
            className="mw-button danger"
            disabled={busy}
            onClick={async () => {
              if (await run({ action: "withdraw-grade", gradeId: grade.id }))
                success("Se ha retirado la publicación de la nota.");
            }}
          >
            Retirar publicación
          </button>
        )}
      </div>
      <p className="mw-note">
        <ShieldCheck size={14} />
        La valoración oficial corresponde al docente. No se propone una nota a partir de las pistas
        o intentos.
      </p>
    </form>
  );
}

function Messages({
  data,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
  open: (drawer: Drawer) => void;
}) {
  const [filter, setFilter] = useState("all");
  const messages = data.messages.filter(
    (message) => !message.withdrawnAt && (filter !== "unread" || !message.readAt),
  );
  return (
    <Panel
      title={data.role === "teacher" ? "Comunicados del aula" : "Tu buzón escolar"}
      description="La conversación se limita a los adultos autorizados de cada estudiante."
    >
      {data.role === "family" && (
        <div className="mw-toolbar">
          <label className="mw-filter">
            <span className="sr-only">Filtrar mensajes</span>
            <select value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="all">Todos los mensajes</option>
              <option value="unread">Sin leer</option>
            </select>
          </label>
        </div>
      )}
      {messages.length ? (
        messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            data={data}
            run={run}
            busy={busy}
            success={success}
          />
        ))
      ) : (
        <Empty
          icon={Inbox}
          title={filter === "unread" ? "No tienes mensajes pendientes" : "El buzón está tranquilo"}
        >
          {data.role === "teacher"
            ? "Envía un comunicado a las familias de tu clase o a estudiantes concretos."
            : "Los mensajes que envíe el centro quedarán guardados aquí."}
        </Empty>
      )}
    </Panel>
  );
}
function Message({
  message,
  data,
  run,
  busy,
  success,
}: {
  message: SchoolMessage;
  data: SchoolSnapshot;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  return (
    <article className="mw-message">
      <div className="mw-list-row">
        <div>
          <h3>{message.title}</h3>
          <div className="mw-message-meta">
            <span>{message.authorName}</span>
            <span>{fullDate(message.createdAt)}</span>
            {data.role === "family" && !message.readAt && <Badge tone="warning">Sin leer</Badge>}
          </div>
        </div>
        {data.role === "teacher" && (
          <Badge tone="outline">
            {message.readCount} {message.readCount === 1 ? "lectura" : "lecturas"}
          </Badge>
        )}
      </div>
      <p className="mw-message-body">{message.body}</p>
      {message.replies.map((reply) => (
        <div className="mw-reply" key={reply.id}>
          <strong style={{ fontSize: 12 }}>{reply.authorName}</strong>
          <small> · {date(reply.createdAt)}</small>
          <p>{reply.body}</p>
        </div>
      ))}
      {data.role === "family" && !message.readAt && (
        <button
          className="mw-button small"
          disabled={busy}
          onClick={async () => {
            if (await run({ action: "mark-message-read", messageId: message.id }))
              success("Comunicado marcado como leído.");
          }}
        >
          <CheckCheck size={14} />
          Marcar como leído
        </button>
      )}
      {data.role === "family" && message.allowReplies && (
        <details className="mw-inline-details">
          <summary>Responder al centro</summary>
          <form
            className="mw-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const fields = new FormData(form);
              if (
                await run({
                  action: "reply-message",
                  messageId: message.id,
                  learnerId: fields.get("learnerId"),
                  body: fields.get("body"),
                })
              ) {
                form.reset();
                success("Respuesta enviada al docente.");
              }
            }}
          >
            <Field label="Sobre qué estudiante">
              <select name="learnerId">
                {message.learnerIds.map((id) => (
                  <option value={id} key={id}>
                    {pupilName(data, id)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tu respuesta" full>
              <textarea
                name="body"
                required
                maxLength={3000}
                placeholder="Escribe una respuesta para el centro."
              />
            </Field>
            <div className="mw-form-actions">
              <button className="mw-button primary" disabled={busy}>
                Enviar respuesta
              </button>
            </div>
          </form>
        </details>
      )}
      {data.role === "family" && !message.allowReplies && (
        <p className="mw-note">El centro ha enviado este comunicado sin respuestas habilitadas.</p>
      )}
      {data.role === "teacher" && (
        <details className="mw-inline-details">
          <summary>Gestionar comunicado</summary>
          <button
            className="mw-button small danger"
            disabled={busy}
            onClick={async () => {
              if (
                window.confirm("¿Retirar este comunicado de los buzones familiares?") &&
                (await run({ action: "withdraw-message", messageId: message.id }))
              )
                success("Comunicado retirado.");
            }}
          >
            Retirar comunicado
          </button>
        </details>
      )}
    </article>
  );
}
function MessageForm({
  data,
  classId,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  classId: string;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  if (!data.learners.length)
    return (
      <Empty icon={Users} title="Añade a los destinatarios">
        Primero incorpora alumnos a una clase para comunicarte con sus familias.
      </Empty>
    );
  return (
    <form
      className="mw-form"
      onSubmit={async (event) => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        if (
          await run({
            action: "send-message",
            ...recipientPayload(fields),
            title: fields.get("title"),
            body: fields.get("body"),
            allowReplies: fields.has("allowReplies"),
          })
        )
          success("Comunicado enviado a las familias autorizadas.");
      }}
    >
      <Recipients data={data} classId={classId} />
      <Field label="Asunto" full>
        <input name="title" required minLength={3} maxLength={160} />
      </Field>
      <Field label="Mensaje" full>
        <textarea name="body" required maxLength={6000} style={{ minHeight: 170 }} />
      </Field>
      <label className="mw-check mw-field full">
        <input type="checkbox" name="allowReplies" defaultChecked />
        <span>Permitir respuestas de las familias</span>
      </label>
      <div className="mw-form-actions">
        <button className="mw-button primary" disabled={busy}>
          {busy ? "Enviando…" : "Enviar comunicado"}
        </button>
      </div>
    </form>
  );
}

type AgendaItem = {
  id: string;
  at: string;
  title: string;
  description: string;
  kind: string;
  lesson?: SchoolLesson;
  event?: SchoolEvent;
};
function Calendar({
  data,
  lessons,
  pupilIds,
  open,
}: {
  data: SchoolSnapshot;
  lessons: SchoolLesson[];
  pupilIds: Set<string>;
  open: (drawer: Drawer) => void;
}) {
  const [month, setMonth] = useState(
    () => new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const [day, setDay] = useState("");
  const items: AgendaItem[] = [
    ...lessons.map((lesson) => ({
      id: lesson.id,
      at: lesson.dueAt,
      title: lesson.title,
      description: lesson.learnerName,
      kind: "Entrega",
      lesson,
    })),
    ...data.events
      .filter((event) => !event.cancelledAt && event.learnerIds.some((id) => pupilIds.has(id)))
      .map((event) => ({
        id: event.id,
        at: event.startsAt,
        title: event.title,
        description: event.description,
        kind:
          event.kind === "meeting"
            ? "Reunión"
            : event.kind === "exam"
              ? "Examen"
              : event.kind === "outing"
                ? "Excursión"
                : "Centro",
        event,
      })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  const prefix = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}`;
  const visible = items.filter((item) => item.at.startsWith(day || prefix));
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const offset = (month.getDay() + 6) % 7;
  return (
    <div className="mw-two-column">
      <Panel
        title={date(month.toISOString(), { month: "long", year: "numeric" })}
        action={
          <div style={{ display: "flex" }}>
            <button
              className="mw-icon-button"
              aria-label="Mes anterior"
              onClick={() => {
                setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1));
                setDay("");
              }}
            >
              <ChevronLeft size={18} />
            </button>
            <button
              className="mw-icon-button"
              aria-label="Mes siguiente"
              onClick={() => {
                setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1));
                setDay("");
              }}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        }
      >
        <div
          className="mw-month-grid"
          style={{ display: "grid", gridTemplateColumns: "repeat(7,minmax(0,1fr))", gap: 4 }}
        >
          {["L", "M", "X", "J", "V", "S", "D"].map((label, index) => (
            <span
              key={`week-${index}`}
              className="mw-subtle"
              style={{ textAlign: "center", padding: "9px 0" }}
            >
              {label}
            </span>
          ))}
          {Array.from({ length: offset }, (_, index) => (
            <span key={`empty-${index}`} />
          ))}
          {Array.from({ length: days }, (_, index) => {
            const key = `${prefix}-${String(index + 1).padStart(2, "0")}`;
            const count = items.filter((item) => item.at.startsWith(key)).length;
            return (
              <button
                key={key}
                className="mw-calendar-day"
                aria-label={`${index + 1} ${date(month.toISOString(), { month: "long" })}, ${count} compromisos`}
                aria-pressed={day === key}
                onClick={() => setDay(day === key ? "" : key)}
              >
                {index + 1}
                {count > 0 && (
                  <span
                    className="mw-dot"
                    style={{ background: "var(--mw-accent)", marginTop: 3 }}
                  />
                )}
              </button>
            );
          })}
        </div>
        <button
          className="mw-text-button"
          style={{ marginTop: 18 }}
          onClick={() => {
            setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
            setDay("");
          }}
        >
          Ir al mes actual
        </button>
      </Panel>
      <Panel
        title={day ? fullDate(day) : "Agenda del mes"}
        description="Las entregas se añaden automáticamente desde las actividades."
      >
        {visible.length ? (
          visible.map((item) => (
            <div className="mw-calendar-group" key={item.id}>
              <div className="mw-calendar-event">
                <time dateTime={item.at}>
                  {date(item.at, { day: "numeric", month: "short" })}
                  {item.at.length > 10 && (
                    <span style={{ display: "block", marginTop: 3 }}>
                      {date(item.at, { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                </time>
                <div>
                  <h3>{item.title}</h3>
                  {item.description && <p>{item.description}</p>}
                  {(item.lesson || data.role === "teacher") && (
                    <button
                      className="mw-text-button"
                      onClick={() =>
                        item.lesson
                          ? open({ kind: "assignment", lesson: item.lesson })
                          : open({ kind: "event", event: item.event })
                      }
                    >
                      {item.lesson ? "Consultar actividad" : "Editar evento"}
                    </button>
                  )}
                </div>
                <Badge>{item.kind}</Badge>
              </div>
            </div>
          ))
        ) : (
          <Empty icon={CalendarDays} title="Un espacio libre en la agenda">
            No hay compromisos para {day ? "este día" : "este mes"}.
          </Empty>
        )}
      </Panel>
    </div>
  );
}
function EventForm({
  data,
  event,
  classId,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  event?: SchoolEvent | undefined;
  classId: string;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  const local = (value: string) => {
    const at = new Date(value);
    return new Date(at.getTime() - at.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  };
  return (
    <form
      className="mw-form"
      onSubmit={async (formEvent) => {
        formEvent.preventDefault();
        const fields = new FormData(formEvent.currentTarget);
        const start = String(fields.get("startsAt")),
          end = String(fields.get("endsAt"));
        const payload = {
          action: "save-event",
          ...(event ? { eventId: event.id } : {}),
          ...recipientPayload(fields),
          title: fields.get("title"),
          description: fields.get("description"),
          kind: fields.get("kind"),
          startsAt: new Date(start).toISOString(),
          endsAt: end ? new Date(end).toISOString() : null,
        };
        if (await run(payload)) success("Evento guardado en el calendario de sus familias.");
      }}
    >
      <Recipients
        data={data}
        classId={event?.classId ?? classId}
        defaultIds={event?.classId ? [] : (event?.learnerIds ?? [])}
      />
      <Field label="Título" full>
        <input name="title" required minLength={3} maxLength={160} defaultValue={event?.title} />
      </Field>
      <Field label="Tipo de evento">
        <select name="kind" defaultValue={event?.kind ?? "meeting"}>
          <option value="meeting">Reunión o tutoría</option>
          <option value="exam">Examen</option>
          <option value="outing">Excursión</option>
          <option value="school">Actividad del centro</option>
        </select>
      </Field>
      <Field label="Inicio">
        <input
          type="datetime-local"
          name="startsAt"
          required
          defaultValue={event ? local(event.startsAt) : undefined}
        />
      </Field>
      <Field label="Fin (opcional)">
        <input
          type="datetime-local"
          name="endsAt"
          defaultValue={event?.endsAt ? local(event.endsAt) : undefined}
        />
      </Field>
      <Field label="Información para las familias" full>
        <textarea name="description" maxLength={3000} defaultValue={event?.description} />
      </Field>
      <p className="mw-subtle mw-field full">
        Las horas se introducen en la zona horaria de este navegador y se guardan con su instante
        exacto.
      </p>
      <div className="mw-form-actions">
        <button className="mw-button primary" disabled={busy}>
          Guardar evento
        </button>
        {event && (
          <button
            type="button"
            className="mw-button danger"
            disabled={busy}
            onClick={async () => {
              if (await run({ action: "delete-event", eventId: event.id }))
                success("Evento cancelado.");
            }}
          >
            Cancelar evento
          </button>
        )}
      </div>
    </form>
  );
}

function Devices({
  data,
  pupils,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  pupils: Pupil[];
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  const ids = new Set(pupils.map((pupil) => pupil.id));
  const devices = data.devices.filter(
    (device) => !device.revoked && device.learnerId && ids.has(device.learnerId),
  );
  return (
    <>
      <Panel
        title="Dispositivos vinculados"
        description="La última conexión es una sincronización comprobada, no una señal de presencia continua."
      >
        {devices.length ? (
          devices.map((device) => (
            <div className="mw-device-row" key={device.id}>
              <div className="mw-device-identity">
                <span className="mw-device-icon">
                  <Monitor size={20} strokeWidth={1.5} />
                </span>
                <div>
                  <h3>Mochi de {pupilName(data, device.learnerId!)}</h3>
                  <p>
                    {device.lastSeenAt
                      ? `Última sincronización: ${date(device.lastSeenAt, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
                      : "Esperando la primera sincronización"}
                  </p>
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Badge
                  tone={
                    device.lastSeenAt && Date.now() - new Date(device.lastSeenAt).getTime() < 90000
                      ? "success"
                      : "outline"
                  }
                >
                  {device.lastSeenAt && Date.now() - new Date(device.lastSeenAt).getTime() < 90000
                    ? "Conexión reciente"
                    : "Sin conexión reciente"}
                </Badge>
                {data.role === "teacher" && (
                  <button
                    className="mw-button small danger"
                    disabled={busy}
                    onClick={async () => {
                      if (
                        window.confirm(
                          "¿Retirar el acceso educativo de este dispositivo? Se aplicará al volver a conectar.",
                        ) &&
                        (await run(
                          { action: "revoke-device", deviceId: device.id },
                          "/api/education/",
                        ))
                      )
                        success("Acceso del dispositivo retirado.");
                    }}
                  >
                    Retirar acceso
                  </button>
                )}
              </div>
            </div>
          ))
        ) : (
          <Empty icon={Monitor} title="Todavía no hay un Mochi vinculado">
            {data.role === "teacher"
              ? "Abre el modo educativo en la placa y confirma el código para asociarla a un alumno."
              : "El centro debe vincular el dispositivo a su perfil educativo."}
          </Empty>
        )}
        <p className="mw-note">
          <Wifi size={14} />
          La práctica descargada puede continuar sin conexión. Los cambios y los resultados se
          aplican al sincronizar.
        </p>
      </Panel>
      {data.role === "teacher" && (
        <Panel
          title="Vincular un Mochi"
          description="El código aparece al abrir el modo educativo del dispositivo."
        >
          <form
            className="mw-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const fields = new FormData(form);
              if (
                await run(
                  {
                    action: "approve-pair",
                    code: String(fields.get("code")).trim().toUpperCase(),
                    learnerId: fields.get("learnerId"),
                  },
                  "/api/education/",
                )
              ) {
                form.reset();
                success("Mochi vinculado. Recibirá las actividades de ese alumno al sincronizar.");
              }
            }}
          >
            <Field label="Código de la placa">
              <input
                name="code"
                required
                minLength={8}
                maxLength={8}
                autoComplete="off"
                placeholder="8 caracteres"
              />
            </Field>
            <Field label="Alumno">
              <select name="learnerId" required>
                {data.learners.map((pupil) => (
                  <option value={pupil.id} key={pupil.id}>
                    {pupil.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="mw-form-actions">
              <button className="mw-button primary" disabled={busy || !data.learners.length}>
                Confirmar vínculo
              </button>
            </div>
          </form>
        </Panel>
      )}
    </>
  );
}

function Settings({
  data,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  const [selected, setSelected] = useState(data.learners[0]?.id ?? "");
  const pupil = data.learners.find((item) => item.id === selected) ?? data.learners[0];
  if (!pupil)
    return (
      <Panel title="Uso del dispositivo">
        <Empty icon={Settings2} title="Primero vincula un estudiante">
          Los horarios, permisos e idioma se configuran de forma independiente para cada estudiante.
        </Empty>
      </Panel>
    );
  const settings = data.settings.find((item) => item.learnerId === pupil.id);
  return (
    <>
      <div className="mw-profile-list" aria-label="Perfil que se configura">
        {data.learners.map((item) => (
          <button
            key={item.id}
            aria-pressed={item.id === pupil.id}
            onClick={() => setSelected(item.id)}
          >
            {item.name}
          </button>
        ))}
      </div>
      <div className="mw-two-column">
        <Panel
          title={`El Mochi de ${pupil.name}`}
          description="Los cambios se guardan en el servidor y llegan a la placa cuando sincroniza."
        >
          {data.role === "family" ? (
            <SettingsForm
              key={`${pupil.id}-${settings?.revision ?? 0}`}
              pupil={pupil}
              settings={settings}
              run={run}
              busy={busy}
              success={success}
            />
          ) : (
            <>
              <dl className="mw-settings-summary">
                <div>
                  <dt>Tiempo diario</dt>
                  <dd>{settings?.dailyMinutes ?? 30} minutos</dd>
                </div>
                <div>
                  <dt>Horario de uso</dt>
                  <dd>
                    {settings?.startTime ?? "16:00"}–{settings?.endTime ?? "20:00"}
                  </dd>
                </div>
                <div>
                  <dt>Conversación por voz</dt>
                  <dd>{settings?.voiceEnabled === false ? "Desactivada" : "Permitida"}</dd>
                </div>
                <div>
                  <dt>Detalle de respuestas</dt>
                  <dd>
                    {settings?.sharePractice === false ? "Privado" : "Compartido con el centro"}
                  </dd>
                </div>
              </dl>
              <p className="mw-note">
                <ShieldCheck size={14} />
                La familia gestiona horarios, accesibilidad y privacidad. Puedes editar el perfil
                curricular desde Clases y alumnos.
              </p>
            </>
          )}
        </Panel>
        <Panel title="Privacidad y acompañamiento">
          <div className="mw-list-leading">
            <ShieldCheck size={22} />
            <div>
              <h3>Datos con un propósito</h3>
              <p className="mw-subtle">
                Los paneles muestran actividades, evidencias autorizadas y comunicaciones escolares.
                Las conversaciones privadas no forman parte de este resumen.
              </p>
            </div>
          </div>
          <div className="mw-section">
            <h3>La práctica continúa</h3>
            <p className="mw-subtle">
              Desactivar el uso de voz o el envío opcional de respuestas no impide realizar las
              actividades descargadas. Sin voz, se muestra la alternativa en texto.
            </p>
          </div>
          <div className="mw-section">
            <h3>Una relación sin presión</h3>
            <p className="mw-subtle">
              Descansar, equivocarse o faltar un día no perjudica a Mochi. No se publican
              clasificaciones entre estudiantes.
            </p>
          </div>
          <p className="mw-note">
            No compartas información sensible en el nombre o las consignas de una actividad.
          </p>
        </Panel>
      </div>
    </>
  );
}
function SettingsForm({
  pupil,
  settings,
  run,
  busy,
  success,
}: {
  pupil: Pupil;
  settings?: SchoolSettings | undefined;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  const [voice, setVoice] = useState(settings?.voiceEnabled ?? true);
  const [captions, setCaptions] = useState(settings?.captionsEnabled ?? false);
  const [textFirst, setTextFirst] = useState(settings?.textFirst ?? false);
  const [reminders, setReminders] = useState(settings?.reminderMinutes !== null);
  const zones = Array.from(
    new Set([
      settings?.timezone ?? "Europe/Madrid",
      "Europe/Madrid",
      "Atlantic/Canary",
      "America/Mexico_City",
      "America/Bogota",
      "America/Lima",
      "America/Argentina/Buenos_Aires",
      "UTC",
    ]),
  );
  return (
    <form
      className="mw-form"
      onSubmit={async (event) => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        if (
          await run({
            action: "save-settings",
            learnerId: pupil.id,
            expectedRevision: settings?.revision ?? 0,
            dailyMinutes: Number(fields.get("dailyMinutes")),
            startTime: fields.get("startTime"),
            endTime: fields.get("endTime"),
            timezone: fields.get("timezone"),
            language: fields.get("language"),
            voiceEnabled: voice,
            captionsEnabled: !voice || captions || textFirst,
            textFirst: !voice || textFirst,
            sharePractice: fields.has("sharePractice"),
            reminderMinutes: reminders ? Number(fields.get("reminderMinutes")) : null,
            familySupportAlertsEnabled: fields.has("familySupportAlertsEnabled"),
          })
        )
          success("Ajustes guardados. Se aplicarán en Mochi al sincronizar.");
      }}
    >
      <Field
        label="Tiempo diario máximo"
        help="Entre 5 y 120 minutos. Las pausas no penalizan el aprendizaje."
      >
        <input
          type="number"
          name="dailyMinutes"
          min={5}
          max={120}
          step={5}
          required
          defaultValue={settings?.dailyMinutes ?? 30}
        />
      </Field>
      <Field label="Idioma de voz" help="La interfaz del dispositivo sigue en español.">
        <select name="language" defaultValue={settings?.language ?? "es"}>
          <option value="es">Español</option>
          <option value="en">English</option>
          <option value="pt">Português</option>
        </select>
      </Field>
      <div className="mw-field full mw-reminder-settings">
        <label className="mw-check">
          <input
            type="checkbox"
            checked={reminders}
            onChange={(event) => setReminders(event.target.checked)}
          />
          Avisar para hacer una pausa
        </label>
        <Field label="Recordatorio de pausa cada (minutos)">
          <input
            type="number"
            name="reminderMinutes"
            min={5}
            max={60}
            step={1}
            required
            disabled={!reminders}
            defaultValue={settings?.reminderMinutes ?? 10}
          />
        </Field>
        <small>
          Entre 5 y 60 minutos de uso. El recordatorio no amplía el tiempo diario máximo.
        </small>
      </div>
      <Field label="Disponible desde">
        <input
          type="time"
          name="startTime"
          required
          defaultValue={settings?.startTime ?? "16:00"}
        />
      </Field>
      <Field label="Hasta">
        <input type="time" name="endTime" required defaultValue={settings?.endTime ?? "20:00"} />
      </Field>
      <Field label="Zona horaria" full>
        <select name="timezone" defaultValue={settings?.timezone ?? "Europe/Madrid"}>
          {zones.map((zone) => (
            <option key={zone}>{zone}</option>
          ))}
        </select>
      </Field>
      <div className="mw-setting-list mw-field full">
        <label className="mw-check">
          <input
            type="checkbox"
            name="familySupportAlertsEnabled"
            defaultChecked={settings?.familySupportAlertsEnabled ?? false}
          />
          <span>
            Recibir avisos privados de acompañamiento
            <small>
              Desactivado por defecto. Permite recibir una señal de posible dificultad entre
              compañeros cuando el menor confirme que quiere compartirla. Sin audio ni
              transcripciones en el aviso; sólo visible para sus familiares autorizados.
            </small>
          </span>
        </label>
        <label className="mw-check">
          <input
            type="checkbox"
            name="voiceEnabled"
            checked={voice}
            onChange={(event) => setVoice(event.target.checked)}
          />
          <span>
            Permitir conversación por voz
            <small>
              La voz requiere los servicios conectados y utiliza el proveedor configurado por el
              centro.
            </small>
          </span>
        </label>
        <label className="mw-check">
          <input
            type="checkbox"
            name="captionsEnabled"
            checked={!voice || captions || textFirst}
            disabled={!voice || textFirst}
            onChange={(event) => setCaptions(event.target.checked)}
          />
          <span>
            Mostrar texto de preguntas y respuestas
            <small>
              Una alternativa completa para seguir la actividad sin depender del sonido.
            </small>
          </span>
        </label>
        <label className="mw-check">
          <input
            type="checkbox"
            name="textFirst"
            checked={!voice || textFirst}
            disabled={!voice}
            onChange={(event) => setTextFirst(event.target.checked)}
          />
          <span>
            Priorizar texto
            <small>
              Presentar primero las instrucciones y respuestas escritas. No se guarda ningún
              diagnóstico.
            </small>
          </span>
        </label>
        <label className="mw-check">
          <input
            type="checkbox"
            name="sharePractice"
            defaultChecked={settings?.sharePractice ?? true}
          />
          <span>
            Compartir detalle de respuestas
            <small>
              Permitir que el centro consulte cada intento. La confirmación y los totales de
              actividad seguirán disponibles si lo desactivas.
            </small>
          </span>
        </label>
      </div>
      <div className="mw-form-actions">
        <button className="mw-button primary" disabled={busy}>
          {busy ? "Guardando…" : "Guardar ajustes"}
        </button>
      </div>
      {settings?.updatedAt && (
        <p className="mw-subtle mw-field full">Último cambio: {fullDate(settings.updatedAt)}</p>
      )}
    </form>
  );
}

function Materials({
  data,
  run,
  busy,
  success,
}: {
  data: SchoolSnapshot;
  run: Run;
  busy: boolean;
  success: (text: string) => void;
}) {
  const [classId, setClassId] = useState(data.classes[0]?.id ?? "");
  const [source, setSource] = useState<{ id: string; page: number | null; content: string }[]>([]);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const materials = data.materials.filter((material) => material.classId === classId);
  return (
    <>
      <Panel
        title="Biblioteca del aula"
        description="Sube materiales propios del centro y conserva las referencias de sus páginas."
      >
        <form
          className="mw-form"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const fields = new FormData(form);
            fields.set("classId", classId);
            const file = fields.get("file");
            if (!(file instanceof File) || file.size > 4 * 1024 * 1024) {
              setError("Selecciona un PDF digital o TXT de hasta 4 MB.");
              return;
            }
            setError("");
            setUploading(true);
            try {
              const session = (await supabase.auth.getSession()).data.session;
              if (!session) throw new Error("Inicia sesión con tu cuenta adulta.");
              const response = await fetch("/api/education/", {
                method: "POST",
                headers: { Authorization: `Bearer ${session.access_token}` },
                body: fields,
              });
              const result = await response.json();
              if (!response.ok) throw new Error(result.error ?? "No se pudo procesar el material.");
              form.reset();
              await run(
                { action: "document-source", documentId: result.documentId },
                "/api/education/",
              ).then((rows) => {
                if (rows) setSource(rows as unknown as typeof source);
              });
              success("Material procesado. Puedes consultar el texto y sus páginas.");
            } catch (reason) {
              setError(reason instanceof Error ? reason.message : "No se pudo subir el documento.");
            } finally {
              setUploading(false);
            }
          }}
        >
          <Field label="Clase">
            <select
              value={classId}
              onChange={(event) => {
                setClassId(event.target.value);
                setSource([]);
              }}
            >
              {data.classes.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Documento educativo" help="PDF digital o TXT, hasta 4 MB.">
            <input type="file" name="file" accept=".pdf,.txt" required />
          </Field>
          <div className="mw-form-actions">
            <button className="mw-button primary" disabled={busy || uploading || !classId}>
              <Upload size={15} />
              {uploading ? "Procesando material…" : "Subir material"}
            </button>
          </div>
          {error && (
            <p role="alert" className="mw-field full" style={{ color: "var(--mw-error)" }}>
              {error}
            </p>
          )}
        </form>
      </Panel>
      <Panel title="Materiales disponibles">
        {materials.length ? (
          <ul className="mw-list mw-file-list">
            {materials.map((material) => (
              <li key={material.id}>
                <div className="mw-list-leading">
                  <FileText size={18} />
                  <div>
                    <h3>{material.name}</h3>
                    <p className="mw-subtle">Añadido el {fullDate(material.createdAt)}</p>
                  </div>
                </div>
                <button
                  className="mw-button small"
                  disabled={busy}
                  onClick={async () => {
                    const result = await run<
                      { id: string; page: number | null; content: string }[]
                    >({ action: "document-source", documentId: material.id }, "/api/education/");
                    if (result) setSource(result);
                  }}
                >
                  Consultar texto
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty icon={FileText} title="Tu biblioteca empieza aquí">
            Los documentos de esta clase estarán disponibles para preparar las actividades.
          </Empty>
        )}
      </Panel>
      {source.length > 0 && (
        <section className="mw-panel mw-section">
          <h2>Texto del material</h2>
          <div className="mw-source-preview">
            {source.map((chunk) => (
              <section key={chunk.id}>
                <h3>{chunk.page ? `Página ${chunk.page}` : "Texto del documento"}</h3>
                <p>{chunk.content}</p>
              </section>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
