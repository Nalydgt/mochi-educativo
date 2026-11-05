import { describe, it, expect } from "vitest";
import { signupAge, learnerInput, sceneSchema } from "@/lib/learning-schema";

describe("Mochi profile safeguards", () => {
  it("restricts web signup to adults", () => {
    expect(signupAge.safeParse("under14").success).toBe(false);
    expect(signupAge.safeParse("14–17").success).toBe(false);
    expect(signupAge.safeParse("18+").success).toBe(true);
  });
  it("allows a managed child profile without email or birth date", () => {
    const result = learnerInput.parse({
      display_name: "Explorador",
      education_level: "Primaria",
      grade_level: "4º",
      age_band: "9–12",
      color: "mint",
    });
    expect(result.age_band).toBe("9–12");
    expect(result.ia).toBe(false);
  });
  it("rejects missing educational content", () => {
    expect(sceneSchema.safeParse({ version: 1, intro: "Hola" }).success).toBe(false);
  });
});
