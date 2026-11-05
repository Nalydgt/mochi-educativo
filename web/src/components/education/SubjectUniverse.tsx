import { useEffect, useRef, type CSSProperties } from "react";
import { ArrowDown, Compass } from "lucide-react";
import { subjects, type Companion } from "@/lib/education/schema";
import { artUrl } from "./fieldArt";
import { FieldGuide } from "./FieldGuide";

export type SubjectZone = { id: string; name: string; count: number };

const landmarks: Record<
  string,
  { sprite: string; landscape: string; x: number; y: number; greeting: string }
> = {
  ciencias: {
    sprite: "rana",
    landscape: "reserva",
    x: 17,
    y: 47,
    greeting: "En el río hay mucho por descubrir.",
  },
  matematicas: {
    sprite: "puesto-cuaderno",
    landscape: "taller",
    x: 43,
    y: 72,
    greeting: "Vamos a construir, contar y probar ideas.",
  },
  lengua: {
    sprite: "gato",
    landscape: "taller",
    x: 70,
    y: 48,
    greeting: "Las palabras también esconden aventuras.",
  },
  historia: {
    sprite: "puesto-mirador",
    landscape: "observatorio",
    x: 87,
    y: 73,
    greeting: "Cada época tiene una historia que contar.",
  },
  geografia: {
    sprite: "tortuga",
    landscape: "reserva",
    x: 63,
    y: 20,
    greeting: "Exploramos lugares y aprendemos a orientarnos.",
  },
  otros: {
    sprite: "puesto-lupa",
    landscape: "taller",
    x: 34,
    y: 19,
    greeting: "Aquí comienzan los descubrimientos nuevos.",
  },
  sin_clasificar: {
    sprite: "puesto-lupa",
    landscape: "taller",
    x: 89,
    y: 21,
    greeting: "También hay aventuras por organizar.",
  },
};

export function SubjectUniverse({
  zones,
  selected,
  onSelect,
  pet,
}: {
  zones: SubjectZone[];
  selected: string;
  onSelect: (subject: string) => void;
  pet?: Companion | undefined;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const frame = useRef<number | undefined>(undefined);
  const target = selected ? landmarks[selected] : undefined;
  const scenery = target?.landscape ?? "reserva";
  const selectedZone = zones.find((zone) => zone.id === selected);
  useEffect(
    () => () => {
      if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    },
    [],
  );

  return (
    <div className="subject-universe">
      <div
        className="universe-scene"
        ref={stage}
        data-destination={selected || "all"}
        data-portals={zones.length}
        onPointerMove={(event) => {
          if (
            event.pointerType === "touch" ||
            matchMedia("(prefers-reduced-motion: reduce)").matches
          )
            return;
          const bounds = event.currentTarget.getBoundingClientRect();
          const x = (event.clientX - bounds.left) / bounds.width - 0.5;
          const y = (event.clientY - bounds.top) / bounds.height - 0.5;
          if (frame.current !== undefined) cancelAnimationFrame(frame.current);
          frame.current = requestAnimationFrame(() => {
            stage.current?.style.setProperty("--universe-x", `${x * 14}px`);
            stage.current?.style.setProperty("--universe-y", `${y * 9}px`);
          });
        }}
        onPointerLeave={() => {
          if (frame.current !== undefined) cancelAnimationFrame(frame.current);
          stage.current?.style.setProperty("--universe-x", "0px");
          stage.current?.style.setProperty("--universe-y", "0px");
        }}
      >
        <img
          className="universe-backdrop"
          key={scenery}
          src={artUrl(scenery)}
          alt=""
          width={1680}
          height={746}
          draggable={false}
        />
        <p className="universe-invitation">
          <Compass size={17} aria-hidden="true" /> Toca un portal y elige tu aventura
        </p>
        <div className="universe-portals" role="group" aria-label="Portales de las asignaturas">
          {zones.map((zone) => {
            const landmark = landmarks[zone.id] ?? landmarks["otros"]!;
            return (
              <button
                type="button"
                className="universe-portal"
                key={zone.id}
                data-subject={zone.id}
                aria-pressed={selected === zone.id}
                aria-controls="universe-adventures"
                style={
                  {
                    "--portal-x": `${landmark.x}%`,
                    "--portal-y": `${landmark.y}%`,
                  } as CSSProperties
                }
                onClick={() => onSelect(zone.id)}
              >
                <span className="universe-portal-art" aria-hidden="true">
                  <img
                    className="universe-portal-window"
                    src={artUrl(landmark.landscape)}
                    alt=""
                    width={300}
                    height={180}
                    draggable={false}
                  />
                  <img
                    className="universe-landmark"
                    src={artUrl(`sprites/${landmark.sprite}`)}
                    alt=""
                    width={180}
                    height={180}
                    draggable={false}
                  />
                </span>
                <span className="universe-portal-name">{zone.name}</span>
                <small>
                  {zone.count
                    ? `${zone.count} ${zone.count === 1 ? "aventura" : "aventuras"}`
                    : "En preparación"}
                </small>
              </button>
            );
          })}
        </div>
        <div
          className="universe-companion"
          style={
            {
              "--guide-x": `${Math.max(5, Math.min(73, target ? target.x - 21 : 58))}%`,
            } as CSSProperties
          }
        >
          <FieldGuide {...pet} mood={selected ? "happy" : "idle"} />
        </div>
        <div className="universe-foreground" aria-hidden="true">
          <img src={artUrl("sprites/helechos")} alt="" width={360} height={360} draggable={false} />
          <img src={artUrl("sprites/flores")} alt="" width={300} height={300} draggable={false} />
        </div>
      </div>
      <div className="universe-guide-message" aria-live="polite">
        <span>
          <strong>{pet?.name ?? "Peluqo"}</strong>{" "}
          {target?.greeting ?? "Te acompaño. Elige por dónde empezamos."}
        </span>
        {selectedZone && (
          <a href="#universe-adventures">
            {selectedZone.count ? "Ver aventuras" : "Ver este portal"}{" "}
            <ArrowDown size={16} aria-hidden="true" />
          </a>
        )}
      </div>
    </div>
  );
}

export function subjectZones(worlds: { subject?: string | null }[]) {
  const entries: SubjectZone[] = Object.entries(subjects)
    .map(([id, name]) => ({
      id,
      name,
      count: worlds.filter((world) => world.subject === id).length,
    }))
    .filter((zone) => zone.count > 0);
  const unclassified = worlds.filter(
    (world) => !world.subject || !(world.subject in subjects),
  ).length;
  if (unclassified)
    entries.push({ id: "sin_clasificar", name: "Por organizar", count: unclassified });
  return entries;
}
