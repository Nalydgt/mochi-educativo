import type { Companion } from "@/lib/education/schema";
import type { MascotMood } from "@/components/Stickers";
import { artUrl, guideArt, guideFilter } from "./fieldArt";

export function FieldGuide({
  color = "sunburst",
  accessory = "none",
  mood = "idle",
  className = "",
}: Partial<Companion> & { mood?: MascotMood; className?: string }) {
  const happy = mood === "celebrate" || mood === "happy";
  return (
    <span
      className={`field-guide ${className}`}
      data-mood={mood}
      role="img"
      aria-label="Peluqo, tu compañero"
    >
      <img
        src={artUrl(happy ? guideArt.celebrate : guideArt.ready)}
        style={{ filter: guideFilter[color] }}
        alt=""
        draggable={false}
      />
      {accessory !== "none" && (
        <img
          className="field-guide-accessory"
          data-accessory={accessory}
          src={artUrl(guideArt[accessory])}
          alt=""
          draggable={false}
        />
      )}
    </span>
  );
}
