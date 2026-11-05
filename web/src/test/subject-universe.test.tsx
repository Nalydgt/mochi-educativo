import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorldLibrary, type WorldListing } from "@/components/education/WorldSpaces";
import { subjectZones } from "@/components/education/SubjectUniverse";

const worlds: WorldListing[] = [
  {
    id: "science",
    subject: "ciencias",
    title: "La reserva",
    intro: "Animales del río",
    theme: "reserve",
  },
  {
    id: "math",
    subject: "matematicas",
    title: "La suma",
    intro: "Construimos una suma",
    theme: "workshop",
  },
];

describe("Subject universe navigation", () => {
  it("keeps assessment locks and the real world action when filtering through portals", () => {
    const open = vi.fn();
    render(
      <WorldLibrary
        worlds={worlds}
        progress={[]}
        lockedVersion="science"
        busy={false}
        onOpen={open}
      />,
    );
    const portals = screen.getByRole("group", { name: "Portales de las asignaturas" });
    fireEvent.click(within(portals).getByRole("button", { name: /Matemáticas/ }));
    expect(screen.getByRole("heading", { name: "La suma" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "La reserva" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explorar mundo" })).toBeDisabled();
    fireEvent.click(within(portals).getByRole("button", { name: /Ciencias/ }));
    fireEvent.click(screen.getByRole("button", { name: "Explorar mundo" }));
    expect(open).toHaveBeenCalledExactlyOnceWith("science");
  });

  it("shows populated subjects and preserves older unclassified worlds", () => {
    const zones = subjectZones([...worlds, { subject: null }, { subject: "asignatura-antigua" }]);
    expect(zones.map((zone) => zone.id)).toEqual(["ciencias", "matematicas", "sin_clasificar"]);
    expect(zones.find((zone) => zone.id === "sin_clasificar")?.count).toBe(2);
  });
});
