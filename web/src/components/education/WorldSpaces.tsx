import { useState } from "react";
import { ArrowRight, BookOpen, Compass, MessageCircle, Send, Sparkles } from "lucide-react";
import { FieldGuide } from "./FieldGuide";
import { SubjectUniverse, subjectZones } from "./SubjectUniverse";
import {
  subjects,
  worldThemes,
  type Companion,
  type Phase,
  type World,
} from "@/lib/education/schema";
import { artUrl, landmarkArt } from "./fieldArt";

export type WorldListing = {
  id: string;
  title: string;
  intro: string;
  theme: World["theme"];
  subject?: string | null;
  course?: string | null;
};
export type CuriosityTurn = {
  id: string;
  question: string;
  text: string;
  kind: "material" | "general" | "guidance";
  sources: { name: string; page: number | null }[];
};
const prompts = [
  "¿Por qué cambia la Luna?",
  "¿Cómo sumo dos fracciones?",
  "¿Cómo vivían en el antiguo Egipto?",
];
const worldArt = {
  reserve: landmarkArt.classification,
  space: landmarkArt.question,
  workshop: landmarkArt.anatomy,
};

export function WorldLibrary({
  worlds,
  progress,
  lockedVersion,
  busy,
  onOpen,
  pet,
}: {
  worlds: WorldListing[];
  progress: { versionId: string; phase: Phase }[];
  lockedVersion: string | undefined;
  busy: boolean;
  onOpen: (id: string) => void;
  pet?: Companion | undefined;
}) {
  const [subject, setSubject] = useState("");
  const zones = subjectZones(worlds);
  const grouped = zones.map((zone) => ({
    ...zone,
    worlds: worlds.filter(
      (world) =>
        (world.subject && world.subject in subjects ? world.subject : "sin_clasificar") === zone.id,
    ),
  }));
  const visible = grouped.filter((group) =>
    subject ? group.id === subject : group.worlds.length > 0,
  );
  const activeProgress =
    progress.find((entry) => entry.versionId === lockedVersion) ??
    progress.find(
      (entry) =>
        entry.phase !== "completed" && worlds.some((world) => world.id === entry.versionId),
    );
  const activeWorld = worlds.find((world) => world.id === activeProgress?.versionId);

  return (
    <section className="world-library world-library-universe" aria-labelledby="world-library-title">
      <header className="expedition-intro">
        <div>
          <p className="expedition-greeting">
            <Compass size={18} aria-hidden="true" /> Mis mundos
          </p>
          <h1 id="world-library-title">Tu universo de aprendizaje</h1>
          <p>Elige una asignatura y cruza su portal.</p>
        </div>
      </header>
      {lockedVersion && (
        <p className="universe-assessment-note" role="status">
          Termina las preguntas de tu aventura para abrir otro mundo.
        </p>
      )}
      <SubjectUniverse zones={zones} selected={subject} onSelect={setSubject} pet={pet} />
      {activeWorld && (
        <aside className="universe-resume">
          <span>
            <small>Tu aventura en curso</small>
            <strong>{activeWorld.title}</strong>
          </span>
          <button
            type="button"
            className="edu-button primary"
            disabled={busy || (!!lockedVersion && lockedVersion !== activeWorld.id)}
            onClick={() => onOpen(activeWorld.id)}
          >
            Continuar mi aventura <ArrowRight size={18} aria-hidden="true" />
          </button>
        </aside>
      )}
      <div className="universe-directory-bar">
        <button
          type="button"
          className="universe-all"
          aria-pressed={!subject}
          onClick={() => setSubject("")}
        >
          Ver todas las aventuras <ArrowRight size={16} aria-hidden="true" />
        </button>
        <details className="universe-shortcuts">
          <summary>Elegir una asignatura por nombre</summary>
          <div className="world-subjects" role="group" aria-label="Asignaturas">
            <button type="button" aria-pressed={!subject} onClick={() => setSubject("")}>
              Todas <span>{worlds.length}</span>
            </button>
            {zones.map((zone) => (
              <button
                type="button"
                key={zone.id}
                aria-pressed={subject === zone.id}
                onClick={() => setSubject(zone.id)}
              >
                {zone.name} <span>{zone.count}</span>
              </button>
            ))}
          </div>
        </details>
      </div>
      <div className="universe-adventures" id="universe-adventures" aria-live="polite">
        {visible.map((group) => (
          <section
            key={group.id}
            className="world-subject-section universe-destination"
            aria-labelledby={`world-subject-${group.id}`}
          >
            <h2 id={`world-subject-${group.id}`}>
              {group.name}{" "}
              <small>
                {group.worlds.length} {group.worlds.length === 1 ? "aventura" : "aventuras"}
              </small>
            </h2>
            {group.worlds.length > 0 ? (
              <div className="universe-adventure-list">
                {group.worlds.map((world) => {
                  const started = progress.find((entry) => entry.versionId === world.id);
                  const scenery = { reserve: "reserva", space: "observatorio", workshop: "taller" }[
                    world.theme
                  ];
                  return (
                    <article className="universe-adventure" key={world.id}>
                      <div className="universe-adventure-art" aria-hidden="true">
                        <img src={artUrl(scenery)} alt="" width={300} height={180} />
                        <img src={artUrl(worldArt[world.theme])} alt="" width={120} height={120} />
                      </div>
                      <div className="universe-adventure-copy">
                        <span className="universe-adventure-kind">
                          {worldThemes[world.theme]}
                          {started &&
                            ` · ${started.phase === "completed" ? "Cuaderno completado" : "Aventura empezada"}`}
                        </span>
                        <h3>{world.title}</h3>
                        {world.course && <small className="world-course">{world.course}</small>}
                        <p>{world.intro}</p>
                      </div>
                      <button
                        type="button"
                        className="edu-button primary"
                        disabled={busy || (!!lockedVersion && lockedVersion !== world.id)}
                        onClick={() => onOpen(world.id)}
                      >
                        {started?.phase === "completed"
                          ? "Abrir mi cuaderno"
                          : started
                            ? "Continuar mundo"
                            : "Explorar mundo"}{" "}
                        <ArrowRight size={18} aria-hidden="true" />
                      </button>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="universe-coming">
                Este portal está preparado para las aventuras que publique tu docente. Puedes
                explorar otra asignatura mientras tanto.
              </p>
            )}
          </section>
        ))}
        {!worlds.length && (
          <p className="universe-coming">
            Tu docente está preparando los primeros mundos. Mientras tanto, puedes hacer preguntas a
            Peluqo.
          </p>
        )}
      </div>
    </section>
  );
}

const originLabels = {
  material: "Material del aula",
  general: "Conocimiento general",
  guidance: "Orientación de Peluqo",
};

function CuriosityAnswer({ turn }: { turn: CuriosityTurn }) {
  return (
    <article className="curiosity-answer">
      <span className="curiosity-origin" data-kind={turn.kind}>
        <BookOpen size={15} aria-hidden="true" />
        {originLabels[turn.kind]}
      </span>
      <h3>{turn.question}</h3>
      <p>{turn.text}</p>
      {turn.sources.length > 0 && (
        <ul className="curiosity-sources" aria-label="Fuentes consultadas">
          {turn.sources.map((source, i) => (
            <li key={`${source.name}-${i}`}>
              {source.name}
              {source.page ? ` · pág. ${source.page}` : ""}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function CuriosityRoom({
  pet,
  turns,
  locked,
  onAsk,
  onBack,
}: {
  pet: Companion;
  turns: CuriosityTurn[];
  locked: boolean;
  onAsk: (question: string) => Promise<boolean>;
  onBack: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [latest, ...history] = turns;
  return (
    <section className="curiosity-room" aria-labelledby="curiosity-title">
      <div className="curiosity-guide">
        <span>
          <Sparkles size={19} aria-hidden="true" /> Preguntas con Peluqo
        </span>
        <h1 id="curiosity-title">¿Qué te da curiosidad?</h1>
        <p>Elige un tema y cuéntame qué quieres entender. Podemos ir paso a paso.</p>
        <FieldGuide
          color={pet.color}
          accessory={pet.accessory}
          mood={asking ? "think" : latest ? "happy" : "listen"}
        />
      </div>
      <div className="curiosity-desk">
        {locked ? (
          <div className="edu-panel">
            <h2>Termina esta etapa</h2>
            <p>Después de guardar tus respuestas, podremos seguir conversando.</p>
            <button type="button" className="edu-button primary" onClick={onBack}>
              Volver a la actividad <ArrowRight size={18} aria-hidden="true" />
            </button>
          </div>
        ) : (
          <>
            <form
              className="curiosity-form"
              onSubmit={async (event) => {
                event.preventDefault();
                const value = question.trim();
                if (!value || asking) return;
                setAsking(true);
                try {
                  if (await onAsk(value)) setQuestion("");
                } finally {
                  setAsking(false);
                }
              }}
            >
              <label>
                <MessageCircle size={19} aria-hidden="true" /> Tu pregunta
                <textarea
                  name="curiosity"
                  required
                  maxLength={1600}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Escribe lo que quieras aprender…"
                />
              </label>
              <div className="curiosity-prompts" aria-label="Ideas para empezar">
                {prompts.map((prompt) => (
                  <button
                    type="button"
                    key={prompt}
                    onClick={() => setQuestion(prompt)}
                    disabled={asking}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              <button className="edu-button primary" disabled={asking || !question.trim()}>
                {asking ? "Peluqo está pensando…" : "Preguntar a Peluqo"}{" "}
                <Send size={17} aria-hidden="true" />
              </button>
            </form>
            <div className="curiosity-latest" aria-live="polite">
              {latest && <CuriosityAnswer turn={latest} />}
            </div>
            {history.length > 0 && (
              <details className="expedition-journal">
                <summary>
                  Mis preguntas anteriores <small>{history.length}</small>
                </summary>
                {history.map((turn) => (
                  <CuriosityAnswer key={turn.id} turn={turn} />
                ))}
              </details>
            )}
          </>
        )}
      </div>
    </section>
  );
}
