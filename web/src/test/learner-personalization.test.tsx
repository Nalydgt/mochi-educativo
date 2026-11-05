import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LearnerPersonalization } from "@/components/education/LearnerPersonalization";
import {
  defaultLearnerPreferences,
  learnerPreferencesSchema,
  personalGoalProgress,
} from "@/lib/education/personalization";

afterEach(cleanup);

describe("learner preferences", () => {
  it("provides defaults for existing learners and measures independent practice separately", () => {
    expect(learnerPreferencesSchema.parse({})).toEqual(defaultLearnerPreferences);
    expect(learnerPreferencesSchema.safeParse({ mechanics: ["puzzle", "puzzle"] }).success).toBe(
      false,
    );
    expect(personalGoalProgress("practice", { discoveries: 8, completed: 2 }).completed).toBeNull();
    expect(
      personalGoalProgress("practice", { discoveries: 8, completed: 2, unaided: 2 }).completed,
    ).toBe(2);
  });

  it("submits web-only choices and shows evidence from the newest visit to a world", async () => {
    const onSave = vi.fn().mockResolvedValue(true);
    render(
      <LearnerPersonalization
        preferences={defaultLearnerPreferences}
        pet={{ name: "Peluqo", accessory: "none", color: "sunburst" }}
        progress={{ discoveries: 3, completed: 1, unaided: 2 }}
        worlds={[
          { id: "reserve", title: "La reserva", intro: "Descubre el río", theme: "reserve" },
        ]}
        history={[
          { versionId: "reserve", phase: "completed" },
          { versionId: "reserve", phase: "practice" },
        ]}
        busy={false}
        onSave={onSave}
      />,
    );
    expect(screen.getByText("Completada")).toBeInTheDocument();
    expect(screen.queryByText("En exploración")).not.toBeInTheDocument();
    expect(screen.getByText("Objetivo cumplido")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Rana de la reserva/ }));
    fireEvent.change(screen.getByLabelText("Ambiente"), { target: { value: "space" } });
    fireEvent.click(screen.getByLabelText("Escucha y descubre"));
    fireEvent.change(screen.getByLabelText("Mi objetivo", { selector: "select" }), {
      target: { value: "practice" },
    });
    expect(screen.getByText("2 de 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Guardar mis preferencias" }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        ...defaultLearnerPreferences,
        theme: "space",
        guide: "frog",
        goal: "practice",
        mechanics: ["listening"],
      }),
    );
  });
});
