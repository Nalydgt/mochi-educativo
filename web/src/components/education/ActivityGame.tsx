import { useEffect, useId, useRef, useState, type Ref } from "react";
import { ArrowRight, CircleX, MapPin, RotateCcw, X } from "lucide-react";
import type { Activity, PublicActivity, StudyFormat } from "@/lib/education/schema";
import { animalArt, artUrl } from "./fieldArt";
import {
  CircuitBoard,
  GuidedBoard,
  ListeningBoard,
  ManipulativeBoard,
  MatchingBoard,
  MemoryBoard,
  PuzzleBoard,
  SequenceBoard,
  type Answer,
  type GameInteraction,
} from "./GameBoards";
export type { GameInteraction } from "./GameBoards";

const mechanics = {
  question: null,
  classification: null,
  anatomy: null,
  matching: MatchingBoard,
  sequence: SequenceBoard,
  memory: MemoryBoard,
  puzzle: PuzzleBoard,
  listening: ListeningBoard,
  manipulatives: ManipulativeBoard,
  lab: CircuitBoard,
};

const diagrams = {
  moon: "Esquema de cuatro fases de la Luna",
  plant: "Esquema de una planta con flores",
  shapes: "Círculo, triángulo y cuadrado",
  timeline: "Línea del tiempo con tres posiciones",
};

function Diagram({
  asset,
  className,
  decorative,
}: {
  asset: keyof typeof diagrams;
  className: string;
  decorative: boolean;
}) {
  return (
    <svg
      viewBox="0 0 320 180"
      className={className}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : diagrams[asset]}
    >
      <g stroke="currentColor" strokeWidth="3" strokeLinejoin="round">
        {asset === "moon" && (
          <>
            <rect x="7" y="40" width="306" height="99" rx="18" fill="#dceeff" />
            {[45, 122, 198, 275].map((x, index) => (
              <circle key={x} cx={x} cy="88" r="27" fill={index === 2 ? "#ffd731" : "#2c3b57"} />
            ))}
            <path
              d="M122 61a27 27 0 0 1 0 54Z M275 61a27 27 0 0 0 0 54Z"
              fill="#ffd731"
              stroke="none"
            />
          </>
        )}
        {asset === "plant" && (
          <>
            <path
              d="M158 116V37M158 83Q182 47 238 62Q206 111 158 83M158 100Q122 62 77 77Q103 118 158 100"
              fill="#55db9c"
            />
            <path
              d="M35 120h250M158 120v36m0-28-25 34m25-35 31 26m-45-10-33 8m61-10 33 10"
              fill="none"
            />
            <path
              d="M156 18q-28-21-39 3-13 20 15 24-14 29 12 30 13 0 17-22 13 28 33 12 16-13-5-26 23-21 0-28-16-5-33 7Z"
              fill="#e9ccff"
            />
            <circle cx="158" cy="35" r="13" fill="#ffd731" />
          </>
        )}
        {asset === "shapes" && (
          <>
            <circle cx="64" cy="90" r="39" fill="#55db9c" />
            <path d="m160 46 44 79h-88Z" fill="#ffd731" />
            <rect x="218" y="52" width="76" height="76" rx="3" fill="#e9ccff" />
          </>
        )}
        {asset === "timeline" && (
          <>
            <path
              d="M16 90h287m-20-15 20 15-20 15"
              fill="none"
              strokeWidth="5"
              strokeLinecap="round"
            />
            {[48, 160, 272].map((x, i) => (
              <circle key={x} cx={x} cy="90" r="21" fill={["#55db9c", "#ffd731", "#e9ccff"][i]} />
            ))}
          </>
        )}
      </g>
    </svg>
  );
}

export function Animal({
  asset = "fish",
  className = "",
  decorative = false,
  schematic = false,
}: {
  asset?: string;
  className?: string;
  decorative?: boolean;
  schematic?: boolean;
}) {
  const species = {
    fish: "Pez",
    frog: "Rana",
    turtle: "Tortuga",
    bird: "Ave",
    dolphin: "Delfín",
    cat: "Gato",
    human: "Figura humana de frente, con brazos y piernas separados",
  };
  const art = animalArt[asset];
  if (art && (!schematic || asset === "human"))
    return (
      <img
        src={artUrl(art)}
        className={`edu-animal-art ${className}`}
        alt={decorative ? "" : (species[asset as keyof typeof species] ?? "Animal")}
        draggable={false}
      />
    );
  if (Object.hasOwn(diagrams, asset))
    return (
      <Diagram
        asset={asset as keyof typeof diagrams}
        className={className}
        decorative={decorative}
      />
    );
  const fish = asset === "fish" || asset === "dolphin";
  return (
    <svg
      viewBox="0 0 320 180"
      className={className}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={
        decorative
          ? undefined
          : ({
              fish: "Pez, esquema anatómico",
              dolphin: "Delfín",
              cat: "Gato",
              bird: "Ave",
              turtle: "Tortuga",
              frog: "Rana",
            }[asset] ?? "Animal")
      }
    >
      <g stroke="currentColor" strokeWidth="3" strokeLinejoin="round">
        {asset === "dolphin" ? (
          <>
            <path
              d="M22 106 5 77 42 86Q87 39 174 53Q208 20 248 47L286 66 314 77 279 89Q251 123 187 132L155 158 142 130Q88 136 42 110L7 133Z"
              fill="#4da2ff"
            />
            <path d="M141 54 166 14 194 55M212 93l-9 31 34-16M228 53l10-1" fill="#4da2ff" />
          </>
        ) : fish ? (
          <>
            <path d="M34 90 6 48v84z" fill="#4da2ff" />
            <ellipse
              cx="168"
              cy="90"
              rx="130"
              ry="58"
              fill={asset === "fish" ? "#55db9c" : "#4da2ff"}
            />
            <path d="M120 38 156 8l25 34M110 136l40 30 22-29" fill="#4da2ff" />
            <path d="M230 45q-25 45 0 90" fill="none" />
          </>
        ) : asset === "bird" ? (
          <>
            <ellipse cx="145" cy="102" rx="90" ry="55" fill="#e9ccff" />
            <circle cx="232" cy="58" r="35" fill="#e9ccff" />
            <path d="m264 55 35 13-35 9M104 152v20m62-20v20M55 100 15 69l7 45" fill="#ffd731" />
            <path d="M100 84q80-8 52 61" fill="none" />
          </>
        ) : asset === "turtle" ? (
          <>
            <ellipse cx="152" cy="94" rx="94" ry="65" fill="#55db9c" />
            <ellipse cx="267" cy="92" rx="35" ry="27" fill="#ffd731" />
            <path d="m94 142-32 25 66-10m55-3 58 18-20-32" fill="#55db9c" />
            <path d="m118 51 61-1 35 47-32 43-65-2-26-43z" fill="none" />
          </>
        ) : asset === "frog" ? (
          <>
            <ellipse cx="160" cy="112" rx="95" ry="49" fill="#55db9c" />
            <circle cx="122" cy="61" r="31" fill="#55db9c" />
            <circle cx="198" cy="61" r="31" fill="#55db9c" />
            <path d="m65 121-38 40 75-2m149-38 38 40-75-2" fill="#55db9c" />
            <path d="M118 111q42 35 84 0" fill="none" />
          </>
        ) : (
          <>
            <ellipse cx="145" cy="104" rx="98" ry="46" fill="#ffd731" />
            <circle cx="246" cy="65" r="44" fill="#ffd731" />
            <path
              d="m211 34 7-25 24 16m23 0 21-15 2 33M75 136v33m63-28v28m74-33v33M49 94Q-8 9 46 14"
              fill="#ffd731"
            />
          </>
        )}
        <circle
          cx={
            asset === "frog"
              ? 122
              : fish
                ? 260
                : asset === "bird"
                  ? 242
                  : asset === "turtle"
                    ? 281
                    : 260
          }
          cy={
            asset === "frog" ? 60 : fish ? 76 : asset === "bird" ? 50 : asset === "turtle" ? 84 : 59
          }
          r="6"
          fill="currentColor"
        />
        {asset === "frog" && <circle cx="198" cy="60" r="6" fill="currentColor" />}
      </g>
    </svg>
  );
}

export function ActivityGame({
  activity: a,
  disabled = false,
  onSubmit,
  preview = false,
  showIllustration = false,
  headingRef,
  retryFeedback,
  onEdit,
  studyFormat = "board",
  onInteraction,
}: {
  activity: PublicActivity | Activity;
  disabled?: boolean;
  onSubmit: (answer: Record<string, string>) => Promise<void>;
  preview?: boolean;
  showIllustration?: boolean;
  headingRef?: Ref<HTMLHeadingElement>;
  retryFeedback?: string | undefined;
  onEdit?: () => void;
  studyFormat?: StudyFormat;
  onInteraction?: ((kind: GameInteraction) => void) | undefined;
}) {
  const feedbackId = useId();
  const [answer, setAnswer] = useState<Answer>({});
  const [discarded, setDiscarded] = useState<readonly string[]>([]);
  const [drag, setDrag] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [placement, setPlacement] = useState("");
  const actions = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (retryFeedback) actions.current?.scrollIntoView?.({ block: "nearest" });
  }, [retryFeedback]);
  function change(next: Answer) {
    setAnswer(next);
    onEdit?.();
  }
  function place(piece: string, target: string) {
    if (disabled) return;
    onInteraction?.("move");
    if ((answer[piece] ?? "") !== target) onEdit?.();
    setAnswer((v) => ({ ...v, [piece]: target }));
    const label = a.pieces.find((item) => item.id === piece)?.label;
    const destination = a.choices.find((choice) => choice.id === target)?.label;
    setPlacement(destination ? `${label} en ${destination}` : `${label} sin colocar`);
    setDrag(null);
    setSelected(null);
  }
  const placed = a.pieces.filter((piece) => answer[piece.id]).length;
  const eliminate = a.type === "question" && studyFormat === "cards";
  const remaining = a.choices.filter((c) => !discarded.includes(c.id));
  const submitting: Answer = eliminate
    ? { choice: remaining[0]?.id ?? "" }
    : a.type === "lab"
      ? { battery: answer["battery"] ?? "off", switch: answer["switch"] ?? "off" }
      : a.type === "manipulatives"
        ? Object.fromEntries(a.pieces.map((p) => [p.id, answer[p.id] ?? "0"]))
        : answer;
  const ready =
    a.type === "question"
      ? eliminate
        ? remaining.length === 1
        : !!answer["choice"]
      : a.type === "lab" || a.type === "manipulatives" || placed === a.pieces.length;
  const Mechanic =
    mechanics[a.type] ?? (studyFormat === "cards" && a.type !== "question" ? GuidedBoard : null);
  return (
    <section className="edu-game" aria-label={a.title} aria-busy={disabled}>
      <p className="edu-tag">{a.competency}</p>
      <h2 ref={headingRef} tabIndex={headingRef ? -1 : undefined}>
        {a.title}
      </h2>
      <p className="edu-instructions">{a.instruction}</p>
      {a.type === "question" && showIllustration && (
        <div className="edu-observation">
          <Animal asset={a.asset} decorative />
        </div>
      )}
      {Mechanic ? (
        <Mechanic
          activity={a}
          answer={answer}
          change={change}
          disabled={disabled}
          Art={Animal}
          onInteraction={onInteraction}
        />
      ) : eliminate ? (
        <div className="edu-mechanic">
          <p className="edu-help">
            Descarta las opciones que no encajan. Deja en juego la que quieras enviar.
          </p>
          <div className="edu-elimination" aria-label="Opciones para descartar">
            {a.choices.map((c) => {
              const removed = discarded.includes(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  className="edu-play-tile"
                  disabled={disabled || (!removed && remaining.length === 1)}
                  aria-label={`${removed ? "Recuperar" : "Descartar"} ${c.label}`}
                  aria-pressed={removed}
                  data-discarded={removed}
                  data-incorrect={!!retryFeedback && !removed}
                  aria-describedby={retryFeedback && !removed ? feedbackId : undefined}
                  onClick={() => {
                    setDiscarded((values) =>
                      removed ? values.filter((id) => id !== c.id) : [...values, c.id],
                    );
                    onEdit?.();
                    onInteraction?.("move");
                  }}
                >
                  <span>{c.label}</span>
                  <span className="edu-elimination-action">
                    {removed ? <RotateCcw size={17} /> : <X size={17} />}
                    {removed ? "Recuperar" : "Descartar"}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="edu-board-status" aria-live="polite">
            {remaining.length === 1
              ? `En juego: ${remaining[0]?.label}`
              : `${remaining.length} opciones en juego`}
          </p>
        </div>
      ) : a.type === "question" ? (
        <fieldset disabled={disabled}>
          <legend className="sr-only">Selecciona una respuesta</legend>
          {a.choices.map((c) => (
            <label
              key={c.id}
              className={`edu-option ${answer["choice"] === c.id ? "is-selected" : ""}`}
              data-incorrect={!!retryFeedback && answer["choice"] === c.id}
            >
              <input
                type="radio"
                name={`answer-${a.id}`}
                value={c.id}
                checked={answer["choice"] === c.id}
                aria-describedby={
                  retryFeedback && answer["choice"] === c.id ? feedbackId : undefined
                }
                onChange={() => {
                  setAnswer({ choice: c.id });
                  onEdit?.();
                  onInteraction?.("select");
                }}
              />
              {c.label}
            </label>
          ))}
        </fieldset>
      ) : (
        <>
          {a.type === "anatomy" && (
            <div className="edu-anatomy">
              <div className="edu-anatomy-figure" data-figure={a.asset}>
                <Animal asset={a.asset} schematic />
                {a.choices.map((c, i) => (
                  <button
                    type="button"
                    className="edu-anatomy-marker"
                    key={c.id}
                    style={{ left: `${c.x ?? 50}%`, top: `${c.y ?? 50}%` }}
                    aria-label={`Zona ${i + 1}: ${c.label}`}
                    data-ready={!!selected}
                    data-placed={a.pieces.some((p) => answer[p.id] === c.id)}
                    disabled={disabled}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      const id = drag ?? e.dataTransfer.getData("text/plain");
                      if (a.pieces.some((p) => p.id === id)) place(id, c.id);
                    }}
                    onClick={() => {
                      if (selected) place(selected, c.id);
                    }}
                  >
                    {i + 1}
                    {a.pieces.some((p) => answer[p.id] === c.id) && (
                      <small className="edu-anatomy-placed">
                        {a.pieces
                          .filter((p) => answer[p.id] === c.id)
                          .map((p) => p.label)
                          .join(", ")}
                      </small>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
          <p className="edu-help">
            Elige una pieza y toca su destino. También puedes arrastrarla o usar las listas.
          </p>
          <div className="edu-placement-count" aria-hidden="true">
            {placed} de {a.pieces.length} piezas colocadas
          </div>
          <span className="sr-only" role="status">
            {placement}
          </span>
          <div className="edu-pieces">
            {a.pieces.map((p) => (
              <button
                key={p.id}
                type="button"
                draggable={!disabled}
                disabled={disabled}
                aria-pressed={selected === p.id}
                data-placed={!!answer[p.id]}
                className={`edu-piece ${selected === p.id ? "is-selected" : ""}`}
                onDragStart={(e) => {
                  setDrag(p.id);
                  setSelected(p.id);
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData("text/plain", p.id);
                }}
                onDragEnd={() => setDrag(null)}
                onClick={() => setSelected(p.id)}
              >
                {p.asset && <Animal asset={p.asset} decorative />}
                <strong>{p.label}</strong>
                {answer[p.id] && (
                  <small>
                    <MapPin size={14} aria-hidden="true" />
                    {a.choices.find((c) => c.id === answer[p.id])?.label}
                  </small>
                )}
              </button>
            ))}
          </div>
          <div className="edu-targets" aria-label="Destinos" data-ready={!!selected}>
            {a.choices.map((c, i) => {
              const labels = a.pieces
                .filter((piece) => answer[piece.id] === c.id)
                .map((piece) => piece.label);
              return (
                <button
                  key={c.id}
                  type="button"
                  disabled={disabled}
                  aria-disabled={disabled || !selected}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const p = drag ?? e.dataTransfer.getData("text/plain");
                    if (a.pieces.some((x) => x.id === p)) place(p, c.id);
                  }}
                  onClick={() => {
                    if (selected) place(selected, c.id);
                  }}
                  className="edu-target"
                >
                  <strong>
                    {a.type === "anatomy" ? `${i + 1}. ` : ""}
                    {c.label}
                  </strong>
                  {labels.length > 0 && <small>{labels.join(", ")}</small>}
                </button>
              );
            })}
          </div>
          <details className="edu-placement-lists">
            <summary>Elegir los destinos con listas</summary>
            <fieldset disabled={disabled} className="edu-accessible-placements">
              <legend className="sr-only">Colocación por selección</legend>
              {a.pieces.map((p) => (
                <label key={p.id}>
                  {p.label}
                  <select value={answer[p.id] ?? ""} onChange={(e) => place(p.id, e.target.value)}>
                    <option value="">Selecciona el destino</option>
                    {a.choices.map((c, i) => (
                      <option key={c.id} value={c.id}>
                        {a.type === "anatomy" ? `${i + 1}. ` : ""}
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </fieldset>
          </details>
        </>
      )}
      <div ref={actions} className="edu-answer-actions">
        <div id={feedbackId} className="edu-retry-feedback" role="status">
          {retryFeedback && (
            <>
              <CircleX size={26} aria-hidden="true" />
              <div>
                <strong>
                  {a.type === "question" ? "Respuesta incorrecta" : "Revisa tu respuesta"}
                </strong>
                <p>{retryFeedback}</p>
              </div>
            </>
          )}
        </div>
        <button
          type="button"
          className="edu-button primary"
          disabled={!ready || disabled}
          onClick={() => void onSubmit(submitting)}
        >
          {preview
            ? "Comprobar en la vista previa"
            : retryFeedback
              ? "Volver a comprobar"
              : "Enviar respuesta"}
          {!preview && <ArrowRight size={17} aria-hidden="true" />}
        </button>
      </div>
    </section>
  );
}
