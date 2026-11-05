export const presentationArt = "/educacion/mundos";
export const presentationSprite = (name: string) => `${presentationArt}/sprites/${name}.webp`;

const subjectArt: Record<string, "reserva" | "observatorio" | "taller"> = {
  matematicas: "taller",
  naturaleza: "reserva",
  palabras: "taller",
  historia: "observatorio",
};

export function subjectLandscape(slug: string) {
  return subjectArt[slug] ?? "reserva";
}

export function BrandMark({ label = "Peluqo" }: { label?: string }) {
  return (
    <span className="peluqo-brand">
      <img src={presentationSprite("peluqo-alerta")} width={42} height={42} alt="" />
      <span>{label}</span>
    </span>
  );
}
