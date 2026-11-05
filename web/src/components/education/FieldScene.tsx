import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Compass, Footprints, Search, X } from "lucide-react";
import type { Companion, PublicActivity, World } from "@/lib/education/schema";
import { artUrl, fieldArt, landmarkArt } from "./fieldArt";
import type { createFieldGame, TrailStop } from "./fieldGame";
import "./field.css";

export default function FieldScene({
  world,
  activities,
  pet,
  solved,
  busy,
  onVisit,
}: {
  world: World;
  activities: PublicActivity[];
  pet: Companion;
  solved?: Set<string>;
  busy?: boolean;
  onVisit: (activity: PublicActivity) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const controls = useRef<ReturnType<typeof createFieldGame>>(null);
  const titleId = useId();
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [selection, setSelection] = useState("");
  const [nearby, setNearby] = useState<string | null>(null);
  const [observation, setObservation] = useState<string | null>(null);
  const [entering, setEntering] = useState(false);
  const art = fieldArt[world.theme];
  const { color, accessory } = pet;
  const stations = world.stations.flatMap((station) => {
    const activity = activities.find((item) => item.id === station.activityId);
    return activity ? [{ ...station, activity }] : [];
  });
  const selected = stations.find((station) => station.activityId === selection);
  const near = stations.find((station) => station.activityId === nearby);
  const observed = stations.find((station) => station.activityId === observation);
  const stopData = JSON.stringify(
    stations.map((station) => ({
      id: station.activityId,
      title: station.title,
      type: station.activity.type,
      complete: solved?.has(station.activityId) ?? false,
      observation: station.observation,
    })),
  );
  const stops = useMemo(() => JSON.parse(stopData) as TrailStop[], [stopData]);

  useEffect(() => {
    if (import.meta.env.SSR || !host.current) return;
    const element = host.current;
    let disposed = false;
    setReady(false);
    setFailed(false);
    setNearby(null);
    setEntering(false);
    void import("./fieldGame")
      .then(({ createFieldGame }) => {
        if (disposed) return;
        controls.current = createFieldGame({
          host: element,
          theme: world.theme,
          stops,
          pet: { color, accessory },
          onReady: () => setReady(true),
          onError: () => setFailed(true),
          onSelect: setSelection,
          onNear: setNearby,
          onObserve: setObservation,
        });
      })
      .catch(() => {
        if (!disposed) setFailed(true);
      });
    return () => {
      disposed = true;
      controls.current?.destroy();
      controls.current = null;
    };
  }, [world.theme, stops, color, accessory]);

  function choose(id: string) {
    if (entering) return;
    setSelection(id);
    if (ready) controls.current?.pick(id);
  }
  function enter(activity: PublicActivity) {
    if (busy || entering) return;
    if (!ready || !controls.current) {
      onVisit(activity);
      return;
    }
    setEntering(true);
    controls.current.enter(activity.id, () => {
      setEntering(false);
      onVisit(activity);
    });
  }

  return (
    <section
      className="field-scene"
      data-ready={ready}
      data-entering={entering}
      data-theme={world.theme}
      aria-labelledby={titleId}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        if (!entering) controls.current?.step(event.key === "ArrowLeft" ? -1 : 1);
      }}
    >
      <div className="field-stage" style={{ backgroundImage: `url(${artUrl(art.background)})` }}>
        <div className="field-canvas" ref={host} aria-hidden="true" />
        <div className="field-hud">
          <h2 id={titleId}>
            <Compass size={18} aria-hidden="true" /> {art.trail}
          </h2>
          <span>
            {stops.filter((stop) => stop.complete).length} / {stops.length} paradas
          </span>
        </div>
        {!ready && !failed && (
          <p className="field-status" role="status">
            Abriendo el sendero…
          </p>
        )}
        {failed && <p className="field-status">Puedes abrir los retos desde las paradas.</p>}
        {observed?.observation && (
          <div className="field-observation" role="status">
            <Search size={20} aria-hidden="true" />
            <div>
              <strong>{observed.title}</strong>
              <p>{observed.observation}</p>
            </div>
            <button
              type="button"
              aria-label="Cerrar observación"
              onClick={() => setObservation(null)}
            >
              <X size={17} />
            </button>
          </div>
        )}
        {!observation && near && !entering && (
          <button
            className="field-nearby"
            type="button"
            onClick={() => {
              choose(near.activityId);
              if (near.observation) setObservation(near.activityId);
            }}
          >
            <Search size={17} aria-hidden="true" /> Explorar {near.title}
          </button>
        )}
        {entering && (
          <p className="field-status field-travelling" role="status">
            Acercándonos al reto…
          </p>
        )}
        <div className="field-walk-controls" role="group" aria-label="Caminar por el sendero">
          <button
            type="button"
            disabled={!ready || entering}
            onClick={() => controls.current?.step(-1)}
            aria-label="Caminar a la izquierda"
          >
            <ArrowLeft size={21} />
          </button>
          <button
            type="button"
            disabled={!ready || entering}
            onClick={() => controls.current?.step(1)}
            aria-label="Caminar a la derecha"
          >
            <ArrowRight size={21} />
          </button>
        </div>
      </div>
      <p className="field-help">
        <Footprints size={17} aria-hidden="true" />
        {stops.some((stop) => stop.observation?.trim())
          ? "Toca el camino para caminar. Los objetos con «?» guardan una observación del mundo."
          : "Toca el camino o usa las flechas para caminar. Elige un puesto para abrir su reto."}
      </p>
      <nav className="field-stations" aria-label="Paradas del sendero">
        {stations.map((station, i) => (
          <button
            key={station.activityId}
            type="button"
            disabled={entering}
            aria-pressed={selection === station.activityId}
            onClick={() => choose(station.activityId)}
          >
            <img src={artUrl(landmarkArt[station.activity.type])} alt="" draggable={false} />
            <span>
              <strong>{station.title}</strong>
              <small>
                {solved?.has(station.activityId) ? (
                  <>
                    <Check size={15} aria-hidden="true" /> Descubierto
                  </>
                ) : (
                  `Parada ${i + 1}`
                )}
              </small>
            </span>
          </button>
        ))}
      </nav>
      {selected && (
        <div className="world-stop-detail" aria-live="polite">
          <div>
            <h3>{selected.title}</h3>
            <p>{selected.observation || selected.activity.title}</p>
          </div>
          <button
            type="button"
            className="edu-button primary"
            disabled={busy || entering}
            onClick={() => enter(selected.activity)}
          >
            {solved?.has(selected.activityId) ? "Ver descubrimiento" : "Abrir reto"}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        </div>
      )}
    </section>
  );
}
