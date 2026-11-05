import {
  activityLabels,
  activitySchema,
  circuitParts,
  puzzleSlots,
  puzzleTiles,
  type Activity,
  type Mission,
  type World,
} from "./schema";

type Type = Activity["type"];
type Picture = NonNullable<Activity["puzzlePicture"]>;
const slotLabels = [
  "Arriba a la izquierda",
  "Arriba a la derecha",
  "Abajo a la izquierda",
  "Abajo a la derecha",
];
const tileLabels = {
  reserve: ["Troncos y hojas", "Río y montañas", "Camino junto a helechos", "Camino junto a rocas"],
  space: [
    "Árbol bajo las estrellas",
    "Luna sobre el observatorio",
    "Sendero bajo el árbol",
    "Sendero junto a los riscos",
  ],
  workshop: [
    "Estantería y vigas",
    "Ventanal al bosque",
    "Suelo junto a las macetas",
    "Suelo junto a la mesa de trabajo",
  ],
} as const;

export function puzzleContent(
  picture: Picture,
): Pick<Activity, "puzzlePicture" | "choices" | "pieces" | "answer"> {
  return {
    puzzlePicture: picture,
    choices: puzzleSlots.map((id, i) => ({ id, label: slotLabels[i]! })),
    pieces: puzzleTiles.map((tile, i) => ({ id: tile, tile, label: tileLabels[picture][i]! })),
    answer: Object.fromEntries(puzzleTiles.map((id, i) => [id, puzzleSlots[i]!])),
  };
}

export function tokenChoices(stock: number): Activity["choices"] {
  return Array.from({ length: stock + 1 }, (_, count) => ({
    id: String(count),
    label: String(count),
  }));
}

const linkedTypes = ["matching", "memory", "sequence", "listening"] as const;
type LinkedType = (typeof linkedTypes)[number];
const variantInstructions: Record<LinkedType, string> = {
  matching: "Une cada tarjeta con la pareja que le corresponde según el material.",
  memory: "Abre las cartas y recuerda dónde está la pareja de cada concepto según el material.",
  sequence: "Ordena las tarjetas de izquierda a derecha según la secuencia que estudiaste.",
  listening: "Escucha o lee cada término y decide en qué grupo se clasifica según el material.",
};

export function fromMaterial(type: LinkedType, source: Activity, id: string): Activity | undefined {
  const original = activitySchema.safeParse(source);
  if (!original.success) return;
  const a = original.data;
  if (type === "listening" && a.type !== "classification") return;
  if (type === "sequence" && (a.type !== "anatomy" || !["moon", "timeline"].includes(a.asset)))
    return;
  if (a.type !== "classification" && a.type !== "anatomy") return;
  const used = new Set<string>();
  const pieces =
    type === "listening"
      ? a.pieces
      : a.pieces.filter((piece) => {
          const value = a.answer[piece.id]!;
          if (used.has(value)) return false;
          used.add(value);
          return true;
        });
  if (pieces.length < 2) return;
  const choices = type === "listening" ? a.choices : a.choices.filter((c) => used.has(c.id));
  if (type === "sequence") choices.sort((a, b) => (a.x ?? 0) - (b.x ?? 0));
  const result = activitySchema.safeParse({
    ...a,
    id,
    type,
    title: `${activityLabels[type]}. ${a.title}`.slice(0, 180),
    instruction: variantInstructions[type],
    choices:
      type === "sequence"
        ? choices.map((c, i) => ({ id: c.id, label: `Posición ${i + 1}` }))
        : choices.map(({ id, label, asset }) => ({ id, label, asset })),
    pieces,
    answer: Object.fromEntries(pieces.map((p) => [p.id, a.answer[p.id]])),
  });
  return result.success ? result.data : undefined;
}

export function variantsFromMaterial(mission: Mission): Activity[] {
  const remaining = 9 - mission.practice.length;
  if (remaining <= 0) return [];
  const existing = new Set(mission.practice.map((a) => a.type));
  const variants: Activity[] = [];
  for (const type of linkedTypes) {
    if (existing.has(type) || variants.length >= remaining) continue;
    const variant = mission.practice
      .map((activity) => fromMaterial(type, activity, `material-${type}`))
      .find((activity) => activity !== undefined);
    if (variant) variants.push(variant);
  }
  const used = new Set(
    [...mission.diagnostic, ...mission.practice, ...mission.final, ...mission.retention].map(
      (a) => a.id,
    ),
  );
  return variants.map((a) => {
    let id = a.id;
    for (let n = 2; used.has(id); n++) id = `${a.id}-${n}`;
    used.add(id);
    return { ...a, id };
  });
}

export function newPracticeGame(type: Type, id: string, theme: World["theme"]): Activity {
  const base: Activity = {
    id,
    type,
    title: activityLabels[type],
    difficulty: "core",
    competency: "",
    instruction: "",
    asset: "fish",
    choices: [
      { id: "opcion-a", label: "" },
      { id: "opcion-b", label: "" },
    ],
    pieces: [],
    answer: { choice: "opcion-a" },
    hints: [],
    explanation: "",
    sources: [],
  };
  if (type === "question") return base;
  if (type === "puzzle") return { ...base, ...puzzleContent(theme) };
  if (type === "lab")
    return {
      ...base,
      experiment: "circuit",
      choices: [
        { id: "off", label: "Desconectado o abierto" },
        { id: "on", label: "Conectado o cerrado" },
      ],
      pieces: circuitParts.map((id) => ({ id, label: id === "battery" ? "Pila" : "Interruptor" })),
      answer: { battery: "on", switch: "on" },
    };
  if (type === "manipulatives")
    return {
      ...base,
      stock: 12,
      choices: tokenChoices(12),
      pieces: [
        { id: "grupo-a", label: "" },
        { id: "grupo-b", label: "" },
      ],
      answer: { "grupo-a": "6", "grupo-b": "6" },
    };
  return {
    ...base,
    asset: type === "anatomy" ? "human" : base.asset,
    choices: base.choices.map((c, i) => ({
      ...c,
      label: type === "sequence" ? `Posición ${i + 1}` : c.label,
      ...(type === "anatomy" ? { x: 50, y: i ? 33 : 12 } : {}),
    })),
    pieces: [
      { id: "tarjeta-a", label: "" },
      { id: "tarjeta-b", label: "" },
    ],
    answer: { "tarjeta-a": "opcion-a", "tarjeta-b": "opcion-b" },
  };
}
