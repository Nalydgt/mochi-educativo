import { useState } from "react";
import { BookOpen, Compass, Flag, Lock, Medal, SlidersHorizontal, Sparkles } from "lucide-react";
import type { MascotMood } from "@/components/Stickers";
import {
  learnerAgeBands,
  learnerGoals,
  learnerGuides,
  personalGoalProgress,
  type LearnerMilestones,
  type LearnerPreferences,
} from "@/lib/education/personalization";
import {
  activityLabels,
  activityTypes,
  allowedAccessory,
  worldThemes,
  type Companion,
  type Phase,
} from "@/lib/education/schema";
import { FieldGuide } from "./FieldGuide";
import { animalArt, artUrl, fieldArt, guideArt, landmarkArt } from "./fieldArt";
import type { WorldListing } from "./WorldSpaces";
import "./personalization.css";

export function WebStudyGuide({
  guide,
  className = "",
  mood = "idle",
  ...pet
}: Partial<Companion> & {
  guide: LearnerPreferences["guide"];
  className?: string;
  mood?: MascotMood;
}) {
  if (guide === "peluqo") return <FieldGuide {...pet} className={className} mood={mood} />;
  return (
    <span
      className={`field-guide study-guide ${className}`}
      data-mood={mood}
      role="img"
      aria-label={learnerGuides[guide]}
    >
      <img src={artUrl(animalArt[guide]!)} alt="" draggable={false} />
    </span>
  );
}

const themeKeys = ["reserve", "space", "workshop"] as const;
const guideKeys = ["peluqo", "frog", "fish"] as const;
const goalKeys = ["explore", "practice", "finish"] as const;
const historyLabels: Record<Phase, string> = {
  diagnostic: "Punto de partida",
  practice: "En exploración",
  final: "Reto final",
  completed: "Completada",
  retention: "Repasando",
};

export function LearnerPersonalization({
  preferences,
  pet,
  progress,
  worlds,
  history,
  busy,
  onSave,
}: {
  preferences: LearnerPreferences;
  pet: Companion;
  progress: LearnerMilestones;
  worlds: WorldListing[];
  history: { versionId: string; phase: Phase }[];
  busy: boolean;
  onSave: (value: LearnerPreferences) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState(preferences);
  const [saved, setSaved] = useState(false);
  const goal = personalGoalProgress(draft.goal, progress);
  const goalComplete = goal.completed === goal.total;
  const worldsById = new Map(worlds.map((world) => [world.id, world]));
  const seen = new Set<string>();
  const visited = history.flatMap((entry) => {
    const world = worldsById.get(entry.versionId);
    if (!world || seen.has(entry.versionId)) return [];
    seen.add(entry.versionId);
    return [{ ...entry, world }];
  });
  const badges = [
    {
      title: "Primer descubrimiento",
      art: landmarkArt.classification,
      description: "Resuelve tu primer reto",
      unlocked: progress.discoveries >= 1,
    },
    {
      title: "Pañuelo de exploración",
      art: guideArt.scarf,
      description: "Resuelve tres retos",
      unlocked: allowedAccessory("scarf", progress.discoveries, progress.completed),
    },
    {
      title: "Estrella de expedición",
      art: guideArt.star,
      description: "Termina una aventura",
      unlocked: allowedAccessory("star", progress.discoveries, progress.completed),
    },
  ];

  function change(values: Partial<LearnerPreferences>) {
    setSaved(false);
    setDraft((previous) => ({ ...previous, ...values }));
  }

  function toggle(mechanic: LearnerPreferences["mechanics"][number]) {
    change({
      mechanics: draft.mechanics.includes(mechanic)
        ? draft.mechanics.filter((id) => id !== mechanic)
        : [...draft.mechanics, mechanic],
    });
  }

  return (
    <section className="study-personalization" aria-labelledby="personalization-heading">
      <header
        className="study-profile-hero"
        data-theme={draft.theme}
        style={{ backgroundImage: `url(${artUrl(fieldArt[draft.theme].background)})` }}
      >
        <div>
          <span>
            <Compass size={17} aria-hidden="true" /> Mi cuaderno
          </span>
          <h2 id="personalization-heading">Explora a tu manera</h2>
          <p>Elige quién te acompaña, qué juegos quieres descubrir y cuál será tu objetivo.</p>
        </div>
        <WebStudyGuide {...pet} guide={draft.guide} mood={saved ? "celebrate" : "idle"} />
      </header>

      <div className="study-profile-layout">
        <form
          className="study-profile-controls"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await onSave(draft)) setSaved(true);
          }}
        >
          <h3>
            <SlidersHorizontal size={20} aria-hidden="true" /> Mi experiencia
          </h3>
          <fieldset>
            <legend>Compañero de la web</legend>
            <div className="study-guide-choices">
              {guideKeys.map((guide) => (
                <label key={guide}>
                  <input
                    type="radio"
                    name="web-guide"
                    value={guide}
                    checked={draft.guide === guide}
                    onChange={() => change({ guide })}
                  />
                  <WebStudyGuide {...pet} guide={guide} />
                  <span>{learnerGuides[guide]}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="study-profile-selects">
            <label>
              Ambiente
              <select
                value={draft.theme}
                onChange={(event) =>
                  change({ theme: event.target.value as LearnerPreferences["theme"] })
                }
              >
                {themeKeys.map((theme) => (
                  <option key={theme} value={theme}>
                    {worldThemes[theme]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Vista por edades
              <select
                value={draft.ageBand}
                onChange={(event) =>
                  change({ ageBand: event.target.value as LearnerPreferences["ageBand"] })
                }
              >
                {learnerAgeBands.map((age) => (
                  <option key={age} value={age}>
                    {age} años
                  </option>
                ))}
              </select>
            </label>
          </div>
          <fieldset>
            <legend>Mis juegos favoritos</legend>
            <p className="study-profile-hint">
              Elige hasta tres para tenerlos en cuenta en tus recomendaciones.
            </p>
            <div className="study-mechanics-choices">
              {activityTypes.map((mechanic) => {
                const selected = draft.mechanics.includes(mechanic);
                return (
                  <label key={mechanic}>
                    <input
                      type="checkbox"
                      checked={selected}
                      disabled={!selected && draft.mechanics.length >= 3}
                      onChange={() => toggle(mechanic)}
                    />
                    <span>{activityLabels[mechanic]}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
          <label>
            Mi objetivo
            <select
              value={draft.goal}
              onChange={(event) =>
                change({ goal: event.target.value as LearnerPreferences["goal"] })
              }
            >
              {goalKeys.map((key) => (
                <option key={key} value={key}>
                  {learnerGoals[key].label}
                </option>
              ))}
            </select>
          </label>
          <button className="edu-button primary" disabled={busy}>
            {busy ? "Guardando…" : "Guardar mis preferencias"}
          </button>
          {saved && (
            <p className="study-profile-saved" role="status">
              Tus preferencias están guardadas.
            </p>
          )}
        </form>

        <div className="study-profile-record">
          <section className="study-personal-goal">
            <h3>
              <Flag size={20} aria-hidden="true" /> Mi objetivo
            </h3>
            <p>{goal.label}</p>
            {goal.completed === null ? (
              <small>El progreso se calcula cuando registres tu práctica.</small>
            ) : (
              <>
                <progress
                  value={goal.completed}
                  max={goal.total}
                  aria-label={`Avance de mi objetivo: ${goal.label}`}
                />
                <strong>
                  {goalComplete ? "Objetivo cumplido" : `${goal.completed} de ${goal.total}`}
                </strong>
              </>
            )}
          </section>
          <section className="study-personal-rewards">
            <h3>
              <Medal size={20} aria-hidden="true" /> Mis coleccionables
            </h3>
            <ul>
              {badges.map((badge) => (
                <li key={badge.title} data-unlocked={badge.unlocked}>
                  <img src={artUrl(badge.art)} alt="" loading="lazy" />
                  <span>
                    <strong>{badge.title}</strong>
                    <small>{badge.unlocked ? "Conseguido" : badge.description}</small>
                  </span>
                  {badge.unlocked ? (
                    <Sparkles size={16} aria-hidden="true" />
                  ) : (
                    <Lock size={16} aria-label="Pendiente" />
                  )}
                </li>
              ))}
            </ul>
          </section>
          <section className="study-personal-history">
            <h3>
              <BookOpen size={20} aria-hidden="true" /> Mis aventuras
            </h3>
            {visited.length > 0 ? (
              <ul>
                {visited.map(({ world, phase }) => (
                  <li key={world.id}>
                    <span>
                      <strong>{world.title}</strong>
                      <small>{worldThemes[world.theme]}</small>
                    </span>
                    <span className="study-history-phase" data-phase={phase}>
                      {historyLabels[phase]}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>Aquí aparecerá la primera aventura que abras.</p>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
