import { useEffect, useRef, useState, type ComponentType } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BatteryCharging,
  CircleHelp,
  Lightbulb,
  Link2,
  Minus,
  Plus,
  Power,
  RotateCcw,
  Volume2,
  X,
} from "lucide-react";
import { puzzleSlots, type PublicActivity } from "@/lib/education/schema";
import { artUrl, fieldArt, guideArt } from "./fieldArt";
import "./games.css";

export type Answer = Record<string, string>;
export type GameInteraction =
  "select" | "move" | "connect" | "reveal" | "pair" | "reset" | "experiment";
type Item = PublicActivity["pieces"][number] | PublicActivity["choices"][number];
type Illustration = ComponentType<{ asset?: string; decorative?: boolean; schematic?: boolean }>;
type BoardProps = {
  activity: PublicActivity;
  answer: Answer;
  disabled: boolean;
  change: (answer: Answer) => void;
  Art: Illustration;
  onInteraction?: ((kind: GameInteraction) => void) | undefined;
};

function mix<T extends { id: string }>(items: readonly T[], salt: string) {
  function rank(id: string) {
    let value = 2166136261;
    for (const character of salt + id) value = Math.imul(value ^ character.charCodeAt(0), 16777619);
    return value >>> 0;
  }
  return [...items].sort((a, b) => rank(a.id) - rank(b.id));
}

function chooseUnique(answer: Answer, from: string, to: string) {
  const pairs = Object.entries(answer).filter(
    ([id, destination]) => id !== from && destination !== to,
  );
  return Object.fromEntries([...pairs, [from, to]]);
}

function Content({ item, Art }: { item: Item; Art: Illustration }) {
  return (
    <>
      {item.asset && <Art asset={item.asset} decorative />}
      <span>{item.label}</span>
    </>
  );
}

type Connection = { id: string; path: string };

export function MatchingBoard({
  activity,
  answer,
  disabled,
  change,
  Art,
  onInteraction,
}: BoardProps) {
  const [selected, select] = useState<string | null>(null);
  const [lines, setLines] = useState<Connection[]>([]);
  const board = useRef<HTMLDivElement>(null);
  const drawing = useRef<{ id: string; x: number; y: number; moved: boolean } | null>(null);
  const skipClick = useRef(false);
  const [pointerLine, setPointerLine] = useState("");
  const pieces = mix(activity.pieces, "pistas");
  const choices = mix(activity.choices, "parejas");
  const selectedPiece = pieces.find((item) => item.id === selected);

  useEffect(() => {
    const root = board.current;
    if (!root) return;
    const from = Array.from(root.querySelectorAll<HTMLElement>("[data-connection-from]"));
    const to = Array.from(root.querySelectorAll<HTMLElement>("[data-connection-to]"));
    function draw() {
      const origin = root!.getBoundingClientRect();
      setLines(
        Object.entries(answer).flatMap(([id, destination]) => {
          const start = from
            .find((node) => node.dataset["connectionFrom"] === id)
            ?.getBoundingClientRect();
          const end = to
            .find((node) => node.dataset["connectionTo"] === destination)
            ?.getBoundingClientRect();
          if (!start || !end) return [];
          const x1 = Math.round(start.right - origin.left);
          const y1 = Math.round(start.top + start.height / 2 - origin.top);
          const x2 = Math.round(end.left - origin.left);
          const y2 = Math.round(end.top + end.height / 2 - origin.top);
          const middle = Math.round((x1 + x2) / 2);
          return [{ id, path: `M${x1} ${y1} C${middle} ${y1},${middle} ${y2},${x2} ${y2}` }];
        }),
      );
    }
    draw();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(draw);
    for (const element of [root, ...from, ...to]) observer.observe(element);
    return () => observer.disconnect();
  }, [answer]);

  function connect(from: string, to: string) {
    if (disabled || !activity.pieces.some((p) => p.id === from)) return;
    change(chooseUnique(answer, from, to));
    onInteraction?.("connect");
    select(null);
    setPointerLine("");
  }

  return (
    <div className="edu-mechanic edu-connect-adventure">
      <p className="edu-help">
        Dibuja un camino desde cada tarjeta hasta su pareja. También puedes tocar las dos.
      </p>
      <div
        className="edu-connect-board"
        ref={board}
        data-drawing={!!pointerLine}
        onPointerMove={(event) => {
          const active = drawing.current;
          if (!active || disabled || !board.current) return;
          if (Math.hypot(event.clientX - active.x, event.clientY - active.y) < 7 && !active.moved)
            return;
          active.moved = true;
          const bounds = board.current.getBoundingClientRect();
          const source = board.current
            .querySelector<HTMLElement>('[data-connection-from="' + CSS.escape(active.id) + '"]')
            ?.getBoundingClientRect();
          if (!source) return;
          const x = source.right - bounds.left;
          const y = source.top + source.height / 2 - bounds.top;
          const endX = event.clientX - bounds.left;
          const endY = event.clientY - bounds.top;
          setPointerLine(
            "M" +
              x +
              " " +
              y +
              " C" +
              (x + 65) +
              " " +
              y +
              "," +
              (endX - 65) +
              " " +
              endY +
              "," +
              endX +
              " " +
              endY,
          );
        }}
        onPointerUp={(event) => {
          const active = drawing.current;
          drawing.current = null;
          setPointerLine("");
          if (!active?.moved) return;
          skipClick.current = true;
          const destination = document
            .elementFromPoint(event.clientX, event.clientY)
            ?.closest<HTMLElement>("[data-connection-to]");
          if (destination?.dataset["connectionTo"])
            connect(active.id, destination.dataset["connectionTo"]);
        }}
        onPointerCancel={() => {
          drawing.current = null;
          setPointerLine("");
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            select(null);
            setPointerLine("");
            drawing.current = null;
          }
        }}
      >
        <svg className="edu-connect-lines" aria-hidden="true">
          {lines.map((line) => (
            <path key={line.id + line.path} d={line.path} pathLength="1" />
          ))}
          {pointerLine && <path className="edu-connect-preview" d={pointerLine} />}
        </svg>
        <div className="edu-connect-column" aria-label="Tarjetas">
          {pieces.map((piece) => {
            const target = choices.find((c) => c.id === answer[piece.id]);
            return (
              <button
                type="button"
                className="edu-play-tile"
                key={piece.id}
                data-connection-from={piece.id}
                aria-pressed={selected === piece.id}
                aria-label={target ? `${piece.label}, unida a ${target.label}` : piece.label}
                disabled={disabled}
                draggable={false}
                onPointerDown={(event) => {
                  if (disabled || event.button !== 0) return;
                  drawing.current = {
                    id: piece.id,
                    x: event.clientX,
                    y: event.clientY,
                    moved: false,
                  };
                  event.currentTarget.setPointerCapture?.(event.pointerId);
                  select(piece.id);
                }}
                onDragStart={(e) => {
                  e.preventDefault();
                }}
                onClick={() => {
                  if (skipClick.current) {
                    skipClick.current = false;
                    return;
                  }
                  select(piece.id);
                  onInteraction?.("select");
                }}
              >
                <Content item={piece} Art={Art} />
              </button>
            );
          })}
        </div>
        <div className="edu-connect-column" aria-label="Parejas">
          {choices.map((choice) => (
            <button
              type="button"
              key={choice.id}
              className="edu-play-tile"
              data-connection-to={choice.id}
              disabled={disabled}
              aria-disabled={disabled || !selected}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                connect(e.dataTransfer.getData("text/plain"), choice.id);
              }}
              onClick={() => {
                if (selected) connect(selected, choice.id);
              }}
            >
              <Content item={choice} Art={Art} />
            </button>
          ))}
        </div>
      </div>
      {selectedPiece && (
        <AudioLine
          key={selectedPiece.id}
          text={selectedPiece.label}
          sample={selectedPiece.sample}
          disabled={disabled}
        />
      )}
      <p className="edu-board-status" aria-live="polite">
        <Link2 size={17} /> {Object.keys(answer).length} de {pieces.length} conexiones
      </p>
      <div className="edu-action-progress" aria-hidden="true">
        {pieces.map((piece) => (
          <span key={piece.id} data-filled={!!answer[piece.id]} />
        ))}
      </div>
    </div>
  );
}

export function SequenceBoard({
  activity,
  answer,
  disabled,
  change,
  Art,
  onInteraction,
}: BoardProps) {
  const pieces = mix(activity.pieces, "secuencia");
  const order = activity.choices.flatMap((slot) => {
    const piece = pieces.find((p) => answer[p.id] === slot.id);
    return piece ? [piece] : [];
  });
  const remaining = pieces.filter((piece) => !answer[piece.id]);

  function rearrange(items: typeof order) {
    change(
      Object.fromEntries(items.map((piece, index) => [piece.id, activity.choices[index]!.id])),
    );
    onInteraction?.("move");
  }

  function move(index: number, offset: number) {
    const next = [...order];
    [next[index], next[index + offset]] = [next[index + offset]!, next[index]!];
    rearrange(next);
  }

  return (
    <div className="edu-mechanic">
      <p className="edu-help">
        Añade las tarjetas en orden. Usa las flechas para cambiar una posición.
      </p>
      <div className="edu-play-bank" aria-label="Tarjetas disponibles">
        {remaining.map((item) => (
          <button
            type="button"
            className="edu-play-tile"
            key={item.id}
            disabled={disabled}
            onClick={() => rearrange([...order, item])}
          >
            <Content item={item} Art={Art} />
            <Plus size={17} />
          </button>
        ))}
        {!remaining.length && <p className="edu-help">Todas las tarjetas están en la secuencia.</p>}
      </div>
      <ol className="edu-sequence" aria-label="Mi secuencia">
        {activity.choices.map((slot, index) => {
          const item = order[index];
          return (
            <li key={slot.id}>
              <span className="edu-sequence-step" aria-hidden="true">
                {index + 1}
              </span>
              {item ? (
                <>
                  <strong>
                    <Content item={item} Art={Art} />
                  </strong>
                  <div className="edu-play-controls">
                    <button
                      type="button"
                      aria-label={`Subir ${item.label}`}
                      disabled={disabled || index === 0}
                      onClick={() => move(index, -1)}
                    >
                      <ArrowUp size={18} />
                    </button>
                    <button
                      type="button"
                      aria-label={`Bajar ${item.label}`}
                      disabled={disabled || index === order.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDown size={18} />
                    </button>
                    <button
                      type="button"
                      aria-label={`Quitar ${item.label}`}
                      disabled={disabled}
                      onClick={() => rearrange(order.filter((p) => p !== item))}
                    >
                      <X size={18} />
                    </button>
                  </div>
                </>
              ) : (
                <span className="edu-help">Por ordenar</span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function AudioLine({
  text,
  disabled,
  sample,
}: {
  text: string;
  disabled: boolean;
  sample?: Item["sample"];
}) {
  const [transcript, setTranscript] = useState(false);
  const [playing, setPlaying] = useState(false);
  const played = useRef<SpeechSynthesisUtterance>(null);
  const recording = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    const clip = recording.current;
    if (!clip) window.speechSynthesis?.getVoices();
    return () => {
      clip?.pause();
      if (played.current) {
        played.current.onend = null;
        played.current.onerror = null;
        window.speechSynthesis?.cancel();
        played.current = null;
      }
    };
  }, []);
  function listen() {
    const clip = recording.current;
    if (clip) {
      if (!clip.paused) {
        clip.pause();
        return;
      }
      if (clip.currentTime > 0) clip.currentTime = 0;
      void clip.play().catch(() => setTranscript(true));
      return;
    }
    const synth = window.speechSynthesis;
    const voice = synth
      ?.getVoices()
      .find((option) => option.localService && /^es(?:[-_]|$)/i.test(option.lang));
    if (!synth || !voice) {
      setTranscript(true);
      return;
    }
    synth.cancel();
    const spoken = new SpeechSynthesisUtterance(text);
    spoken.voice = voice;
    spoken.lang = voice.lang;
    spoken.rate = 0.88;
    spoken.onend = () => {
      if (played.current === spoken) played.current = null;
    };
    spoken.onerror = (event) => {
      if (played.current !== spoken) return;
      played.current = null;
      if (event.error !== "interrupted" && event.error !== "canceled") setTranscript(true);
    };
    played.current = spoken;
    synth.speak(spoken);
  }
  return (
    <div className="edu-audio-line">
      {sample && (
        <audio
          ref={recording}
          src={`/educacion/audio/${sample}.mp3`}
          preload="none"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(event) => {
            if (event.currentTarget.currentTime >= 8) event.currentTarget.pause();
          }}
        />
      )}
      <button type="button" className="edu-button" disabled={disabled} onClick={listen}>
        <Volume2 size={18} /> {playing ? "Detener audio" : "Escuchar"}
      </button>
      <button
        type="button"
        className="edu-button"
        disabled={disabled}
        aria-expanded={transcript}
        onClick={() => setTranscript(!transcript)}
      >
        {transcript ? "Ocultar texto" : "Leer texto"}
      </button>
      {transcript && <p role="status">{text}</p>}
      {sample && (
        <a
          className="edu-help"
          href="/educacion/audio/creditos.txt"
          target="_blank"
          rel="noreferrer"
        >
          Créditos del audio
        </a>
      )}
    </div>
  );
}

export function MemoryBoard({
  activity,
  answer,
  disabled,
  change,
  Art,
  onInteraction,
}: BoardProps) {
  const [left, selectLeft] = useState<string | null>(null);
  const [right, selectRight] = useState<string | null>(null);
  const pieces = mix(activity.pieces, "memoria-pista");
  const choices = mix(activity.choices, "memoria-pareja");
  const revealedLeft = pieces.find((p) => p.id === left);
  const revealedRight = choices.find((c) => c.id === right);
  const pairs = pieces.filter((p) => answer[p.id]);
  const numbers = new Map(pairs.map((p, i) => [p.id, i + 1]));
  const reverse = new Map(Object.entries(answer).map(([id, match]) => [match, id]));

  function flip(item: Item, side: "left" | "right") {
    if (side === "left") selectLeft(left === item.id ? null : item.id);
    else selectRight(right === item.id ? null : item.id);
    onInteraction?.("reveal");
  }

  function deck(items: Item[], side: "left" | "right") {
    return (
      <div className="edu-memory-deck" aria-label={side === "left" ? "Pistas" : "Parejas"}>
        <h3>{side === "left" ? "Pistas" : "Parejas"}</h3>
        {items.map((item, index) => {
          const open = item.id === (side === "left" ? left : right);
          const number = numbers.get(side === "left" ? item.id : (reverse.get(item.id) ?? ""));
          const label = `${side === "left" ? "Pista" : "Pareja"} ${index + 1}`;
          return (
            <button
              type="button"
              key={item.id}
              disabled={disabled}
              aria-label={
                open
                  ? `${label}, ${item.label}`
                  : number
                    ? `${label}, pareja guardada ${number}. Volver a abrir`
                    : `Girar ${label.toLowerCase()}`
              }
              aria-pressed={open}
              className="edu-play-tile edu-memory-tile"
              data-paired={!!number}
              data-revealed={open}
              onClick={() => flip(item, side)}
            >
              {open ? (
                <Content item={item} Art={Art} />
              ) : number ? (
                <>
                  <Link2 size={19} /> Par {number}
                </>
              ) : (
                <span className="edu-memory-back">
                  <img src={artUrl(guideArt.ready)} alt="" draggable={false} />
                  <span>{index + 1}</span>
                </span>
              )}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="edu-mechanic edu-memory-adventure">
      <p className="edu-help">
        Descubre una carta de cada lado. Recuerda dónde están y guarda las que creas que forman
        pareja.
      </p>
      <div className="edu-memory-glance">
        <span>
          <CircleHelp size={17} /> {Number(!!left) + Number(!!right)} de 2 cartas abiertas
        </span>
        <span>{pairs.length} parejas en tu cuaderno</span>
      </div>
      <div className="edu-memory-board">
        {deck(pieces, "left")}
        {deck(choices, "right")}
      </div>
      <div className="edu-play-controls">
        <button
          type="button"
          className="edu-button"
          disabled={disabled || !left || !right}
          onClick={() => {
            if (!left || !right) return;
            change(chooseUnique(answer, left, right));
            onInteraction?.("pair");
            selectLeft(null);
            selectRight(null);
          }}
        >
          <Link2 size={18} /> Guardar pareja
        </button>
        <p className="edu-board-status" aria-live="polite">
          {pairs.length} de {pieces.length} parejas guardadas
        </p>
      </div>
      {!!pairs.length && (
        <details className="edu-memory-notes">
          <summary>Revisar mis parejas</summary>
          <ul>
            {pairs.map((piece) => (
              <li key={piece.id}>
                <strong>{piece.label}</strong>
                <Link2 size={15} aria-hidden="true" />
                <span>{choices.find((choice) => choice.id === answer[piece.id])?.label}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {[revealedLeft, revealedRight].map(
        (item, side) =>
          item && (
            <AudioLine
              key={`${side}:${item.id}`}
              disabled={disabled}
              text={item.label}
              sample={item.sample}
            />
          ),
      )}
    </div>
  );
}

export function ListeningBoard({ activity, answer, disabled, change, Art }: BoardProps) {
  const [index, setIndex] = useState(0);
  const piece = activity.pieces[index];
  if (!piece) return null;
  return (
    <div className="edu-mechanic">
      <p className="edu-help">Escucha o lee la pista y elige con qué opción se relaciona.</p>
      <div className="edu-listening-panel">
        <div className="edu-listening-icon" aria-hidden="true">
          <Volume2 size={34} />
        </div>
        <strong>
          Audio {index + 1} de {activity.pieces.length}
        </strong>
        <AudioLine key={piece.id} text={piece.label} sample={piece.sample} disabled={disabled} />
      </div>
      <Choices
        activity={activity}
        active={answer[piece.id]}
        disabled={disabled}
        choose={(value) => change({ ...answer, [piece.id]: value })}
        Art={Art}
      />
      <Pager index={index} total={activity.pieces.length} move={setIndex} disabled={disabled} />
    </div>
  );
}

function Choices({
  activity,
  active,
  disabled,
  choose,
  Art,
}: {
  activity: PublicActivity;
  active: string | undefined;
  disabled: boolean;
  choose: (value: string) => void;
  Art: Illustration;
}) {
  return (
    <div className="edu-play-bank" aria-label="Opciones">
      {activity.choices.map((choice, i) => (
        <button
          type="button"
          className="edu-play-tile"
          key={choice.id}
          disabled={disabled}
          aria-pressed={active === choice.id}
          onClick={() => choose(choice.id)}
        >
          {activity.type === "anatomy" && <span className="edu-sequence-step">{i + 1}</span>}
          <Content item={choice} Art={Art} />
        </button>
      ))}
    </div>
  );
}

function Pager({
  index,
  total,
  move,
  disabled,
}: {
  index: number;
  total: number;
  move: (index: number) => void;
  disabled: boolean;
}) {
  return (
    <div className="edu-play-controls edu-board-pager">
      <button
        type="button"
        className="edu-button"
        disabled={disabled || index === 0}
        onClick={() => move(index - 1)}
      >
        <ArrowLeft size={18} /> Anterior
      </button>
      <button
        type="button"
        className="edu-button"
        disabled={disabled || index === total - 1}
        onClick={() => move(index + 1)}
      >
        Siguiente <ArrowRight size={18} />
      </button>
    </div>
  );
}

export function GuidedBoard({ activity, answer, disabled, change, Art }: BoardProps) {
  const [index, setIndex] = useState(0);
  const piece = activity.pieces[index];
  if (!piece) return null;
  const placed = activity.pieces.filter((item) => answer[item.id]).length;
  return (
    <div className="edu-mechanic">
      <p className="edu-help">Elige un destino para la tarjeta. Después, pasa a la siguiente.</p>
      {activity.type === "anatomy" && (
        <div className="edu-anatomy">
          <div className="edu-anatomy-figure" data-figure={activity.asset}>
            <Art asset={activity.asset} schematic />
            {activity.choices.map((choice, i) => (
              <button
                type="button"
                key={choice.id}
                className="edu-anatomy-marker"
                style={{ left: `${choice.x}%`, top: `${choice.y}%` }}
                aria-label={`Zona ${i + 1}. ${choice.label}`}
                aria-pressed={answer[piece.id] === choice.id}
                data-ready="true"
                disabled={disabled}
                onClick={() => change({ ...answer, [piece.id]: choice.id })}
              >
                {i + 1}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="edu-guided-panel" key={piece.id}>
        <p className="edu-board-status">
          Tarjeta {index + 1} de {activity.pieces.length}
        </p>
        <div className="edu-guided-piece">
          <Content item={piece} Art={Art} />
        </div>
      </div>
      <Choices
        activity={activity}
        active={answer[piece.id]}
        disabled={disabled}
        choose={(value) => change({ ...answer, [piece.id]: value })}
        Art={Art}
      />
      <div className="edu-board-status" aria-live="polite">
        {placed} de {activity.pieces.length} tarjetas colocadas
      </div>
      <Pager index={index} total={activity.pieces.length} move={setIndex} disabled={disabled} />
    </div>
  );
}

const pictureDescriptions = {
  reserve:
    "Un camino cruza el paisaje. Tras él, el bosque se abre hacia el río y las montañas. Los helechos crecen a la izquierda, junto a los troncos, y las rocas están a la derecha.",
  space:
    "En lo alto, un árbol enmarca el cielo estrellado y la luna brilla sobre el observatorio. El sendero pasa bajo el árbol y bordea los riscos a su derecha.",
  workshop:
    "Un suelo de piedra recorre el taller. A la izquierda se ven una estantería, vigas y macetas. A la derecha, un gran ventanal mira al bosque sobre la mesa de trabajo.",
} as const;

export function PuzzleBoard({ activity, answer, disabled, change, onInteraction }: BoardProps) {
  const [selected, select] = useState<string | null>(null);
  const [moves, setMoves] = useState(0);
  const moving = useRef<{ piece: string; x: number; y: number } | null>(null);
  const skipClick = useRef(false);
  const slots = puzzleSlots.flatMap(
    (id) => activity.choices.find((choice) => choice.id === id) ?? [],
  );
  const scrambled = mix(activity.pieces, "mosaico-inicial");
  const layout = Object.keys(answer).length
    ? answer
    : Object.fromEntries(scrambled.map((piece, index) => [piece.id, slots[index]!.id]));
  function place(piece: string, slot: string) {
    if (disabled || !activity.pieces.some((item) => item.id === piece)) return;
    const previous = layout[piece];
    if (previous === slot) {
      select(null);
      return;
    }
    const other = activity.pieces.find((item) => layout[item.id] === slot);
    change({ ...layout, [piece]: slot, ...(other && previous ? { [other.id]: previous } : {}) });
    setMoves((count) => count + 1);
    onInteraction?.("move");
    select(null);
  }
  function image(piece: PublicActivity["pieces"][number]) {
    return (
      <img
        src={artUrl(`puzles/${activity.puzzlePicture}-${piece.tile}`)}
        alt=""
        draggable={false}
      />
    );
  }
  return (
    <div className="edu-mechanic edu-puzzle-adventure">
      <p className="edu-help">
        El paisaje se ha mezclado. Toca dos fragmentos para intercambiarlos o arrastra uno sobre
        otro.
      </p>
      <div
        className="edu-puzzle-board"
        aria-label="Mosaico"
        onPointerUp={(event) => {
          const active = moving.current;
          moving.current = null;
          if (!active || Math.hypot(event.clientX - active.x, event.clientY - active.y) < 8) return;
          skipClick.current = true;
          const destination = document
            .elementFromPoint(event.clientX, event.clientY)
            ?.closest<HTMLElement>("[data-puzzle-slot]");
          if (destination?.dataset["puzzleSlot"])
            place(active.piece, destination.dataset["puzzleSlot"]);
        }}
        onPointerCancel={() => {
          moving.current = null;
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") select(null);
        }}
      >
        {slots.map((slot) => {
          const piece = activity.pieces.find((item) => layout[item.id] === slot.id);
          return (
            <button
              type="button"
              key={slot.id}
              className="edu-puzzle-slot"
              disabled={disabled}
              data-puzzle-slot={slot.id}
              aria-pressed={!!piece && piece.id === selected}
              aria-label={piece ? `${slot.label}, ${piece.label}` : slot.label}
              onDragOver={(e) => e.preventDefault()}
              onPointerDown={(event) => {
                if (disabled || !piece || event.button !== 0) return;
                moving.current = { piece: piece.id, x: event.clientX, y: event.clientY };
                event.currentTarget.setPointerCapture?.(event.pointerId);
              }}
              onDrop={(e) => {
                e.preventDefault();
                place(e.dataTransfer.getData("text/plain"), slot.id);
              }}
              onClick={() => {
                if (skipClick.current) {
                  skipClick.current = false;
                  return;
                }
                if (selected) place(selected, slot.id);
                else if (piece) {
                  select(piece.id);
                  onInteraction?.("select");
                }
              }}
            >
              {piece ? (
                <span className="edu-puzzle-fragment" key={piece.id}>
                  {image(piece)}
                </span>
              ) : (
                <span>{slot.label}</span>
              )}
              <span className="edu-puzzle-position" aria-hidden="true">
                {slots.indexOf(slot) + 1}
              </span>
            </button>
          );
        })}
      </div>
      <details className="edu-puzzle-access">
        <summary>Seleccionar un fragmento por su nombre</summary>
        <div className="edu-puzzle-bank" aria-label="Fragmentos">
          {mix(activity.pieces, "puzle").map((piece) => (
            <button
              type="button"
              className="edu-play-tile"
              key={piece.id}
              disabled={disabled}
              aria-pressed={selected === piece.id}
              draggable={!disabled}
              onDragStart={(e) => {
                e.dataTransfer.setData("text/plain", piece.id);
                select(piece.id);
              }}
              onClick={() => {
                select(selected === piece.id ? null : piece.id);
                onInteraction?.("select");
              }}
            >
              {image(piece)}
              <span>{piece.label}</span>
            </button>
          ))}
        </div>
      </details>
      <p className="edu-board-status" aria-live="polite">
        {selected
          ? "Elige con qué fragmento intercambiarlo"
          : moves + (moves === 1 ? " intercambio realizado" : " intercambios realizados")}
      </p>
      {activity.puzzlePicture && (
        <details className="edu-puzzle-reference">
          <summary>Consultar la ilustración de referencia</summary>
          <img
            src={artUrl(fieldArt[activity.puzzlePicture].background)}
            alt={pictureDescriptions[activity.puzzlePicture]}
            loading="lazy"
          />
        </details>
      )}
    </div>
  );
}

export function ManipulativeBoard({
  activity,
  answer,
  disabled,
  change,
  onInteraction,
}: BoardProps) {
  const counts = activity.pieces.map((piece) => Number(answer[piece.id] ?? 0));
  const left = (activity.stock ?? 0) - counts.reduce((sum, count) => sum + count, 0);
  function move(id: string, delta: number) {
    const count = Number(answer[id] ?? 0) + delta;
    if (disabled || count < 0 || (delta > 0 && left <= 0)) return;
    change(
      Object.fromEntries(
        activity.pieces.map((p) => [p.id, p.id === id ? String(count) : (answer[p.id] ?? "0")]),
      ),
    );
    onInteraction?.("move");
  }
  return (
    <div className="edu-mechanic">
      <div
        className="edu-token-tray"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const id = e.dataTransfer.getData("application/x-peluqo-bin");
          if (activity.pieces.some((p) => p.id === id)) move(id, -1);
        }}
      >
        <strong aria-live="polite">
          {left} {left === 1 ? "ficha disponible" : "fichas disponibles"}
        </strong>
        <div className="edu-token-grid" aria-hidden="true">
          {Array.from({ length: left }, (_, i) => (
            <span
              key={i}
              className="edu-token"
              draggable={!disabled}
              onDragStart={(e) => {
                e.dataTransfer.setData("application/x-peluqo-token", "1");
              }}
            />
          ))}
        </div>
      </div>
      <p className="edu-help">
        Reparte las fichas con los botones + y − o arrástralas entre la bandeja y cada grupo.
      </p>
      <div className="edu-token-bins">
        {activity.pieces.map((piece, index) => {
          const count = counts[index] ?? 0;
          return (
            <section
              className="edu-token-bin"
              key={piece.id}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.getData("application/x-peluqo-token") === "1") move(piece.id, 1);
              }}
            >
              <h3>{piece.label}</h3>
              <div className="edu-token-grid" aria-hidden="true">
                {Array.from({ length: count }, (_, i) => (
                  <span
                    key={i}
                    className="edu-token"
                    draggable={!disabled}
                    onDragStart={(e) => {
                      e.dataTransfer.setData("application/x-peluqo-bin", piece.id);
                    }}
                  />
                ))}
              </div>
              <div className="edu-play-controls">
                <button
                  type="button"
                  disabled={disabled || count === 0}
                  aria-label={`Quitar una ficha de ${piece.label}`}
                  onClick={() => move(piece.id, -1)}
                >
                  <Minus size={18} />
                </button>
                <span aria-live="polite">{count}</span>
                <button
                  type="button"
                  disabled={disabled || left === 0}
                  aria-label={`Añadir una ficha a ${piece.label}`}
                  onClick={() => move(piece.id, 1)}
                >
                  <Plus size={18} />
                </button>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

export function CircuitBoard({ answer, disabled, change, onInteraction }: BoardProps) {
  const battery = answer["battery"] === "on";
  const closed = answer["switch"] === "on";
  const lit = battery && closed;
  const labels = lit ? "La lámpara está encendida" : "La lámpara está apagada";
  const [observations, setObservations] = useState<{ battery: boolean; closed: boolean }[]>([]);
  function experiment(nextBattery: boolean, nextClosed: boolean) {
    change({ battery: nextBattery ? "on" : "off", switch: nextClosed ? "on" : "off" });
    setObservations((previous) => [
      ...previous.filter((item) => item.battery !== nextBattery || item.closed !== nextClosed),
      { battery: nextBattery, closed: nextClosed },
    ]);
    onInteraction?.("experiment");
  }
  return (
    <div className="edu-mechanic edu-lab-adventure">
      <p className="edu-help">
        Conecta la pila y prueba el interruptor. Observa cuándo puede circular la corriente.
      </p>
      <div className="edu-circuit" data-lit={lit} data-battery={battery} data-closed={closed}>
        <div className="edu-circuit-top">
          <span>Banco de electricidad</span>
          <span>{lit ? "Corriente en circulación" : "Sin circulación"}</span>
        </div>
        <svg
          className="edu-circuit-wires"
          viewBox="0 0 340 150"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path d="M40 36h96m68 0h96v80H40V36" />
          <path d={closed ? "M136 36h68" : "M136 36l61-24"} />
          <circle cx="136" cy="36" r="5" />
          <circle cx="204" cy="36" r="5" />
          <path className="edu-current-flow" d="M40 36h260v80H40V36" pathLength="100" />
        </svg>
        <span className="edu-circuit-lamp">
          <Lightbulb size={48} className="edu-circuit-bulb" aria-hidden="true" />
        </span>
        <button
          type="button"
          className="edu-play-tile edu-circuit-battery"
          disabled={disabled}
          aria-pressed={battery}
          onClick={() => experiment(!battery, closed)}
        >
          <BatteryCharging size={23} /> {battery ? "Pila conectada" : "Conectar pila"}
        </button>
        <button
          type="button"
          className="edu-play-tile edu-circuit-switch"
          disabled={disabled}
          aria-pressed={closed}
          onClick={() => experiment(battery, !closed)}
        >
          <Power size={23} /> {closed ? "Interruptor cerrado" : "Cerrar interruptor"}
        </button>
        <p className="edu-circuit-observation" aria-live="polite">
          {labels}
        </p>
      </div>
      <div className="edu-play-controls">
        <button
          type="button"
          className="edu-button"
          disabled={disabled || (!battery && !closed)}
          onClick={() => {
            experiment(false, false);
            onInteraction?.("reset");
          }}
        >
          <RotateCcw size={17} /> Reiniciar
        </button>
        <p className="edu-help">Prueba también a abrirlo cuando la lámpara ya esté encendida.</p>
      </div>
      {!!observations.length && (
        <div className="edu-experiment-notes" aria-label="Mis observaciones">
          <h3>Tu cuaderno del laboratorio</h3>
          <div className="edu-experiment-head">
            <span>Pila</span>
            <span>Interruptor</span>
            <span>Lámpara</span>
          </div>
          {observations.map((item) => (
            <div className="edu-experiment-row" key={String(item.battery) + String(item.closed)}>
              <span>{item.battery ? "Conectada" : "Desconectada"}</span>
              <span>{item.closed ? "Cerrado" : "Abierto"}</span>
              <span>
                <Lightbulb size={14} aria-hidden="true" />{" "}
                {item.battery && item.closed ? "Encendida" : "Apagada"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
