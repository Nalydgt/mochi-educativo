import { FieldGuide } from "./education/FieldGuide";

type P = { className?: string };
const S = "stroke-foreground";

export type MascotMood = "idle" | "listen" | "think" | "encourage" | "happy" | "wow" | "celebrate";
export function Mascot({
  className = "",
  mood = "happy",
  color = "sunburst",
  accessory = "none",
}: P & { mood?: MascotMood; color?: string; accessory?: string }) {
  const tint = color === "mint" || color === "lavender" || color === "ember" ? color : "sunburst";
  const piece = accessory === "scarf" || accessory === "star" ? accessory : "none";
  return (
    <FieldGuide
      className={`platform-portrait ${className}`}
      color={tint}
      accessory={piece}
      mood={mood}
    />
  );
}

export function Coin({ className = "" }: P) {
  return (
    <svg viewBox="0 0 60 60" className={className} aria-hidden>
      <circle cx="30" cy="30" r="27" className={`fill-sunburst ${S}`} strokeWidth="2" />
      <circle cx="30" cy="30" r="18" fill="none" className={S} strokeWidth="2" />
      <path d="M30 20 V40 M24 26 H36" className={S} strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export function Rocket({ className = "" }: P) {
  return (
    <svg viewBox="0 0 60 80" className={className} aria-hidden>
      <path
        d="M30 4 C44 18 46 40 40 58 H20 C14 40 16 18 30 4 Z"
        className={`fill-ember ${S}`}
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle cx="30" cy="30" r="7" className={`fill-sky ${S}`} strokeWidth="2" />
      <path
        d="M20 46 L8 62 L20 58 Z M40 46 L52 62 L40 58 Z"
        className={`fill-violet ${S}`}
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M24 60 L30 76 L36 60 Z"
        className={`fill-sunburst ${S}`}
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Check({ className = "" }: P) {
  return (
    <svg viewBox="0 0 60 60" className={className} aria-hidden>
      <rect
        x="3"
        y="3"
        width="54"
        height="54"
        rx="16"
        className={`fill-mint ${S}`}
        strokeWidth="2"
      />
      <path
        d="M16 31 L26 41 L44 20"
        fill="none"
        className={S}
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Star({ className = "" }: P) {
  return (
    <svg viewBox="0 0 60 60" className={className} aria-hidden>
      <path
        d="M30 4 L37 22 L56 23 L41 35 L46 54 L30 43 L14 54 L19 35 L4 23 L23 22 Z"
        className={`fill-lavender ${S}`}
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Ribbon({ className = "" }: P) {
  return (
    <svg viewBox="0 0 800 200" className={className} aria-hidden preserveAspectRatio="none">
      <path
        d="M-20 150 C120 20 260 20 380 110 S640 200 820 40"
        fill="none"
        className="stroke-foreground"
        strokeWidth="64"
        strokeLinecap="round"
      />
      <path
        d="M-20 150 C120 20 260 20 380 110 S640 200 820 40"
        fill="none"
        className="stroke-electric"
        strokeWidth="60"
        strokeLinecap="round"
      />
    </svg>
  );
}
