import { useEffect, useState } from "react";
import { ArrowUpRight, Compass } from "lucide-react";
import { BrandMark, presentationArt, presentationSprite } from "./BrandMark";
import "./presentacion.css";

export { presentationArt, presentationSprite } from "./BrandMark";

export function ClassroomLink({ short = false }: { short?: boolean }) {
  return (
    <a className="presentacion-entrada" href="/expedicion">
      {short ? "Entrar al Aula" : "Entrar a Peluqo Aula"}{" "}
      <ArrowUpRight size={18} aria-hidden="true" />
    </a>
  );
}

export function PublicHeader({ active }: { active?: "register" | "login" | "recovery" }) {
  const [section, setSection] = useState("");
  useEffect(() => {
    if (active || !window.IntersectionObserver) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setSection(entry.target.id === "inicio" ? "" : entry.target.id);
        }
      },
      { rootMargin: "-10% 0px -60% 0px" },
    );
    document
      .querySelectorAll(".presentacion-hero, #mundos, #como-se-juega")
      .forEach((element) => observer.observe(element));
    const reveal = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("presentacion-revealed");
            reveal.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -6% 0px", threshold: 0.12 },
    );
    document.querySelectorAll("[data-reveal]").forEach((element) => reveal.observe(element));
    return () => {
      observer.disconnect();
      reveal.disconnect();
    };
  }, [active]);
  return (
    <header className="presentacion-cabecera">
      <div className="presentacion-ancho">
        <a className="presentacion-marca" href={active ? "/" : "#inicio"}>
          <BrandMark />
        </a>
        <nav aria-label="Presentación de Peluqo">
          <a
            href={active ? "/#mundos" : "#mundos"}
            aria-current={!active && section === "mundos" ? "location" : undefined}
          >
            Mundos
          </a>
          <a
            href={active ? "/#como-se-juega" : "#como-se-juega"}
            aria-current={!active && section === "como-se-juega" ? "location" : undefined}
          >
            Cómo se juega
          </a>
        </nav>
        <div className="presentacion-accesos">
          <a
            className="presentacion-sesion"
            href="/entrar"
            aria-current={active === "login" ? "page" : undefined}
          >
            Iniciar sesión
          </a>
          <a
            className="presentacion-registro"
            href="/registro"
            aria-current={active === "register" ? "page" : undefined}
          >
            Crear cuenta
          </a>
          <ClassroomLink short />
        </div>
      </div>
    </header>
  );
}

export function RiverPortrait({ welcome = false }: { welcome?: boolean }) {
  return (
    <figure className="presentacion-paisaje">
      <img
        className="presentacion-fondo"
        src={`${presentationArt}/reserva.webp`}
        width="1680"
        height="746"
        alt="Sendero junto a un río, rodeado de helechos y montañas"
        fetchPriority="high"
      />
      <img
        className="presentacion-personaje"
        src={presentationSprite(welcome ? "peluqo-alegre" : "peluqo-alerta")}
        width="460"
        height="460"
        alt="Peluqo, un compañero amarillo de orejas puntiagudas"
      />
      <img
        className="presentacion-rana"
        src={presentationSprite("rana")}
        width="460"
        height="460"
        alt=""
      />
      <figcaption>
        <Compass size={16} aria-hidden="true" /> Sendero del río
      </figcaption>
    </figure>
  );
}
