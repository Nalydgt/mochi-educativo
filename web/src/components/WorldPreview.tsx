import { useState, type Dispatch, type SetStateAction } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Compass,
  Minus,
  Plus,
  RotateCcw,
  X,
} from "lucide-react";
import { presentationArt, presentationSprite } from "./BrandMark";

const scenes = [
  {
    id: "reserve",
    name: "Reserva",
    image: "reserva",
    trail: "Sendero del río",
    alt: "Un sendero junto al río entre helechos y montañas",
  },
  {
    id: "space",
    name: "Observatorio",
    image: "observatorio",
    trail: "Paseo del observatorio",
    alt: "Un observatorio en una colina bajo la luna",
  },
  {
    id: "workshop",
    name: "Taller",
    image: "taller",
    trail: "Taller de ideas",
    alt: "Un taller luminoso con plantas, cuadernos y objetos para explorar",
  },
] as const;

type Notice = { correct: boolean; text: string };
type ChallengeProps = { onComplete: (completed: boolean) => void };

function Feedback({ notice }: { notice: Notice | undefined }) {
  return notice ? (
    <p
      className="preview-feedback"
      data-correct={notice.correct}
      role={notice.correct ? "status" : "alert"}
    >
      {notice.text}
    </p>
  ) : null;
}

function AnimalChallenge({ onComplete }: ChallengeProps) {
  const [selected, setSelected] = useState<string>();
  const [placed, setPlaced] = useState<string[]>([]);
  const [notice, setNotice] = useState<Notice>();
  const animals = [
    { id: "frog", name: "Rana", sprite: "rana", group: "anfibios" },
    { id: "fish", name: "Pez", sprite: "pez", group: "peces" },
  ];

  function place(group: string, piece = selected) {
    const animal = animals.find((item) => item.id === piece);
    if (!animal || placed.includes(animal.id)) return;
    if (animal.group !== group) {
      setNotice({
        correct: false,
        text:
          animal.id === "fish"
            ? "El pez respira con branquias. Prueba con el otro grupo."
            : "La rana cambia mucho al crecer. Piensa en los anfibios.",
      });
      return;
    }
    const next = [...placed, animal.id];
    setPlaced(next);
    setSelected(undefined);
    setNotice({
      correct: true,
      text:
        next.length === animals.length
          ? "¡Los dos en su grupo! Acabas de clasificar vertebrados."
          : "¡Bien! Ahora busca el grupo del otro animal.",
    });
    if (next.length === animals.length) onComplete(true);
  }

  return (
    <>
      <h3>Clasifica a los habitantes del río</h3>
      <p>Elige un animal y después su grupo. También puedes arrastrarlo.</p>
      <div className="preview-animals">
        {animals.map((animal) => (
          <button
            type="button"
            className="preview-animal"
            key={animal.id}
            draggable={!placed.includes(animal.id)}
            disabled={placed.includes(animal.id)}
            aria-pressed={selected === animal.id}
            onClick={() => {
              setSelected(animal.id);
              setNotice(undefined);
            }}
            onDragStart={(event) => {
              event.dataTransfer.setData("text/plain", animal.id);
              setSelected(animal.id);
            }}
          >
            <img src={presentationSprite(animal.sprite)} width={90} height={70} alt="" />
            <span>
              {animal.name}
              {placed.includes(animal.id) && " · Colocado"}
            </span>
          </button>
        ))}
      </div>
      <div className="preview-targets">
        {["anfibios", "peces"].map((group) => (
          <button
            type="button"
            key={group}
            onClick={() => place(group)}
            disabled={placed.length === animals.length}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              place(group, event.dataTransfer.getData("text/plain"));
            }}
          >
            {group === "anfibios" ? "Anfibios" : "Peces"}
          </button>
        ))}
      </div>
      <Feedback notice={notice} />
    </>
  );
}

const moonSteps = [
  { id: "full", label: "Luna llena" },
  { id: "new", label: "Luna nueva" },
  { id: "quarter", label: "Cuarto creciente" },
];

function SequenceChallenge({ onComplete }: ChallengeProps) {
  const [steps, setSteps] = useState(moonSteps);
  const [notice, setNotice] = useState<Notice>();
  function move(index: number, direction: number) {
    const next = [...steps];
    const first = next[index];
    const second = next[index + direction];
    if (!first || !second) return;
    next[index] = second;
    next[index + direction] = first;
    setSteps(next);
    setNotice(undefined);
    onComplete(false);
  }
  return (
    <>
      <h3>De Luna nueva a Luna llena</h3>
      <p>Ordena estas tres fases con las flechas.</p>
      <ol className="preview-sequence">
        {steps.map((step, index) => (
          <li key={step.id}>
            <span className="preview-step">{index + 1}</span>
            <strong>{step.label}</strong>
            <button
              type="button"
              onClick={() => move(index, -1)}
              disabled={!index}
              aria-label={`Subir ${step.label}`}
            >
              <ArrowUp size={16} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => move(index, 1)}
              disabled={index === steps.length - 1}
              aria-label={`Bajar ${step.label}`}
            >
              <ArrowDown size={16} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="preview-check"
        onClick={() => {
          const correct = steps.map((step) => step.id).join(",") === "new,quarter,full";
          setNotice({
            correct,
            text: correct
              ? "¡Así crece la parte iluminada de la Luna que vemos!"
              : "Comienza por Luna nueva. Después vemos cada vez más parte iluminada.",
          });
          onComplete(correct);
        }}
      >
        Comprobar el orden
      </button>
      <Feedback notice={notice} />
    </>
  );
}

function CountingChallenge({ onComplete }: ChallengeProps) {
  const [count, setCount] = useState(2);
  const [notice, setNotice] = useState<Notice>();
  function change(amount: number) {
    setCount((value) => Math.max(0, Math.min(8, value + amount)));
    setNotice(undefined);
    onComplete(false);
  }
  return (
    <>
      <h3>Construye una suma</h3>
      <p>Tienes dos estrellas y encuentras otras dos. ¿Cuántas juntas?</p>
      <div className="preview-stars" role="img" aria-label={`${count} estrellas`}>
        {Array.from({ length: count }, (_, index) => (
          <img key={index} src={presentationSprite("estrella")} width={44} height={44} alt="" />
        ))}
      </div>
      <div className="preview-counter">
        <button
          type="button"
          onClick={() => change(-1)}
          disabled={!count}
          aria-label="Quitar una estrella"
        >
          <Minus size={18} aria-hidden="true" />
        </button>
        <output aria-live="polite">{count} estrellas</output>
        <button
          type="button"
          onClick={() => change(1)}
          disabled={count === 8}
          aria-label="Añadir una estrella"
        >
          <Plus size={18} aria-hidden="true" />
        </button>
      </div>
      <button
        type="button"
        className="preview-check"
        onClick={() => {
          const correct = count === 4;
          setNotice({
            correct,
            text: correct
              ? "¡Cuatro! Has construido la suma 2 + 2."
              : "Vuelve a juntar dos estrellas con otras dos. Puedes añadir o quitar.",
          });
          onComplete(correct);
        }}
      >
        Comprobar mi suma
      </button>
      <Feedback notice={notice} />
    </>
  );
}

function moveGuide(setPosition: Dispatch<SetStateAction<number>>, direction: number) {
  setPosition((position) => Math.max(0, Math.min(65, position + direction)));
}

export function WorldPreview() {
  const [sceneIndex, setSceneIndex] = useState(0);
  const [position, setPosition] = useState(16);
  const [playing, setPlaying] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [round, setRound] = useState(0);
  const scene = scenes[sceneIndex]!;

  return (
    <div className="world-preview">
      <div className="preview-scenes" role="group" aria-label="Escenario de la vista previa">
        {scenes.map((item, index) => (
          <button
            type="button"
            key={item.id}
            aria-pressed={sceneIndex === index}
            onClick={() => {
              setSceneIndex(index);
              setPosition(16);
              setPlaying(false);
              setCompleted(false);
              setRound((value) => value + 1);
            }}
          >
            {item.name}
          </button>
        ))}
      </div>
      <figure
        className="presentacion-paisaje preview-stage"
        data-scene={scene.id}
        tabIndex={0}
        aria-label={`${scene.trail}. Haz clic en el sendero o usa las flechas para mover a Peluqo.`}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            moveGuide(setPosition, event.key === "ArrowLeft" ? -8 : 8);
          }
        }}
        onPointerUp={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          setPosition(
            Math.max(0, Math.min(65, ((event.clientX - bounds.left) / bounds.width) * 100 - 16)),
          );
        }}
      >
        <img
          key={scene.image}
          className="presentacion-fondo"
          src={`${presentationArt}/${scene.image}.webp`}
          width={1680}
          height={746}
          alt={scene.alt}
          fetchPriority="high"
          draggable={false}
        />
        <div
          className="preview-guide"
          style={{ transform: `translateX(${position}%)` }}
          data-happy={completed}
        >
          <img
            src={presentationSprite(completed ? "peluqo-alegre" : "peluqo-alerta")}
            width={460}
            height={460}
            alt="Peluqo explora el sendero"
            draggable={false}
          />
        </div>
        {scene.id === "reserve" && (
          <img
            className="presentacion-rana"
            src={presentationSprite("rana")}
            width={460}
            height={460}
            alt=""
            draggable={false}
          />
        )}
        <figcaption>
          <Compass size={16} aria-hidden="true" /> {scene.trail}
        </figcaption>
      </figure>
      <div className="preview-toolbar">
        <div className="preview-movement" role="group" aria-label="Mover a Peluqo">
          <button
            type="button"
            onClick={() => moveGuide(setPosition, -8)}
            disabled={position === 0}
            aria-label="Mover a Peluqo a la izquierda"
          >
            <ArrowLeft size={19} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => moveGuide(setPosition, 8)}
            disabled={position === 65}
            aria-label="Mover a Peluqo a la derecha"
          >
            <ArrowRight size={19} aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          className="preview-play"
          aria-expanded={playing}
          aria-controls="preview-challenge"
          onClick={() => {
            setPlaying((value) => !value);
            setCompleted(false);
            setRound((value) => value + 1);
          }}
        >
          {playing ? (
            <>
              Cerrar reto <X size={17} aria-hidden="true" />
            </>
          ) : (
            <>
              Prueba un reto <ArrowUpRight size={17} aria-hidden="true" />
            </>
          )}
        </button>
      </div>
      <p className="preview-caption">Vista previa · Toca el sendero y mueve a Peluqo.</p>
      {playing && (
        <section
          className="preview-challenge"
          id="preview-challenge"
          aria-label={`Reto de ${scene.name}`}
        >
          {scene.id === "reserve" ? (
            <AnimalChallenge key={round} onComplete={setCompleted} />
          ) : scene.id === "space" ? (
            <SequenceChallenge key={round} onComplete={setCompleted} />
          ) : (
            <CountingChallenge key={round} onComplete={setCompleted} />
          )}
          {completed && (
            <button
              type="button"
              className="preview-replay"
              onClick={() => {
                setRound((value) => value + 1);
                setCompleted(false);
              }}
            >
              <RotateCcw size={15} aria-hidden="true" /> Volver a jugar
            </button>
          )}
        </section>
      )}
    </div>
  );
}
