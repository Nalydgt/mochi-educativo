import { afterEach, describe, expect, it, vi } from "vitest";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/integrations/supabase/types";

const query = vi.hoisted(() => vi.fn());
vi.mock("@/lib/education/db.server", () => ({ db: () => query }));
import { cleanupLearningFiles, resetLearningData } from "@/lib/education/privacy.server";

const file = { id: "file-1", storage_path: "adult/notebook/file.pdf" };
const queued = { result: { pendingFiles: 1, files: [file] } };
function storage(remove: ReturnType<typeof vi.fn>) {
  return {
    storage: { from: vi.fn().mockReturnValue({ remove }) },
  } as unknown as SupabaseClient<Database>;
}

afterEach(() => vi.resetAllMocks());

describe("durable privacy cleanup", () => {
  it("keeps a failed file removal queued and acknowledges it only after a successful retry", async () => {
    query.mockResolvedValueOnce([queued]);
    const remove = vi.fn().mockResolvedValueOnce({ error: new Error("Storage unavailable") });
    const client = storage(remove);
    expect(await cleanupLearningFiles("adult", client)).toBe(1);
    expect(query).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith([file.storage_path]);

    query
      .mockResolvedValueOnce([queued])
      .mockResolvedValueOnce([{ result: { pendingFiles: 0, files: [] } }]);
    remove.mockResolvedValueOnce({ error: null });
    expect(await cleanupLearningFiles("adult", client)).toBe(0);
    expect(query).toHaveBeenLastCalledWith(expect.any(Array), "adult", [file.id]);
  });

  it("reports committed data deletion and pending files when Storage fails", async () => {
    query
      .mockResolvedValueOnce([{ result: { homeLearners: 2, legacyLearners: 1, pendingFiles: 1 } }])
      .mockResolvedValueOnce([queued]);
    const client = storage(vi.fn().mockRejectedValue(new Error("Connection lost")));
    expect(await resetLearningData("adult", client, "request")).toEqual({
      ok: true,
      homeLearners: 2,
      legacyLearners: 1,
      pendingFiles: 1,
    });
    expect(query).toHaveBeenCalledTimes(2);
  });
});
