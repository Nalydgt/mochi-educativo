import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActivityGame } from "@/components/education/ActivityGame";
import { MissionEditor } from "@/components/education/MissionEditor";
import { newPracticeGame, variantsFromMaterial } from "@/lib/education/game-templates";
import {
  activitySchema,
  checkAnswer,
  missionSchema,
  publicActivity,
  type Activity,
} from "@/lib/education/schema";
import { reviewedMission } from "../../fixtures/reviewed-mission";

const mission = reviewedMission("22222222-2222-4222-8222-222222222222", 1);
const classification = mission.practice.find((a) => a.type === "classification")!;

function exercise(type: Activity["type"], patch: Partial<Activity> = {}) {
  return activitySchema.parse({
    ...newPracticeGame(type, "reto-prueba", "reserve"),
    competency: "Competencia de la prueba",
    instruction: "Resuelve este reto de prueba.",
    hints: ["Una pista breve."],
    explanation: "Una explicación educativa de la solución.",
    sources: classification.sources,
    ...patch,
  });
}

function play(activity: Activity, cards = false) {
  const submitted = vi.fn(async (_answer: Record<string, string>) => undefined);
  render(
    <ActivityGame
      activity={publicActivity(activity)}
      studyFormat={cards ? "cards" : "board"}
      onSubmit={submitted}
    />,
  );
  return {
    submit() {
      const button = screen.getByRole("button", { name: "Enviar respuesta" });
      expect(button).toBeEnabled();
      fireEvent.click(button);
      const last = submitted.mock.lastCall?.[0];
      expect(last).toBeDefined();
      expect(checkAnswer(activity, last!)).toBe(true);
    },
  };
}

function pairwise(type: "matching" | "memory" | "sequence") {
  return exercise(type, {
    choices: [
      { id: "uno", label: "Primer destino" },
      { id: "dos", label: "Segundo destino" },
    ],
    pieces: [
      { id: "a", label: "Clavel" },
      { id: "b", label: "Amapola" },
    ],
    answer: { a: "uno", b: "dos" },
  });
}

describe("mecánicas reutilizables de Peluqo", () => {
  it("crea variantes con referencias reales y añade sus paradas al borrador sin alterar la evaluación", () => {
    const variants = variantsFromMaterial(mission);
    expect(variants.map((a) => a.type)).toEqual(["matching", "memory", "listening"]);
    for (const activity of variants) {
      expect(activity.sources).toEqual(classification.sources);
      expect(publicActivity(activity)).not.toHaveProperty("answer");
    }
    const changed = vi.fn();
    render(<MissionEditor mission={mission} onChange={changed} />);
    fireEvent.click(screen.getByText("Ampliar los juegos de práctica"));
    fireEvent.click(screen.getByRole("button", { name: /Crear variantes del material/ }));
    const draft = missionSchema.parse(changed.mock.lastCall?.[0]);
    expect(draft.practice.length).toBe(6);
    expect(draft.world?.stations.length).toBe(6);
    expect(draft.final).toEqual(mission.final);
  });

  it("une tarjetas con controles de teclado y dibuja conexiones neutrales antes de comprobar", () => {
    const game = play(pairwise("matching"));
    fireEvent.click(screen.getByRole("button", { name: "Clavel" }));
    fireEvent.click(screen.getByRole("button", { name: "Primer destino" }));
    expect(
      screen.getByRole("button", { name: "Clavel, unida a Primer destino" }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 de 2 conexiones")).toBeInTheDocument();
    expect(screen.queryByText("Respuesta incorrecta")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Amapola" }));
    fireEvent.click(screen.getByRole("button", { name: "Segundo destino" }));
    game.submit();
  });

  it("reordena una secuencia después de colocarla", () => {
    const game = play(pairwise("sequence"));
    fireEvent.click(screen.getByRole("button", { name: "Amapola" }));
    fireEvent.click(screen.getByRole("button", { name: "Clavel" }));
    fireEvent.click(screen.getByRole("button", { name: "Subir Clavel" }));
    expect(
      within(screen.getByRole("list", { name: "Mi secuencia" })).getAllByRole("listitem")[0],
    ).toHaveTextContent("Clavel");
    game.submit();
  });

  it("oculta las cartas de memoria y permite abrirlas antes de guardar la pareja", () => {
    const game = play(pairwise("memory"));
    expect(screen.queryByText("Clavel")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Girar pista 1" }));
    if (!screen.queryByRole("button", { name: /Pista .*Clavel/ })) {
      fireEvent.click(screen.getByRole("button", { name: "Girar pista 2" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Girar pareja 1" }));
    if (!screen.queryByRole("button", { name: /Pareja .*Primer destino/ })) {
      fireEvent.click(screen.getByRole("button", { name: "Girar pareja 2" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Guardar pareja" }));
    expect(screen.getByText("1 de 2 parejas guardadas")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Girar pista/ }));
    fireEvent.click(screen.getByRole("button", { name: /Girar pareja/ }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar pareja" }));
    game.submit();
  });

  it("intercambia los fragmentos del mosaico conservando las cuatro piezas", () => {
    const activity = exercise("puzzle");
    const game = play(activity);
    for (const piece of activity.pieces) {
      fireEvent.click(screen.getByRole("button", { name: piece.label }));
      fireEvent.click(
        screen.getByRole("button", {
          name: new RegExp(
            "^" + activity.choices.find((c) => c.id === activity.answer[piece.id])!.label + ",",
          ),
        }),
      );
    }
    expect(screen.getByText(/intercambios? realizados?/)).toBeInTheDocument();
    expect(document.querySelectorAll(".edu-puzzle-slot img")).toHaveLength(4);
    game.submit();
  });

  it("completa una clasificación auditiva utilizando la alternativa textual", () => {
    const activity = variantsFromMaterial(mission).find((a) => a.type === "listening")!;
    const game = play(activity);
    for (const [i, piece] of activity.pieces.entries()) {
      fireEvent.click(screen.getByRole("button", { name: "Leer texto" }));
      expect(screen.getByText(piece.label)).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", {
          name: activity.choices.find((c) => c.id === activity.answer[piece.id])!.label,
        }),
      );
      if (i < activity.pieces.length - 1)
        fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    }
    game.submit();
  });

  it("observa el resultado del circuito al conectar la pila y cerrar el interruptor", () => {
    const game = play(exercise("lab"));
    fireEvent.click(screen.getByRole("button", { name: "Conectar pila" }));
    expect(screen.getByText("La lámpara está apagada")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar interruptor" }));
    expect(screen.getByText("La lámpara está encendida")).toBeInTheDocument();
    game.submit();
  });

  it("reparte fichas sin superar el total disponible", () => {
    const game = play(
      exercise("manipulatives", {
        pieces: [
          { id: "grupo-a", label: "Primer huerto" },
          { id: "grupo-b", label: "Segundo huerto" },
        ],
      }),
    );
    for (let i = 0; i < 6; i++) {
      fireEvent.click(screen.getByRole("button", { name: "Añadir una ficha a Primer huerto" }));
      fireEvent.click(screen.getByRole("button", { name: "Añadir una ficha a Segundo huerto" }));
    }
    expect(screen.getByText("0 fichas disponibles")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Añadir una ficha a Segundo huerto" }),
    ).toBeDisabled();
    game.submit();
  });

  it("permite practicar con tarjetas guiadas sin cambiar la corrección", () => {
    const guided = play(classification, true);
    for (const [i, piece] of classification.pieces.entries()) {
      expect(screen.getByText(`Tarjeta ${i + 1} de 3`)).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", {
          name: classification.choices.find((c) => c.id === classification.answer[piece.id])!.label,
        }),
      );
      if (i < classification.pieces.length - 1)
        fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    }
    guided.submit();
  });

  it("envía solo la opción que quedó después de descartar las otras", () => {
    const activity = mission.practice.find((a) => a.type === "question")!;
    const game = play(activity, true);
    const rejected = activity.choices.filter((choice) => choice.id !== activity.answer["choice"]);
    for (const choice of rejected)
      fireEvent.click(screen.getByRole("button", { name: `Descartar ${choice.label}` }));
    expect(screen.getByText(/En juego:/)).toBeInTheDocument();
    expect(screen.queryByText("Respuesta incorrecta")).toBeNull();
    game.submit();
  });

  it("retira el resultado de la vista previa al cambiar una respuesta", () => {
    const questionIndex = mission.practice.findIndex((a) => a.type === "question");
    const activity = mission.practice[questionIndex]!;
    render(<MissionEditor mission={mission} onChange={() => undefined} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Actividad" }), {
      target: { value: activity.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "Probar esta actividad" }));
    const correct = screen.getByRole("radio", {
      name: activity.choices.find((choice) => choice.id === activity.answer["choice"])!.label,
    });
    const wrong = screen.getAllByRole("radio").find((radio) => radio !== correct)!;
    fireEvent.click(correct);
    fireEvent.click(screen.getByRole("button", { name: "Comprobar en la vista previa" }));
    expect(screen.getByText(/^Correcto\./)).toBeInTheDocument();
    fireEvent.click(wrong);
    expect(screen.queryByText(/^Correcto\./)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Comprobar en la vista previa" }));
    expect(screen.getByText("Respuesta incorrecta")).toBeInTheDocument();
    fireEvent.click(correct);
    expect(screen.queryByText("Respuesta incorrecta")).toBeNull();
  });

  it("permite revisar una pareja de memoria sin borrarla", () => {
    const activity = pairwise("memory");
    const game = play(activity);
    for (const [wantedLeft, wantedRight] of [
      ["Clavel", "Primer destino"],
      ["Amapola", "Segundo destino"],
    ]) {
      for (const [side, wanted] of [
        ["Pistas", wantedLeft],
        ["Parejas", wantedRight],
      ]) {
        const deck = document.querySelector('[aria-label="' + side + '"]')!;
        for (const button of within(deck as HTMLElement).getAllByRole("button")) {
          if (button.getAttribute("data-paired") === "true") continue;
          fireEvent.click(button);
          if (button.textContent === wanted) break;
        }
      }
      fireEvent.click(screen.getByRole("button", { name: "Guardar pareja" }));
    }
    expect(screen.getByText("2 de 2 parejas guardadas")).toBeInTheDocument();
    const paired = screen.getAllByRole("button", { name: /pareja guardada/ })[0]!;
    fireEvent.click(paired);
    expect(screen.getByText("2 de 2 parejas guardadas")).toBeInTheDocument();
    game.submit();
  });

  it("guarda las condiciones realmente probadas en el laboratorio", () => {
    play(exercise("lab"));
    fireEvent.click(screen.getByRole("button", { name: "Conectar pila" }));
    const observations = screen.getByLabelText("Mis observaciones");
    expect(observations).toHaveTextContent("Conectada");
    expect(observations).toHaveTextContent("Abierto");
    expect(observations).toHaveTextContent("Apagada");
    fireEvent.click(screen.getByRole("button", { name: "Cerrar interruptor" }));
    expect(observations).toHaveTextContent("Encendida");
    fireEvent.click(screen.getByRole("button", { name: "Interruptor cerrado" }));
    expect(observations.querySelectorAll(".edu-experiment-row")).toHaveLength(2);
    expect(screen.getByText("La lámpara está apagada")).toBeInTheDocument();
  });
});
