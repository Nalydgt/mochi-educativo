import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StudentCodeEntry } from "@/components/education/StudentAccess";
import { studentAccessCommand } from "@/lib/education/student-access";
import { studentCodeExpiry } from "@/lib/education/student-access.server";

const pupil = { id: "30000000-0000-4000-8000-000000000001", name: "Iris", color: "mint" } as const;

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("student access", () => {
  it("requires a duration, supports an indefinite code and validates a custom future date", () => {
    const command = { action: "issue", learnerId: pupil.id };
    const now = Date.parse("2026-11-01T10:30:00Z");
    expect(studentAccessCommand.safeParse(command).success).toBe(false);
    expect(studentAccessCommand.safeParse({ ...command, duration: "custom" }).success).toBe(false);
    expect(studentAccessCommand.safeParse({ ...command, duration: "unlimited" }).success).toBe(
      true,
    );
    expect(studentCodeExpiry("unlimited", undefined, now)).toBeNull();
    expect(studentCodeExpiry("24h", undefined, now)).toBe("2026-11-02T10:30:00.000Z");
    expect(studentCodeExpiry("7d", undefined, now)).toBe("2026-11-08T10:30:00.000Z");
    expect(studentCodeExpiry("30d", undefined, now)).toBe("2026-12-01T10:30:00.000Z");
    expect(studentCodeExpiry("custom", "2026-11-02T09:30:00+01:00", now)).toBe(
      "2026-11-02T08:30:00.000Z",
    );
    expect(() => studentCodeExpiry("custom", "2026-11-01T10:30:00Z", now)).toThrow("fecha futura");
  });

  it("remembers only the opted-in visual profile and still verifies its code on a new session", async () => {
    const onCode = vi.fn().mockResolvedValue(pupil);
    const initial = render(<StudentCodeEntry busy={false} error="" onCode={onCode} />);
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Recordarme en este dispositivo privado" }),
    );
    fireEvent.change(screen.getByLabelText("Tu código de explorador"), {
      target: { value: "ABCD-EFGH-JKLM" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Abrir mi mundo" }));
    await waitFor(() => expect(localStorage.length).toBe(1));
    expect(onCode).toHaveBeenLastCalledWith("ABCDEFGHJKLM", { remember: true });
    expect(localStorage.getItem(localStorage.key(0)!)).not.toContain("ABCDEFGHJKLM");
    initial.unmount();

    render(<StudentCodeEntry busy={false} error="" onCode={onCode} />);
    fireEvent.click(await screen.findByText("Iris"));
    const code = screen.getByLabelText("Código de Iris");
    expect(code).toHaveFocus();
    fireEvent.change(code, { target: { value: "ABCD-EFGH-JKLM" } });
    fireEvent.click(screen.getByRole("button", { name: "Abrir mi mundo" }));
    await waitFor(() =>
      expect(onCode).toHaveBeenLastCalledWith("ABCDEFGHJKLM", {
        remember: true,
        learnerId: pupil.id,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Olvidar el perfil de Iris" }));
    expect(localStorage.length).toBe(0);
  });
});
