import { describe, it, expect } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  missionSchema,
  publicActivity,
  checkAnswer,
  defaultWorld,
  allowedAccessory,
  commandSchema,
} from "@/lib/education/schema";
import { ActivityGame } from "@/components/education/ActivityGame";
import { reviewedMission } from "../../fixtures/reviewed-mission";
const mission = reviewedMission("22222222-2222-4222-8222-222222222222", 1);
describe("educational publishing and evaluation", () => {
  it("accepts the reviewed three-game mission and rejects duplicated assessment content", () => {
    expect(missionSchema.safeParse(mission).success).toBe(true);
    expect(missionSchema.safeParse({ ...mission, final: mission.diagnostic }).success).toBe(false);
  });
  it("keeps answers and progressive help out of the learner payload", () => {
    const visible = publicActivity(mission.practice[0]!);
    expect(visible).not.toHaveProperty("answer");
    expect(visible).not.toHaveProperty("hints");
    expect(visible).not.toHaveProperty("explanation");
  });
  it("ties every published world stop to a distinct practice game", () => {
    const world = { ...defaultWorld(mission.practice), theme: "space" } as const;
    expect(missionSchema.safeParse({ ...mission, world }).success).toBe(true);
    const stations = world.stations.map((station) => ({ ...station, activityId: "another-world" }));
    expect(missionSchema.safeParse({ ...mission, world: { ...world, stations } }).success).toBe(
      false,
    );
  });
  it("requires every piece to be placed correctly, without extra or missing pieces", () => {
    const a = mission.practice[0]!;
    expect(checkAnswer(a, a.answer)).toBe(true);
    expect(checkAnswer(a, { ...a.answer, extra: "m" })).toBe(false);
    expect(checkAnswer(a, { delfin: "p", gorrion: "a", trucha: "p" })).toBe(false);
  });
  it("does not unlock accessories from client configuration or inactivity", () => {
    expect(allowedAccessory("scarf", 0, 0)).toBe(false);
    expect(allowedAccessory("star", 30, 0)).toBe(false);
    expect(allowedAccessory("star", 3, 1)).toBe(true);
    expect(
      commandSchema.safeParse({
        action: "companion",
        companion: { name: "Peluqo", color: "mint", accessory: "unlimited" },
      }).success,
    ).toBe(false);
  });
  it("supports classification entirely with labelled selection controls", async () => {
    let submitted: unknown;
    render(
      <ActivityGame
        activity={publicActivity(mission.practice[0]!)}
        onSubmit={async (answer) => {
          submitted = answer;
        }}
      />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Delfín" }), { target: { value: "m" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Gorrión" }), { target: { value: "a" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Trucha" }), { target: { value: "p" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar respuesta" }));
    expect(submitted).toEqual(mission.practice[0]!.answer);
  });
  it("shows the wrong-answer state only after grading and clears it when the answer changes", () => {
    const activity = publicActivity(mission.practice.find((entry) => entry.type === "question")!);
    function Attempt() {
      const [retry, setRetry] = useState<string>();
      return (
        <ActivityGame
          activity={activity}
          retryFeedback={retry}
          onEdit={() => setRetry(undefined)}
          onSubmit={async () => {
            setRetry("Revisa el dato que observaste.");
          }}
        />
      );
    }
    render(<Attempt />);
    const [first, second] = screen.getAllByRole("radio");
    fireEvent.click(first!);
    expect(first?.closest("label")).toHaveAttribute("data-incorrect", "false");
    expect(screen.queryByText("Respuesta incorrecta")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Enviar respuesta" }));
    expect(screen.getByRole("status")).toHaveTextContent("Respuesta incorrecta");
    expect(first?.closest("label")).toHaveAttribute("data-incorrect", "true");
    fireEvent.click(second!);
    expect(screen.queryByText("Respuesta incorrecta")).toBeNull();
    expect(second?.closest("label")).toHaveAttribute("data-incorrect", "false");
  });
});
