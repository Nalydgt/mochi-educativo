import { lazy, Suspense, useEffect, useRef, useState, type Ref } from "react";
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  BookOpen,
  Check,
  ClipboardList,
  ChevronRight,
  Compass,
  Flag,
  Lightbulb,
  Footprints,
  Map,
  MapPin,
  MessageCircle,
  Sparkles,
  Volume2,
  VolumeX,
} from "lucide-react";
import type { MascotMood } from "@/components/Stickers";
import {
  activityLabels,
  colors,
  defaultWorld,
  isAssessment,
  supportsCards,
  subjects,
  worldThemes,
  type Companion,
  type Phase,
  type PublicActivity,
  type StudyFormat,
  type World,
} from "@/lib/education/schema";
import type { StudyRecommendation, SuggestedActivity } from "@/lib/education/study";
import {
  defaultLearnerPreferences,
  type LearnerPreferences,
} from "@/lib/education/personalization";
import { useStudyTelemetry } from "@/hooks/use-study-telemetry";
import { useStudySound } from "@/hooks/use-study-sound";
import { ActivityGame, Animal } from "./ActivityGame";
import { FieldGuide } from "./FieldGuide";
import { LearnerPersonalization, WebStudyGuide } from "./LearnerPersonalization";
import { artUrl, landmarkArt } from "./fieldArt";
import { CuriosityRoom, WorldLibrary, type CuriosityTurn, type WorldListing } from "./WorldSpaces";
import "./student.css";
import "./worlds.css";
import "./field.css";

const FieldScene = lazy(() => import("./FieldScene"));
type ExpeditionView = "map" | "list";
type LearnerReply<Command> = Command extends { action: "answer" }
  ? { correct: boolean | null; challenge: boolean; explanation: string | null }
  : Command extends { action: "hint" }
    ? { hint: string }
    : Command extends { action: "tutor" }
      ? { text: string }
      : Record<string, unknown>;

type Progress = { discoveries: number; completed: number };
type Turn = {
  id: string;
  question: string;
  text: string;
  sources: { name: string; page: number | null }[];
};
type Learning = {
  id: string;
  version_id: string;
  title: string;
  subject?: keyof typeof subjects | null;
  intro: string;
  phase: Phase;
  activities: PublicActivity[];
  attempts: { activity_id: string; phase: Phase; correct: boolean | null }[];
  turns: Turn[];
  completed_at: string | null;
  retention_completed_at: string | null;
  world: World | null;
  studyRecommendations?: Record<string, StudyRecommendation>;
  recommendations?: SuggestedActivity[];
};
export type LearnerData = {
  learner: {
    id: string;
    name: string;
    companion: Companion;
    support: boolean;
    web_preferences?: LearnerPreferences;
  };
  progress: Progress & { unaided?: number };
  learning: Learning | null;
  versions: WorldListing[];
  worldsInProgress: { versionId: string; phase: Phase }[];
  curiosity: CuriosityTurn[];
  recommendedWorld?: { versionId: string; reason: string } | null;
  devices: { id: string; session_id: string | null; last_seen_at: string | null }[];
};

const route = [
  { phase: "diagnostic", title: "Punto de partida", icon: Flag },
  { phase: "practice", title: "Exploración", icon: Compass },
  { phase: "final", title: "Reto final", icon: Sparkles },
  { phase: "completed", title: "Cuaderno", icon: BookOpen },
] as const;
const stageTitles = {
  diagnostic: "¿Qué sabes ya?",
  final: "Pon a prueba tus descubrimientos",
  retention: "¿Qué recuerdas de la expedición?",
};
const stationActions = activityLabels;
const formatReasons: Record<StudyRecommendation["reason"], string> = {
  start: "Puedes probar el juego principal y cambiar de formato cuando quieras.",
  guided: "Tu adulto ha activado la práctica paso a paso.",
  retry: "Tras dos intentos sin resolver, prueba a mirar el reto de otra forma.",
  unassisted: "Ya has resuelto varios retos de este tipo sin pistas.",
};
const palette = { sunburst: "Sol", mint: "Menta", lavender: "Lavanda", ember: "Coral" };
const day = 86_400_000;

function ExpeditionMap({
  mission,
  world,
  solved,
  busy,
  onVisit,
  headingRef,
}: {
  mission: Learning;
  world: World;
  solved: Set<string>;
  busy: boolean;
  onVisit: (activity: PublicActivity) => void;
  headingRef: Ref<HTMLHeadingElement>;
}) {
  return (
    <section
      className="expedition-map"
      data-layout={world.stations.length === 3 ? "atlas" : "grid"}
      data-theme={world.theme}
      aria-label="Mapa de la expedición"
    >
      <div className="expedition-map-heading">
        <div>
          <h2 ref={headingRef} tabIndex={-1}>
            {world.theme === "reserve"
              ? "El mapa de la reserva"
              : `Mapa del ${world.theme === "space" ? "observatorio" : "taller"}`}
          </h2>
          <p>Elige un lugar para explorar.</p>
        </div>
        <Compass className="expedition-compass" size={34} aria-hidden="true" />
      </div>
      <svg
        className="expedition-trail"
        viewBox="0 0 800 300"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path d="M136 206C234 242 278 88 400 107S561 221 666 179" fill="none" />
      </svg>
      <ol className="expedition-stations">
        {world.stations.map((station, index) => {
          const activity = mission.activities.find((item) => item.id === station.activityId);
          if (!activity) return null;
          const done = solved.has(activity.id);
          return (
            <li key={activity.id} data-station={activity.type}>
              <button type="button" disabled={busy} onClick={() => onVisit(activity)}>
                <span className="expedition-pin" data-done={done}>
                  <img src={artUrl(landmarkArt[activity.type])} alt="" />
                  <span className="expedition-stamp" aria-hidden="true">
                    {done ? <Check size={16} /> : index + 1}
                  </span>
                </span>
                <span className="expedition-station-label">
                  <strong>{station.title}</strong>
                  <small>{done ? "Descubierto" : stationActions[activity.type]}</small>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <span className="expedition-map-caption">
        <MapPin size={15} aria-hidden="true" /> {worldThemes[world.theme]}
      </span>
    </section>
  );
}

function CompanionEditor({
  pet,
  progress,
  busy,
  onSave,
  onBack,
}: {
  pet: Companion;
  progress: Progress;
  busy: boolean;
  onSave: (value: Companion) => Promise<boolean>;
  onBack: () => void;
}) {
  const [draft, setDraft] = useState(pet);
  const [saved, setSaved] = useState(false);
  const outfits = [
    { id: "none", title: "Al natural", ready: true, clue: "Disponible" },
    { id: "scarf", title: "Pañuelo", ready: progress.discoveries >= 3, clue: "3 descubrimientos" },
    {
      id: "star",
      title: "Estrella",
      ready: progress.completed > 0,
      clue: "Una expedición completa",
    },
  ] as const;
  function edit(change: Partial<Companion>) {
    setSaved(false);
    setDraft((current) => ({ ...current, ...change }));
  }
  return (
    <section className="expedition-wardrobe">
      <div className="expedition-wardrobe-stage" data-color={draft.color}>
        <span className="expedition-wardrobe-label">
          <Sparkles size={18} aria-hidden="true" /> Mi Peluqo
        </span>
        <FieldGuide
          color={draft.color}
          accessory={draft.accessory}
          mood={saved ? "celebrate" : "idle"}
        />
        <h1>{draft.name || "Peluqo"}</h1>
        <p>{progress.completed ? "Compañero de exploración" : "Listo para descubrir contigo"}</p>
      </div>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (await onSave(draft)) setSaved(true);
        }}
      >
        <h2>Prepara a tu compañero</h2>
        <label>
          ¿Cómo se llama?
          <input
            value={draft.name}
            maxLength={32}
            required
            onChange={(event) => edit({ name: event.target.value })}
          />
        </label>
        <fieldset>
          <legend>Su color en la web</legend>
          <div className="expedition-swatches">
            {colors.map((color) => (
              <label key={color} data-color={color}>
                <input
                  type="radio"
                  name="color"
                  checked={draft.color === color}
                  onChange={() => edit({ color })}
                />
                <span>{palette[color]}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Accesorios del cuaderno</legend>
          <div className="expedition-outfits">
            {outfits.map((outfit) => (
              <label key={outfit.id} data-locked={!outfit.ready}>
                <input
                  type="radio"
                  name="accessory"
                  checked={draft.accessory === outfit.id}
                  disabled={!outfit.ready}
                  onChange={() => edit({ accessory: outfit.id })}
                />
                <span>
                  <strong>{outfit.title}</strong>
                  <small>{outfit.ready ? "Disponible" : outfit.clue}</small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <p className="edu-help">
          El nombre acompaña tu misión en la placa. Los colores y accesorios se ven aquí.
        </p>
        <div className="expedition-actions">
          <button className="edu-button primary" disabled={busy}>
            {busy ? "Guardando…" : "Guardar mi Peluqo"}
          </button>
          <button className="edu-button" type="button" onClick={onBack}>
            Volver a mi aventura
          </button>
        </div>
      </form>
    </section>
  );
}

export function StudentAdventure({
  data,
  tab,
  busy,
  run,
  notice,
  navigate,
}: {
  data: LearnerData;
  tab: string;
  busy: boolean;
  run: <const Command extends { action: string }>(
    command: Command,
  ) => Promise<LearnerReply<Command> | null>;
  notice: (message: string) => void;
  navigate: (id: string) => void;
}) {
  const { learner, learning, progress } = data;
  const pet = learner.companion;
  const preferences = learner.web_preferences ?? defaultLearnerPreferences;
  const suggestedWorld = data.versions.find(
    (version) => version.id === data.recommendedWorld?.versionId,
  );
  const [selection, setSelection] = useState("");
  const [viewChoice, setViewChoice] = useState<{ session: string; view: ExpeditionView }>();
  const [mood, setMood] = useState<MascotMood>("idle");
  const sound = useStudySound();
  const [stamp, setStamp] = useState<{ title: string; id: string }>();
  useEffect(() => {
    if (!stamp) return;
    const timer = window.setTimeout(() => setStamp(undefined), 3200);
    return () => window.clearTimeout(timer);
  }, [stamp]);
  const [result, setResult] = useState<{ tone: "success" | "retry"; text: string }>();
  const [help, setHelp] = useState("");
  const [studyChoice, setStudyChoice] = useState<{
    session: string;
    activity: string;
    format: StudyFormat;
  }>();
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const focus = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus.current && heading.current) {
      focus.current = false;
      heading.current.focus();
    }
  }, [selection, learning?.phase, tab]);

  const items = learning?.activities ?? [];
  const practice = learning?.phase === "practice";
  const world =
    learning?.world ??
    (practice ? defaultWorld(items, learning.title === "La expedición de los vertebrados") : null);
  const worldView = viewChoice && viewChoice.session === learning?.id ? viewChoice.view : "map";
  const completed = learning?.phase === "completed";
  const selected = items.find((item) => item.id === selection);
  const map = practice && !selected;
  const completedItems = new Set(
    learning?.attempts
      .filter((attempt) => attempt.phase === learning.phase && (!practice || attempt.correct))
      .map((attempt) => attempt.activity_id),
  );
  const discoveries = new Set(
    learning?.attempts
      .filter((attempt) => attempt.phase === "practice" && attempt.correct)
      .map((attempt) => attempt.activity_id),
  );
  const next = items.find((item) => !completedItems.has(item.id));
  const current = map ? undefined : (selected ?? next ?? items[0]);
  const currentDone = current ? completedItems.has(current.id) : false;
  const hasFormats = !!(practice && current && supportsCards(current));
  const recommended =
    hasFormats && current ? learning?.studyRecommendations?.[current.id] : undefined;
  const format =
    hasFormats &&
    current &&
    studyChoice?.session === learning?.id &&
    studyChoice?.activity === current.id
      ? studyChoice.format
      : (recommended?.format ?? "board");
  const allDone = items.length > 0 && completedItems.size === items.length;
  const phaseIndex = route.findIndex((step) => step.phase === learning?.phase);
  const connected = data.devices.some(
    (device) =>
      device.session_id === learning?.id &&
      device.last_seen_at &&
      Date.now() - Date.parse(device.last_seen_at) < 15_000,
  );
  const retentionDate = learning?.completed_at ? Date.parse(learning.completed_at) + 7 * day : 0;
  useStudyTelemetry({
    surface: tab === "mundos" || tab === "preguntas" || tab === "peluqo" ? tab : "aventura",
    sessionId: tab === "aventura" ? (learning?.id ?? null) : null,
    activityId: tab === "aventura" ? (current?.id ?? null) : null,
    format: tab === "aventura" && current ? format : null,
  });

  function reset() {
    setResult(undefined);
    setHelp("");
    setMood("idle");
  }
  function visit(activity: PublicActivity) {
    if (!learning) return;
    reset();
    sound.play("select");
    focus.current = true;
    setSelection(activity.id);
    setStudyChoice({
      session: learning.id,
      activity: activity.id,
      format:
        practice && supportsCards(activity)
          ? (learning.studyRecommendations?.[activity.id]?.format ?? "board")
          : "board",
    });
    void run({ action: "focus", sessionId: learning.id, activityId: activity.id });
  }
  function backToMap() {
    reset();
    sound.play("move");
    focus.current = true;
    setSelection("");
  }
  async function advance() {
    if (!learning) return;
    if (await run({ action: "advance", sessionId: learning.id })) {
      backToMap();
      heading.current?.focus();
    }
  }
  async function openWorld(versionId: string) {
    if (await run({ action: "start", versionId })) {
      backToMap();
      navigate("aventura");
    }
  }

  if (tab === "mundos")
    return (
      <>
        {suggestedWorld && (
          <details className="expedition-recommended" aria-label="Recomendado para ti">
            <summary>
              <Sparkles size={20} aria-hidden="true" /> Recomendado para ti
            </summary>
            <p>{data.recommendedWorld?.reason}</p>
            <button
              type="button"
              className="edu-button primary"
              disabled={busy}
              onClick={() => void openWorld(suggestedWorld.id)}
            >
              {suggestedWorld.title} <ArrowRight size={18} aria-hidden="true" />
            </button>
          </details>
        )}
        <WorldLibrary
          pet={pet}
          worlds={data.versions}
          progress={data.worldsInProgress ?? []}
          lockedVersion={isAssessment(learning?.phase) ? learning?.version_id : undefined}
          busy={busy}
          onOpen={(id) => void openWorld(id)}
        />
      </>
    );
  if (tab === "preguntas")
    return (
      <CuriosityRoom
        pet={pet}
        turns={data.curiosity ?? []}
        locked={isAssessment(learning?.phase)}
        onBack={() => navigate("aventura")}
        onAsk={async (value) =>
          !!(await run({ action: "ask", question: value, requestId: crypto.randomUUID() }))
        }
      />
    );

  if (tab === "peluqo") {
    return (
      <>
        <CompanionEditor
          pet={pet}
          progress={progress}
          busy={busy}
          onBack={() => navigate("aventura")}
          onSave={async (value) => {
            const saved = await run({ action: "companion", companion: value });
            if (saved) notice("Tu Peluqo está listo para acompañarte.");
            return !!saved;
          }}
        />
        <LearnerPersonalization
          preferences={preferences}
          pet={pet}
          progress={progress}
          worlds={data.versions}
          history={data.worldsInProgress}
          busy={busy}
          onSave={async (value) => !!(await run({ action: "preferences", preferences: value }))}
        />
      </>
    );
  }

  return (
    <div
      className="student-expedition"
      data-exploring={map}
      data-world-theme={world?.theme ?? preferences.theme}
    >
      <header className="expedition-intro">
        <div>
          <p className="expedition-greeting">
            <Compass size={18} aria-hidden="true" /> Hola, {learner.name}
            {learning?.subject && (
              <span className="expedition-subject">{subjects[learning.subject]}</span>
            )}
          </p>
          <h1>{learning?.title ?? "Tu próxima expedición"}</h1>
          {learning && (
            <p>
              {learning.phase === "practice"
                ? "Recorre el sendero con tu compañero y completa el cuaderno."
                : learning.intro}
            </p>
          )}
        </div>
        {learning && (
          <div className="expedition-physical">
            <div className="expedition-connection" data-connected={connected}>
              <AudioLines size={16} aria-hidden="true" />
              {connected ? "Mochi conectado" : "Explorando en la web"}
            </div>
            {data.devices.length > 0 && (
              <details className="expedition-device">
                <summary>Mi Mochi físico</summary>
                <p>Elige esta aventura para que tu Mochi te acompañe.</p>
                {data.devices.map((device, index) => {
                  const active = device.session_id === learning.id;
                  return (
                    <button
                      className="edu-button"
                      type="button"
                      key={device.id}
                      disabled={busy}
                      onClick={async () => {
                        const saved = await run({
                          action: "bind-device",
                          deviceId: device.id,
                          sessionId: active ? null : learning.id,
                        });
                        if (saved)
                          notice(
                            active
                              ? "Mochi ha dejado de acompañar esta aventura."
                              : "Esta aventura ya está conectada con tu Mochi.",
                          );
                      }}
                    >
                      {active ? "Desconectar de esta aventura" : "Conectar Mochi a esta aventura"}
                      {data.devices.length > 1 && ` · ${index + 1}`}
                    </button>
                  );
                })}
              </details>
            )}
          </div>
        )}
      </header>
      <div className="expedition-play-tools">
        {sound.available && (
          <button
            type="button"
            className="expedition-sound"
            aria-pressed={sound.enabled}
            onClick={() => void sound.toggle()}
          >
            {sound.enabled ? (
              <Volume2 size={18} aria-hidden="true" />
            ) : (
              <VolumeX size={18} aria-hidden="true" />
            )}
            {sound.enabled ? "Sonido activado" : "Activar sonidos"}
          </button>
        )}
        {practice && (
          <span>
            <Compass size={17} aria-hidden="true" /> {discoveries.size} descubrimientos en tu
            pasaporte
          </span>
        )}
      </div>
      {stamp && (
        <div key={stamp.id} className="expedition-new-stamp" role="status">
          <span className="expedition-stamp-icon">
            <Sparkles size={24} aria-hidden="true" />
          </span>
          <div>
            <strong>¡Nuevo descubrimiento!</strong>
            <span>{stamp.title}</span>
          </div>
          <button
            type="button"
            aria-label="Cerrar descubrimiento"
            onClick={() => setStamp(undefined)}
          >
            ×
          </button>
        </div>
      )}

      {learning && (
        <details className="expedition-route-panel" open={!practice || undefined}>
          <summary>
            <Compass size={17} aria-hidden="true" /> Mi recorrido{" "}
            <span>
              {practice
                ? `${discoveries.size} de ${items.length} descubrimientos`
                : completed
                  ? "Aventura completada"
                  : "Vamos paso a paso"}
            </span>
          </summary>
          <ol className="expedition-route" aria-label="Etapas de la expedición">
            {route.map(({ phase, title, icon: Icon }, index) => (
              <li
                key={phase}
                aria-current={learning.phase === phase ? "step" : undefined}
                data-past={index < phaseIndex || learning.phase === "retention"}
              >
                <span>
                  {index < phaseIndex ? (
                    <Check size={18} aria-hidden="true" />
                  ) : (
                    <Icon size={18} aria-hidden="true" />
                  )}
                </span>
                <strong>{title}</strong>
              </li>
            ))}
          </ol>
        </details>
      )}

      {!learning ? (
        <section className="expedition-start">
          <div className="expedition-start-copy">
            <h2>Prepara tu cuaderno</h2>
            <p>
              {data.versions.length
                ? "Tu docente ha preparado una misión para ti. Puedes personalizar a tu Peluqo antes de empezar."
                : "Tu docente está preparando la primera misión del aula."}
            </p>
            {data.versions.map((version) => (
              <button
                type="button"
                key={version.id}
                className="edu-button primary"
                disabled={busy}
                onClick={() => void run({ action: "start", versionId: version.id })}
              >
                Empezar {version.title} <ArrowRight size={18} aria-hidden="true" />
              </button>
            ))}
            <button className="edu-button" onClick={() => navigate("peluqo")}>
              Personalizar mi Peluqo
            </button>
          </div>
          <WebStudyGuide
            guide={preferences.guide}
            color={pet.color}
            accessory={pet.accessory}
            mood="wow"
          />
        </section>
      ) : completed ? (
        <section className="expedition-finish">
          <WebStudyGuide
            guide={preferences.guide}
            color={pet.color}
            accessory={pet.accessory}
            mood="celebrate"
          />
          <div>
            <h2 ref={heading} tabIndex={-1}>
              ¡Expedición completada!
            </h2>
            <p>
              Tu cuaderno guarda {discoveries.size} descubrimientos. Ya puedes elegir tu estrella en
              Mi Peluqo.
            </p>
            <p>
              {learning.retention_completed_at
                ? "Tu repaso también está guardado."
                : `El repaso se abre el ${new Date(retentionDate).toLocaleDateString("es-ES", { day: "numeric", month: "long" })}.`}
            </p>
            <div className="expedition-actions">
              <button className="edu-button primary" onClick={() => navigate("peluqo")}>
                Ver mi Peluqo <Sparkles size={18} aria-hidden="true" />
              </button>
              {!learning.retention_completed_at &&
                retentionDate > 0 &&
                Date.now() >= retentionDate && (
                  <button className="edu-button" disabled={busy} onClick={() => void advance()}>
                    Comprobar lo que recuerdo
                  </button>
                )}
            </div>
          </div>
        </section>
      ) : (
        <div className="expedition-layout" data-map={map}>
          <div className="expedition-board">
            {map && world ? (
              <>
                {!!learning.recommendations?.length && (
                  <details className="expedition-recommended" aria-label="Recomendado para ti">
                    <summary>
                      <Sparkles size={20} aria-hidden="true" /> Tu siguiente descubrimiento
                    </summary>
                    <div className="expedition-suggestions">
                      {learning.recommendations.map((suggestion) => {
                        const item = items.find(
                          (activity) => activity.id === suggestion.activityId,
                        );
                        if (!item || discoveries.has(item.id)) return null;
                        return (
                          <div key={item.id}>
                            <p>{suggestion.reason}</p>
                            <button
                              type="button"
                              className="edu-button"
                              disabled={busy}
                              onClick={() => visit(item)}
                            >
                              {item.title} <ArrowRight size={17} aria-hidden="true" />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                )}
                <details className="expedition-passport">
                  <summary>
                    <BookOpen size={18} aria-hidden="true" /> Mi pasaporte{" "}
                    <span>
                      {discoveries.size} de {items.length} sellos
                    </span>
                  </summary>
                  <div>
                    {items.map((item, index) => (
                      <button
                        type="button"
                        key={item.id}
                        data-discovered={discoveries.has(item.id)}
                        disabled={busy}
                        onClick={() => visit(item)}
                        aria-label={`${item.title}. ${discoveries.has(item.id) ? "Descubrimiento conseguido" : "Explorar este reto"}`}
                      >
                        <Animal asset={item.asset} decorative />
                        <small>{index + 1}</small>
                        <strong>{item.title}</strong>
                        <span>{discoveries.has(item.id) ? "Conseguido" : "Explorar"}</span>
                      </button>
                    ))}
                  </div>
                </details>
                <div className="world-view-switch" role="group" aria-label="Vista de la expedición">
                  <button
                    type="button"
                    aria-pressed={worldView === "map"}
                    onClick={() => setViewChoice({ session: learning.id, view: "map" })}
                  >
                    <Footprints size={18} aria-hidden="true" /> Explorar 2D
                  </button>
                  <button
                    type="button"
                    aria-pressed={worldView === "list"}
                    onClick={() => setViewChoice({ session: learning.id, view: "list" })}
                  >
                    <Map size={18} aria-hidden="true" /> Mapa de paradas
                  </button>
                </div>
                {worldView === "map" ? (
                  <Suspense
                    fallback={
                      <p className="world-loading" role="status">
                        Abriendo el sendero…
                      </p>
                    }
                  >
                    <FieldScene
                      key={learning.id}
                      world={world}
                      activities={items}
                      pet={pet}
                      solved={discoveries}
                      busy={busy}
                      onVisit={visit}
                    />
                  </Suspense>
                ) : (
                  <ExpeditionMap
                    mission={learning}
                    world={world}
                    solved={discoveries}
                    busy={busy}
                    onVisit={visit}
                    headingRef={heading}
                  />
                )}
                <div className="expedition-map-footer">
                  <p>
                    <BookOpen size={20} aria-hidden="true" />{" "}
                    <strong>
                      {discoveries.size} de {items.length}
                    </strong>{" "}
                    descubrimientos
                  </p>
                  {allDone && (
                    <button
                      className="edu-button primary"
                      disabled={busy}
                      onClick={() => void advance()}
                    >
                      Ir al reto final <ArrowRight size={18} aria-hidden="true" />
                    </button>
                  )}
                </div>
              </>
            ) : (
              current && (
                <section className="expedition-workbench" aria-label="Actividad de la expedición">
                  <div className="expedition-workbench-top">
                    {practice ? (
                      <button className="expedition-back" onClick={backToMap}>
                        <ArrowLeft size={17} aria-hidden="true" /> Volver al mapa
                      </button>
                    ) : (
                      <span>{stageTitles[learning.phase as keyof typeof stageTitles]}</span>
                    )}
                    <span className="expedition-count">
                      {items.indexOf(current) + 1} de {items.length}
                    </span>
                  </div>
                  {practice &&
                    world?.stations.find((station) => station.activityId === current.id)
                      ?.observation && (
                      <p className="world-observation">
                        <Compass size={18} aria-hidden="true" />{" "}
                        {
                          world.stations.find((station) => station.activityId === current.id)
                            ?.observation
                        }
                      </p>
                    )}
                  {!currentDone && hasFormats && (
                    <div className="expedition-format">
                      <p>
                        <strong>Elige cómo practicar</strong>{" "}
                        <span>
                          {recommended ? formatReasons[recommended.reason] : formatReasons.start}
                        </span>
                      </p>
                      <div role="group" aria-label="Formato de práctica">
                        {(["board", "cards"] as const).map((choice) => (
                          <button
                            type="button"
                            key={choice}
                            aria-pressed={format === choice}
                            disabled={busy}
                            onClick={() => {
                              setStudyChoice({
                                session: learning.id,
                                activity: current.id,
                                format: choice,
                              });
                              setResult(undefined);
                            }}
                          >
                            {choice === "board"
                              ? current.type === "question"
                                ? "Pregunta directa"
                                : "Tablero"
                              : current.type === "question"
                                ? "Descartar opciones"
                                : "Una tarjeta a la vez"}
                            {recommended?.reason !== "start" && recommended?.format === choice && (
                              <small>Recomendado</small>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {currentDone ? (
                    <div className="expedition-done" data-practice={practice}>
                      {practice && <Animal asset={current.asset} decorative />}
                      <h2 ref={heading} tabIndex={-1}>
                        {current.title}
                      </h2>
                      <p>
                        {practice ? (
                          <Check size={20} aria-hidden="true" />
                        ) : (
                          <ClipboardList size={20} aria-hidden="true" />
                        )}{" "}
                        {practice ? "Descubrimiento anotado" : "Respuesta guardada"}
                      </p>
                    </div>
                  ) : (
                    <ActivityGame
                      key={current.id}
                      activity={current}
                      disabled={busy}
                      showIllustration={practice}
                      studyFormat={format}
                      onInteraction={(cue) => sound.play(cue)}
                      headingRef={heading}
                      retryFeedback={practice && result?.tone === "retry" ? result.text : undefined}
                      onEdit={() => setResult(undefined)}
                      onSubmit={async (answer) => {
                        setSelection(current.id);
                        const reply = await run({
                          action: "answer",
                          sessionId: learning.id,
                          activityId: current.id,
                          requestId: crypto.randomUUID(),
                          answer,
                          studyFormat: format,
                        });
                        if (!reply) return;
                        if (!practice || reply.correct)
                          requestAnimationFrame(() => heading.current?.focus());
                        if (!practice) return;
                        sound.play(reply.correct ? "success" : "retry");
                        setMood(reply.correct ? "celebrate" : "encourage");
                        if (reply.correct)
                          setStamp({ title: current.title, id: crypto.randomUUID() });
                        const stretch =
                          reply.challenge && !learner.support
                            ? " Reto extra. Piensa en otro animal al que puedas aplicar lo que descubriste."
                            : "";
                        setResult({
                          tone: reply.correct ? "success" : "retry",
                          text: reply.explanation + stretch,
                        });
                      }}
                    />
                  )}
                  <div className="expedition-result" role="status">
                    {result?.tone === "success" && result.text}
                  </div>
                  {currentDone && (
                    <div className="expedition-actions">
                      {practice ? (
                        <button className="edu-button primary" onClick={backToMap}>
                          Seguir explorando <ChevronRight size={18} aria-hidden="true" />
                        </button>
                      ) : (
                        next && (
                          <button
                            className="edu-button primary"
                            disabled={busy}
                            onClick={() => visit(next)}
                          >
                            Siguiente pregunta <ChevronRight size={18} aria-hidden="true" />
                          </button>
                        )
                      )}
                      {allDone && (
                        <button
                          className={`edu-button${practice ? "" : " primary"}`}
                          disabled={busy}
                          onClick={() => void advance()}
                        >
                          {learning.phase === "diagnostic"
                            ? "Abrir el mapa"
                            : practice
                              ? "Ir al reto final"
                              : "Terminar y ver mi cuaderno"}
                          <ArrowRight size={18} aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  )}
                </section>
              )
            )}
          </div>

          <aside className="expedition-buddy" aria-label="Tu compañero de expedición">
            <div className="expedition-buddy-stage" data-mood={mood}>
              <WebStudyGuide
                guide={preferences.guide}
                mood={mood}
                color={pet.color}
                accessory={pet.accessory}
              />
              <span className="expedition-buddy-name">
                {preferences.guide === "peluqo"
                  ? pet.name
                  : preferences.guide === "frog"
                    ? "Rana de la reserva"
                    : "Pez del río"}
              </span>
            </div>
            <div className="expedition-buddy-body">
              <h2>{map ? "¿Adónde vamos?" : practice ? "Vamos juntos" : "A tu ritmo"}</h2>
              <p>
                {map
                  ? "Toca un lugar. Cada reto que completes deja un sello en el mapa."
                  : practice
                    ? learner.support
                      ? "Podemos ir paso a paso. Pídeme una pista cuando la necesites."
                      : "Prueba tu idea. Si te atascas, tengo una pista para ti."
                    : "Lee cada pregunta y elige tu respuesta. Guardaré lo que escribas."}
              </p>
              {map ? (
                <button className="edu-button" onClick={() => navigate("peluqo")}>
                  <Sparkles size={18} aria-hidden="true" /> Personalizar
                </button>
              ) : (
                practice &&
                current && (
                  <>
                    {!currentDone && (
                      <button
                        className="edu-button expedition-hint"
                        disabled={busy}
                        onClick={async () => {
                          const reply = await run({
                            action: "hint",
                            sessionId: learning.id,
                            activityId: current.id,
                          });
                          if (reply) {
                            sound.play("select");
                            setMood("think");
                            setHelp(reply.hint);
                          }
                        }}
                      >
                        <Lightbulb size={18} aria-hidden="true" /> Pedir una pista
                      </button>
                    )}
                    <details className="expedition-chat">
                      <summary>
                        <MessageCircle size={18} aria-hidden="true" /> Preguntar a {pet.name}
                      </summary>
                      <form
                        onSubmit={async (event) => {
                          event.preventDefault();
                          setAsking(true);
                          setMood("think");
                          try {
                            const reply = await run({
                              action: "tutor",
                              sessionId: learning.id,
                              question,
                              requestId: crypto.randomUUID(),
                            });
                            if (reply) {
                              setQuestion("");
                              setHelp(reply.text);
                              setMood("happy");
                            }
                          } finally {
                            setAsking(false);
                          }
                        }}
                      >
                        <label>
                          Tu pregunta
                          <textarea
                            required
                            maxLength={1600}
                            value={question}
                            onFocus={() => setMood("listen")}
                            onChange={(event) => setQuestion(event.target.value)}
                            placeholder="¿Qué diferencia a un mamífero de un pez?"
                          />
                        </label>
                        <button className="edu-button primary" disabled={asking || busy}>
                          {asking ? "Buscando en el material…" : "Enviar mi pregunta"}
                        </button>
                      </form>
                    </details>
                    <div className="expedition-help" role="status">
                      {help}
                    </div>
                  </>
                )
              )}
            </div>
          </aside>
        </div>
      )}

      {!!learning?.turns.length && (
        <details className="expedition-journal">
          <summary>
            <BookOpen size={19} aria-hidden="true" /> Preguntas y fuentes del cuaderno{" "}
            <small>{learning.turns.length}</small>
          </summary>
          {learning.turns.map((turn) => (
            <article className="edu-turn" key={turn.id}>
              <strong>{turn.question}</strong>
              <p>{turn.text}</p>
              <small>
                {turn.sources
                  .map((source) => `${source.name}${source.page ? `, pág. ${source.page}` : ""}`)
                  .join(" · ") || "Respuesta de orientación"}
              </small>
            </article>
          ))}
        </details>
      )}
    </div>
  );
}
