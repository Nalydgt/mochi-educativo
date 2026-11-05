import { describe, it, expect } from "vitest";
import { guestOrderSchema, isSoldOut, ENTITLED } from "@/lib/billing-schema";
const base = {
  requestKey: crypto.randomUUID(),
  name: "Ana Pérez",
  email: "ana@example.com",
  items: [{ productId: crypto.randomUUID(), quantity: 1 }],
};
describe("billing rules", () => {
  it("guest orders need name, email and items", () => {
    expect(guestOrderSchema.safeParse(base).success).toBe(true);
    expect(guestOrderSchema.safeParse({ ...base, email: "x" }).success).toBe(false);
    expect(guestOrderSchema.safeParse({ ...base, items: [] }).success).toBe(false);
  });
  it("zero stock is sold out", () => {
    expect(isSoldOut({ stock: 0 })).toBe(true);
    expect(isSoldOut({ stock: 1 })).toBe(false);
  });
  it("only active or trialing subscriptions grant access", () => {
    expect(ENTITLED).not.toContain("past_due");
    expect(ENTITLED).toContain("active");
  });
});
