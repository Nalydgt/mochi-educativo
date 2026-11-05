import { describe, expect, it } from "vitest";
import { reviewedMission } from "../../fixtures/reviewed-mission";
import { defaultLearnerPreferences } from "@/lib/education/personalization";
import { publicActivity } from "@/lib/education/schema";
import {
  recommendActivities,
  recommendStudyFormat,
  recommendWorld,
  type StudyAttempt,
} from "@/lib/education/study";

const mission = reviewedMission("22222222-2222-4222-8222-222222222222", 1);
const activities = mission.practice.map(publicActivity);
const current = activities[0]!;
const preferences = { ...defaultLearnerPreferences };
const attempt: StudyAttempt = {
  session_id: "current",
  activity_id: current.id,
  competency: current.competency,
  correct: false,
  hints: 0,
  study_format: "board",
  game: current.type,
};

describe("evidence-based study recommendations", () => {
  it("suggests a change only after repeated errors in the same presentation", () => {
    expect(recommendStudyFormat("current", current.id, false, [attempt]).format).toBe("board");
    expect(recommendStudyFormat("current", current.id, false, [attempt, attempt]).format).toBe(
      "cards",
    );
    expect(
      recommendStudyFormat("current", current.id, false, [
        { ...attempt, study_format: "cards" },
        attempt,
      ]).reason,
    ).toBe("start");
  });

  it("keeps independent pupils and sessions out of the retry signal", () => {
    expect(recommendStudyFormat("new", current.id, false, [attempt, attempt]).reason).toBe("start");
    expect(recommendStudyFormat("current", "different", false, [attempt, attempt]).reason).toBe(
      "start",
    );
  });

  it("uses distinct successes rather than duplicated attempts to infer an effective format", () => {
    const win = { ...attempt, study_format: "cards", correct: true } as const;
    expect(recommendStudyFormat("current", current.id, false, [win, win]).reason).toBe("start");
    expect(
      recommendStudyFormat("current", current.id, false, [win, { ...win, activity_id: "another" }])
        .reason,
    ).toBe("unassisted");
    expect(
      recommendStudyFormat("current", current.id, false, [
        { ...win, hints: 1 },
        { ...win, activity_id: "another", hints: 1 },
      ]).reason,
    ).toBe("start");
  });

  it("offers pending activities and retains variety when the pupil has a preferred mechanic", () => {
    const alternate = activities[1]!;
    const more = { ...current, id: "extra" };
    const result = recommendActivities(
      "current",
      [current, more, alternate],
      [],
      {
        ...preferences,
        mechanics: [current.type],
      },
      [],
      false,
    );
    expect(result).toHaveLength(2);
    expect(result[0]!.activityId).toBe(current.id);
    expect(result[1]!.activityId).toBe(alternate.id);
    expect(
      recommendActivities(
        "current",
        [current],
        [{ ...attempt, correct: true }],
        preferences,
        [],
        false,
      ),
    ).toEqual([]);
  });

  it("keeps a challenge behind sufficient unaided evidence and applies adult support priorities", () => {
    const easy = { ...current, id: "intro", difficulty: "intro" as const };
    const hard = { ...current, id: "challenge", difficulty: "challenge" as const };
    const priorities = [{ subject: null, goal: "stretch" as const }];
    expect(
      recommendActivities("current", [hard, easy], [], preferences, priorities, false)[0]!
        .activityId,
    ).toBe("intro");
    const wins = ["win1", "win2"].map((id) => ({ ...attempt, activity_id: id, correct: true }));
    expect(
      recommendActivities("current", [easy, hard], wins, preferences, priorities, false)[0]!
        .activityId,
    ).toBe("challenge");
    expect(
      recommendActivities(
        "current",
        [hard, easy],
        wins,
        preferences,
        [...priorities, { subject: null, goal: "support" }],
        false,
      )[0]!.activityId,
    ).toBe("intro");
  });

  it("prioritizes assigned subjects without recommending an already started world", () => {
    const worlds = [
      { id: "favorite", subject: "lengua", theme: "reserve", age_band: "9–12" },
      { id: "priority", subject: "ciencias", theme: "space", age_band: "9–12" },
    ];
    const priorities = [{ subject: "ciencias" as const, goal: "balanced" as const }];
    expect(recommendWorld(worlds, [], preferences, priorities)?.versionId).toBe("priority");
    expect(recommendWorld(worlds, ["priority"], preferences, priorities)?.versionId).toBe(
      "favorite",
    );
    expect(
      recommendWorld(
        worlds,
        worlds.map((w) => w.id),
        preferences,
        priorities,
      ),
    ).toBeNull();
  });
});
