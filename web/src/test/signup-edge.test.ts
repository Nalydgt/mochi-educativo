import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import ts from "typescript";
import { beforeEach, describe, expect, it, vi } from "vitest";

const source = readFileSync("supabase/functions/peluqo-pilot-signup/index.ts", "utf8");
const javascript = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
}).outputText;
const origin = "https://peluqo-mundos.vercel.app";
const account = {
  email: "fictional@school.invalid",
  password: "fictitious-password",
  invitation: "A".repeat(24),
  display_name: "Adulto ficticio",
  account_type: "teacher",
  age_band: "18+",
};

describe("deployed adult signup edge contract", () => {
  let handler: (request: Request) => Promise<Response>;
  const network = vi.fn();
  beforeEach(() => {
    network.mockReset();
    const deno = {
      env: {
        get: (key: string) =>
          key === "SUPABASE_URL" ? "https://project.invalid" : "fictional-test-key",
      },
      serve: (work: typeof handler) => {
        handler = work;
      },
    };
    new Function("Deno", "fetch", "crypto", javascript)(deno, network, webcrypto);
  });
  const request = (body: unknown, from = origin) =>
    new Request("https://project.invalid/functions/v1/peluqo-pilot-signup", {
      method: "POST",
      headers: { Origin: from, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  const ok = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  it("rejects minors, non-adult roles and missing invitations before privileged calls", async () => {
    expect((await handler(request({ ...account, age_band: "14–17" }))).status).toBe(400);
    expect((await handler(request({ ...account, account_type: "adult_student" }))).status).toBe(
      400,
    );
    expect((await handler(request({ ...account, invitation: undefined }))).status).toBe(400);
    expect(network).not.toHaveBeenCalled();
  });
  it("never creates a teacher without an available server-issued invitation", async () => {
    network.mockResolvedValueOnce(ok(false));
    expect((await handler(request(account))).status).toBe(400);
    expect(network).toHaveBeenCalledTimes(1);
    expect(network.mock.calls[0]?.[0]).toContain("peluqo_account_invitation_available");
  });
  it("writes role only in server-owned metadata from the validated adult profile", async () => {
    network
      .mockResolvedValueOnce(ok(true))
      .mockResolvedValueOnce(ok({ id: "fictional-created-user" }));
    const response = await handler(
      request({ ...account, app_metadata: { mochi_adult_role: "admin" }, role: "admin" }),
    );
    expect(response.status).toBe(200);
    const creation = JSON.parse(network.mock.calls[1]?.[1].body);
    expect(creation.app_metadata.mochi_adult_role).toBe("teacher");
    expect(creation.app_metadata).not.toHaveProperty("role");
    expect(creation.user_metadata).toEqual({
      display_name: account.display_name,
      account_type: "teacher",
      age_band: "18+",
    });
    expect(creation.email_confirm).toBe(true);
    expect(await response.json()).toEqual({ ok: true });
  });
  it("rejects untrusted origins before checking invitations or credentials", async () => {
    expect((await handler(request(account, "https://foreign.invalid"))).status).toBe(403);
    expect(network).not.toHaveBeenCalled();
  });
  it("cannot activate a pending minor or promote user-editable teacher metadata", async () => {
    network
      .mockResolvedValueOnce(ok(true))
      .mockResolvedValueOnce(ok({ error_code: "email_not_confirmed" }, 400))
      .mockResolvedValueOnce(ok("fictional-user"))
      .mockResolvedValueOnce(
        ok({
          id: "fictional-user",
          user_metadata: { age_band: "9–12", account_type: "teacher" },
          app_metadata: {},
        }),
      );
    const response = await handler(request({ ...account, action: "activate" }));
    expect(response.status).toBe(400);
    expect(network).toHaveBeenCalledTimes(4);
    expect(network.mock.calls.some((call) => call[1]?.method === "PUT")).toBe(false);
  });
  it.each([
    [undefined, "family"],
    ["teacher", "teacher"],
  ])(
    "activation preserves trusted role %s and unrelated app metadata without elevation",
    async (role, expected) => {
      network
        .mockResolvedValueOnce(ok(true))
        .mockResolvedValueOnce(ok({ error_code: "email_not_confirmed" }, 400))
        .mockResolvedValueOnce(ok("fictional-user"))
        .mockResolvedValueOnce(
          ok({
            id: "fictional-user",
            user_metadata: { age_band: "18+", account_type: "teacher" },
            app_metadata: { provider: "email", ...(role ? { mochi_adult_role: role } : {}) },
          }),
        )
        .mockResolvedValueOnce(ok({ id: "fictional-user" }));
      const response = await handler(
        request({ ...account, action: "activate", account_type: "teacher" }),
      );
      expect(response.status).toBe(200);
      const activation = JSON.parse(network.mock.calls[4]?.[1].body);
      expect(activation.app_metadata.mochi_adult_role).toBe(expected);
      expect(activation.app_metadata.provider).toBe("email");
      expect(activation.app_metadata.peluqo_invitation_hash).toMatch(/^[0-9a-f]{64}$/);
    },
  );
});
