import { z } from "zod";

export const guestOrderSchema = z.object({
  requestKey: z.string().uuid(),
  name: z.string().trim().min(2).max(120),
  email: z.string().trim().email().max(200),
  items: z
    .array(z.object({ productId: z.string().uuid(), quantity: z.number().int().min(1).max(10) }))
    .min(1)
    .max(10),
});

export const adminBillingSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("plan"), id: z.string().uuid(), is_active: z.boolean() }),
  z.object({
    kind: z.literal("price"),
    id: z.string().uuid(),
    unit_amount: z.number().int().positive().nullable(),
    is_active: z.boolean(),
  }),
  z.object({
    kind: z.literal("product"),
    id: z.string().uuid(),
    unit_amount: z.number().int().positive().nullable(),
    stock: z.number().int().min(0),
    is_active: z.boolean(),
  }),
]);

export const ENTITLED = ["active", "trialing"];
export const isSoldOut = (p: { stock: number }) => p.stock <= 0;
export const formatMoney = (cents: number | null, currency: string) =>
  cents == null
    ? "Precio no disponible"
    : new Intl.NumberFormat("es-ES", {
        style: "currency",
        currency: currency.toUpperCase(),
      }).format(cents / 100);
