import { lazy, Suspense, useState } from "react";
import { ActivityGame } from "./ActivityGame";
import {
  activityLabels,
  activitySchema,
  activityTypes,
  assets,
  audioLabels,
  checkAnswer,
  defaultWorld,
  difficulties,
  educationAgeBands,
  puzzlePictures,
  subjects,
  supportsCards,
  worldThemes,
  type Mission,
  type Activity,
  type StudyFormat,
  type World,
} from "@/lib/education/schema";
import {
  newPracticeGame,
  puzzleContent,
  tokenChoices,
  variantsFromMaterial,
} from "@/lib/education/game-templates";

const FieldScene = lazy(() => import("./FieldScene"));
const assetLabels: Record<Activity["asset"], string> = {
  fish: "Pez",
  frog: "Rana",
  turtle: "Tortuga",
  bird: "Ave",
  dolphin: "Delfín",
  cat: "Gato",
  moon: "Fases de la Luna",
  plant: "Planta",
  shapes: "Figuras geométricas",
  timeline: "Línea del tiempo",
  human: "Cuerpo humano de frente",
};

function RecordingOption({
  value,
  onChange,
}: {
  value: Activity["pieces"][number]["sample"];
  onChange: (value: Activity["pieces"][number]["sample"]) => void;
}) {
  return (
    <label>
      Audio de la tarjeta
      <select
        value={value ?? ""}
        onChange={(e) => onChange((e.target.value || undefined) as typeof value)}
      >
        <option value="">Voz local para leer el texto</option>
        {Object.entries(audioLabels).map(([id, label]) => (
          <option key={id} value={id}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function MissionEditor({
  mission,
  onChange,
  sourceOptions = [],
}: {
  mission: Mission;
  onChange: (m: Mission) => void;
  sourceOptions?: { id: string; page: number | null; content: string }[];
}) {
  const [phase, setPhase] = useState<"diagnostic" | "practice" | "final" | "retention">("practice");
  const [index, setIndex] = useState(0);
  const [preview, setPreview] = useState(false);
  const [previewWorld, setPreviewWorld] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [newType, setNewType] = useState<Activity["type"]>("matching");
  const [previewFormat, setPreviewFormat] = useState<StudyFormat>("board");
  const a = mission[phase][index] ?? mission[phase][0];
  const world =
    mission.world ??
    defaultWorld(mission.practice, mission.title === "La expedición de los vertebrados");
  if (!a) return <p>La propuesta no contiene actividades en esta fase.</p>;
  const variants = phase === "practice" ? variantsFromMaterial(mission) : [];
  const validation = activitySchema.safeParse(a);
  const validationMessage = validation.error?.issues.find(
    (issue) => issue.code === "custom",
  )?.message;
  const fixedChoices = ["puzzle", "sequence", "manipulatives", "lab"].includes(a.type);
  const fixedPieces = a.type === "puzzle" || a.type === "lab";
  const paired = ["matching", "memory", "sequence"].includes(a.type);
  function editWorld(patch: Partial<World>) {
    onChange({ ...mission, world: { ...world, ...patch, view: "map" } });
  }
  function edit(patch: Partial<Activity>) {
    onChange({
      ...mission,
      [phase]: mission[phase].map((x) => (x.id === a!.id ? { ...x, ...patch } : x)),
    });
  }
  function append(games: Activity[]) {
    if (!games.length || mission.practice.length + games.length > 9) return;
    onChange({
      ...mission,
      practice: [...mission.practice, ...games],
      world: {
        ...world,
        view: "map",
        stations: [
          ...world.stations,
          ...games.map((game) => ({ activityId: game.id, title: game.title, observation: "" })),
        ],
      },
    });
    setIndex(mission.practice.length);
    setPreview(false);
    setFeedback("");
  }
  function addPiece() {
    const id = `pieza-${crypto.randomUUID().slice(0, 8)}`;
    const slot = paired ? `destino-${id}` : a!.choices[0]!.id;
    edit({
      choices: paired
        ? [
            ...a!.choices,
            { id: slot, label: a!.type === "sequence" ? `Posición ${a!.choices.length + 1}` : "" },
          ]
        : a!.choices,
      pieces: [...a!.pieces, { id, label: "" }],
      answer: { ...a!.answer, [id]: slot },
    });
  }
  return (
    <div className="edu-editor">
      <label>
        Nombre de la misión
        <input
          value={mission.title}
          onChange={(e) => onChange({ ...mission, title: e.target.value })}
        />
      </label>
      <label>
        Bienvenida
        <textarea
          value={mission.intro}
          onChange={(e) => onChange({ ...mission, intro: e.target.value })}
        />
      </label>
      <label>
        Asignatura
        <select
          value={mission.subject ?? ""}
          onChange={(e) => {
            const { subject, ...rest } = mission;
            const selected = e.target.value;
            onChange(selected ? { ...rest, subject: selected as keyof typeof subjects } : rest);
          }}
        >
          <option value="">Sin indicar</option>
          {Object.entries(subjects).map(([id, title]) => (
            <option key={id} value={id}>
              {title}
            </option>
          ))}
        </select>
      </label>
      <div className="edu-row">
        <label>
          Edad recomendada
          <select
            value={mission.ageBand}
            onChange={(e) =>
              onChange({
                ...mission,
                ageBand: e.target.value as Mission["ageBand"],
              })
            }
          >
            {educationAgeBands.map((band) => (
              <option key={band} value={band}>
                {band} años
              </option>
            ))}
          </select>
        </label>
        <label>
          Curso (opcional)
          <input
            value={mission.course ?? ""}
            maxLength={90}
            placeholder="Por ejemplo, 2.º de ESO"
            onChange={(e) => {
              const { course, ...rest } = mission;
              onChange(e.target.value.trim() ? { ...rest, course: e.target.value } : rest);
            }}
          />
        </label>
      </div>
      <details className="world-editor">
        <summary>Escenario y paradas del mundo</summary>
        <div className="edu-row">
          <label>
            Escenario
            <select
              value={world.theme}
              onChange={(event) => editWorld({ theme: event.target.value as World["theme"] })}
            >
              {Object.entries(worldThemes).map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {world.stations.map((station, i) => (
          <fieldset className="world-editor-station" key={station.activityId}>
            <legend>
              {i + 1}.{" "}
              {mission.practice.find((activity) => activity.id === station.activityId)?.title}
            </legend>
            <label>
              Nombre de la parada
              <input
                value={station.title}
                maxLength={180}
                onChange={(event) =>
                  editWorld({
                    stations: world.stations.map((item) =>
                      item.activityId === station.activityId
                        ? { ...item, title: event.target.value }
                        : item,
                    ),
                  })
                }
              />
            </label>
            <label>
              Qué observar
              <textarea
                value={station.observation}
                maxLength={420}
                onChange={(event) =>
                  editWorld({
                    stations: world.stations.map((item) =>
                      item.activityId === station.activityId
                        ? { ...item, observation: event.target.value }
                        : item,
                    ),
                  })
                }
              />
            </label>
          </fieldset>
        ))}
        <button
          type="button"
          className="edu-button"
          onClick={() => setPreviewWorld((shown) => !shown)}
        >
          {previewWorld ? "Cerrar el sendero" : "Probar el sendero 2D"}
        </button>
        {previewWorld && (
          <Suspense fallback={<p role="status">Abriendo el sendero…</p>}>
            <FieldScene
              world={world}
              activities={mission.practice}
              pet={{ name: "Peluqo", color: "sunburst", accessory: "none" }}
              onVisit={(activity) => {
                setPhase("practice");
                const index = mission.practice.findIndex((item) => item.id === activity.id);
                setIndex(index);
                setPreview(activitySchema.safeParse(mission.practice[index]).success);
                setFeedback("");
              }}
            />
          </Suspense>
        )}
      </details>
      <div className="edu-row">
        <label>
          Etapa
          <select
            value={phase}
            onChange={(e) => {
              setPhase(e.target.value as typeof phase);
              setIndex(0);
              setFeedback("");
            }}
          >
            <option value="diagnostic">Diagnóstico sin ayuda</option>
            <option value="practice">Práctica</option>
            <option value="final">Evaluación final</option>
            <option value="retention">Repaso diferido</option>
          </select>
        </label>
        <label>
          Actividad
          <select
            value={a.id}
            onChange={(e) => {
              setIndex(mission[phase].findIndex((x) => x.id === e.target.value));
              setFeedback("");
            }}
          >
            {mission[phase].map((x) => (
              <option key={x.id} value={x.id}>
                {x.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      {phase === "practice" && (
        <details className="world-editor">
          <summary>Ampliar los juegos de práctica</summary>
          <p className="edu-help">
            {mission.practice.length} de 9 retos. Cada juego tendrá su parada y sus fuentes.
          </p>
          {variants.length > 0 && (
            <button type="button" className="edu-button" onClick={() => append(variants)}>
              Crear variantes del material ({variants.length})
            </button>
          )}
          {mission.practice.length < 9 && (
            <div className="edu-row">
              <label>
                Mecánica nueva
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value as Activity["type"])}
                >
                  {activityTypes.map((type) => (
                    <option key={type} value={type}>
                      {activityLabels[type]}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="edu-button"
                onClick={() =>
                  append([
                    newPracticeGame(
                      newType,
                      `reto-${crypto.randomUUID().slice(0, 8)}`,
                      world.theme,
                    ),
                  ])
                }
              >
                Añadir juego
              </button>
            </div>
          )}
          {mission.practice.length > 3 && (
            <button
              type="button"
              className="edu-button"
              onClick={() => {
                onChange({
                  ...mission,
                  practice: mission.practice.filter((game) => game.id !== a.id),
                  world: {
                    ...world,
                    stations: world.stations.filter((stop) => stop.activityId !== a.id),
                  },
                });
                setIndex(0);
                setPreview(false);
                setFeedback("");
              }}
            >
              Quitar este juego del borrador
            </button>
          )}
        </details>
      )}
      <button
        className="edu-button"
        disabled={!preview && !validation.success}
        onClick={() => {
          setPreview((v) => !v);
          setFeedback("");
        }}
      >
        {preview ? "Editar contenido" : "Probar esta actividad"}
      </button>
      {!preview && !validation.success && (
        <p className="edu-help">
          {validationMessage ??
            "Completa las instrucciones, las tarjetas, la solución, una pista, una explicación y al menos una fuente para probarlo."}
        </p>
      )}
      {preview ? (
        <>
          {phase === "practice" && supportsCards(a) && (
            <label>
              Forma de practicar
              <select
                value={previewFormat}
                onChange={(e) => setPreviewFormat(e.target.value as StudyFormat)}
              >
                <option value="board">Tablero original</option>
                <option value="cards">
                  {a.type === "question" ? "Descartar opciones" : "Tarjetas guiadas"}
                </option>
              </select>
            </label>
          )}
          <ActivityGame
            key={`${a.id}:${previewFormat}`}
            activity={a}
            studyFormat={phase === "practice" && supportsCards(a) ? previewFormat : "board"}
            preview
            retryFeedback={feedback.startsWith("Todavía no.") ? feedback : undefined}
            onEdit={() => setFeedback("")}
            onSubmit={async (answer) =>
              setFeedback(
                checkAnswer(a, answer)
                  ? "Correcto. " + a.explanation
                  : "Todavía no. Revisa la solución y las instrucciones.",
              )
            }
          />
          {!feedback.startsWith("Todavía no.") && <p role="status">{feedback}</p>}
        </>
      ) : (
        <div className="edu-edit-fields">
          <p className="edu-tag">{activityLabels[a.type]}</p>
          <label>
            Título
            <input value={a.title} onChange={(e) => edit({ title: e.target.value })} />
          </label>
          <label>
            Competencia
            <input value={a.competency} onChange={(e) => edit({ competency: e.target.value })} />
          </label>
          <label>
            Dificultad
            <select
              value={a.difficulty ?? ""}
              onChange={(e) =>
                edit({
                  difficulty: (e.target.value || undefined) as Activity["difficulty"],
                })
              }
            >
              <option value="">Sin indicar</option>
              {Object.entries(difficulties).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Instrucciones
            <textarea
              value={a.instruction}
              onChange={(e) => edit({ instruction: e.target.value })}
            />
          </label>
          {a.type === "anatomy" && (
            <label>
              Esquema
              <select
                value={a.asset}
                onChange={(e) => edit({ asset: e.target.value as Activity["asset"] })}
              >
                {assets.map((asset) => (
                  <option key={asset} value={asset}>
                    {assetLabels[asset]}
                  </option>
                ))}
              </select>
            </label>
          )}
          {a.type === "puzzle" && (
            <label>
              Ilustración del puzle
              <select
                value={a.puzzlePicture}
                onChange={(e) => edit(puzzleContent(e.target.value as keyof typeof puzzlePictures))}
              >
                {Object.entries(puzzlePictures).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {a.type === "manipulatives" && (
            <label>
              Fichas disponibles
              <select
                value={a.stock}
                onChange={(e) => {
                  const stock = Number(e.target.value);
                  edit({
                    stock,
                    choices: tokenChoices(stock),
                    answer: Object.fromEntries(
                      Object.entries(a.answer).map(([id, count]) => [
                        id,
                        String(Math.min(stock, Number(count))),
                      ]),
                    ),
                  });
                }}
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i + 1}>
                    {i + 1}
                  </option>
                ))}
              </select>
            </label>
          )}
          {a.type === "lab" && (
            <p>Modelo de circuito eléctrico sencillo con una pila, un interruptor y una lámpara.</p>
          )}
          {!fixedChoices && <h3>{a.type === "question" ? "Opciones" : "Destinos"}</h3>}
          {!fixedChoices &&
            a.choices.map((c, i) => (
              <div key={c.id} className="edu-row">
                <label>
                  Opción {i + 1}
                  <input
                    value={c.label}
                    onChange={(e) =>
                      edit({
                        choices: a.choices.map((x) =>
                          x.id === c.id ? { ...x, label: e.target.value } : x,
                        ),
                      })
                    }
                  />
                </label>
                {(a.type === "matching" || a.type === "memory") && (
                  <label>
                    Ilustración del destino
                    <select
                      value={c.asset ?? ""}
                      onChange={(e) =>
                        edit({
                          choices: a.choices.map((x) =>
                            x.id === c.id
                              ? {
                                  ...x,
                                  asset: (e.target.value || undefined) as
                                    Activity["asset"] | undefined,
                                }
                              : x,
                          ),
                        })
                      }
                    >
                      <option value="">Sin ilustración</option>
                      {assets.map((asset) => (
                        <option key={asset} value={asset}>
                          {assetLabels[asset]}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {a.type === "memory" && (
                  <RecordingOption
                    value={c.sample}
                    onChange={(sample) =>
                      edit({
                        choices: a.choices.map((x) => (x.id === c.id ? { ...x, sample } : x)),
                      })
                    }
                  />
                )}
                {a.type === "anatomy" && (
                  <>
                    <label>
                      Posición horizontal (%)
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={c.x ?? 50}
                        onChange={(e) =>
                          edit({
                            choices: a.choices.map((x) =>
                              x.id === c.id ? { ...x, x: Number(e.target.value) } : x,
                            ),
                          })
                        }
                      />
                    </label>
                    <label>
                      Posición vertical (%)
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={c.y ?? 50}
                        onChange={(e) =>
                          edit({
                            choices: a.choices.map((x) =>
                              x.id === c.id ? { ...x, y: Number(e.target.value) } : x,
                            ),
                          })
                        }
                      />
                    </label>
                  </>
                )}
              </div>
            ))}
          {!fixedChoices && !paired && a.choices.length < 8 && (
            <button
              type="button"
              className="edu-button"
              onClick={() =>
                edit({
                  choices: [
                    ...a.choices,
                    {
                      id: `destino-${crypto.randomUUID().slice(0, 8)}`,
                      label: "",
                      ...(a.type === "anatomy" ? { x: 50, y: 50 } : {}),
                    },
                  ],
                })
              }
            >
              Añadir {a.type === "question" ? "opción" : "destino"}
            </button>
          )}
          {a.type !== "puzzle" && <h3>Solución privada</h3>}
          {a.type !== "puzzle" &&
            (a.type === "question"
              ? [{ id: "choice", label: "Respuesta correcta" }]
              : a.pieces
            ).map((p) => (
              <div key={p.id}>
                {a.type !== "question" && !fixedPieces && (
                  <label>
                    {a.type === "manipulatives"
                      ? "Nombre del grupo"
                      : a.type === "listening"
                        ? "Texto de la pista"
                        : "Nombre de la tarjeta"}
                    <input
                      value={p.label}
                      onChange={(e) =>
                        edit({
                          pieces: a.pieces.map((x) =>
                            x.id === p.id ? { ...x, label: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </label>
                )}
                {a.type !== "question" &&
                  !fixedPieces &&
                  a.type !== "manipulatives" &&
                  a.type !== "listening" && (
                    <label>
                      Ilustración de la tarjeta
                      <select
                        value={"asset" in p ? (p.asset ?? "") : ""}
                        onChange={(e) =>
                          edit({
                            pieces: a.pieces.map((x) =>
                              x.id === p.id
                                ? {
                                    ...x,
                                    asset: (e.target.value || undefined) as
                                      Activity["asset"] | undefined,
                                  }
                                : x,
                            ),
                          })
                        }
                      >
                        <option value="">Sin ilustración</option>
                        {assets.map((asset) => (
                          <option key={asset} value={asset}>
                            {assetLabels[asset]}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                {(a.type === "listening" || a.type === "memory" || a.type === "matching") && (
                  <RecordingOption
                    value={"sample" in p ? p.sample : undefined}
                    onChange={(sample) =>
                      edit({ pieces: a.pieces.map((x) => (x.id === p.id ? { ...x, sample } : x)) })
                    }
                  />
                )}
                <label>
                  {p.label || "Respuesta esperada"}
                  <select
                    value={a.answer[p.id] ?? ""}
                    onChange={(e) => edit({ answer: { ...a.answer, [p.id]: e.target.value } })}
                  >
                    {a.choices.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ))}
          {a.type !== "question" && !fixedPieces && a.pieces.length < (paired ? 8 : 12) && (
            <button type="button" className="edu-button" onClick={addPiece}>
              Añadir{" "}
              {a.type === "manipulatives" ? "grupo" : paired ? "pareja de tarjetas" : "tarjeta"}
            </button>
          )}
          <label>
            Pistas, una por línea
            <textarea
              value={a.hints.join("\n")}
              onChange={(e) => edit({ hints: e.target.value.split("\n") })}
            />
          </label>
          <label>
            Explicación del resultado
            <textarea
              value={a.explanation}
              onChange={(e) => edit({ explanation: e.target.value })}
            />
          </label>
          {sourceOptions.length > 0 && (
            <fieldset>
              <legend>Fuentes que justifican esta actividad</legend>
              {sourceOptions.map((s, i) => (
                <label className="edu-check" key={s.id}>
                  <input
                    type="checkbox"
                    checked={a.sources.some((r) => r.chunkId === s.id)}
                    onChange={(e) =>
                      edit({
                        sources: e.target.checked
                          ? [...a.sources, { chunkId: s.id, page: s.page }]
                          : a.sources.filter((r) => r.chunkId !== s.id),
                      })
                    }
                  />
                  <span>
                    {s.page ? `Página ${s.page}` : "Texto"}, fragmento {i + 1}:{" "}
                    {s.content.slice(0, 140)}…
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          {sourceOptions.length === 0 && a.sources.length === 0 && (
            <p className="edu-help">
              Abre «Leer fuente extraída» en la sección de materiales para asociar un fragmento.
            </p>
          )}
          <p className="edu-help">
            Referencias verificadas:{" "}
            {a.sources.map((s) => (s.page ? `pág. ${s.page}` : "documento de texto")).join(", ")}.
            Las soluciones solo son visibles para el docente.
          </p>
        </div>
      )}
    </div>
  );
}
