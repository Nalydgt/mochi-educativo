import type { Companion, PublicActivity, World } from "@/lib/education/schema";

export const artUrl = (asset: string) => `/educacion/mundos/${asset}.webp`;

export const fieldArt: Record<
  World["theme"],
  { background: string; trail: string; ground: number }
> = {
  reserve: { background: "reserva", trail: "Sendero del río", ground: 0.78 },
  space: { background: "observatorio", trail: "Paseo del observatorio", ground: 0.85 },
  workshop: { background: "taller", trail: "Sala de los descubrimientos", ground: 0.81 },
};

export const guideArt = {
  ready: "sprites/peluqo-alerta",
  celebrate: "sprites/peluqo-alegre",
  scarf: "sprites/panuelo",
  star: "sprites/estrella",
};

export const guideFilter: Record<Companion["color"], string> = {
  sunburst: "none",
  mint: "hue-rotate(92deg) saturate(.8)",
  lavender: "hue-rotate(208deg) saturate(.76)",
  ember: "hue-rotate(-23deg) saturate(1.12)",
};

export const landmarkArt: Record<PublicActivity["type"], string> = {
  classification: "sprites/puesto-cuaderno",
  anatomy: "sprites/puesto-lupa",
  question: "sprites/puesto-mirador",
  matching: "sprites/puesto-cuaderno",
  sequence: "sprites/puesto-mirador",
  memory: "sprites/puesto-cuaderno",
  puzzle: "sprites/puesto-lupa",
  listening: "sprites/puesto-mirador",
  manipulatives: "sprites/puesto-cuaderno",
  lab: "sprites/puesto-lupa",
};

export const animalArt: Record<string, string> = {
  frog: "sprites/rana",
  fish: "sprites/pez",
  cat: "sprites/gato",
  bird: "sprites/ave",
  turtle: "sprites/tortuga",
  dolphin: "sprites/delfin",
  human: "sprites/cuerpo-humano",
};
