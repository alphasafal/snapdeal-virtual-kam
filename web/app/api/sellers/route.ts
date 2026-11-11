import { NextResponse } from "next/server";
import { newId, q } from "@/lib/db";

export const dynamic = "force-dynamic";

const num = (v: unknown) => (v === "" || v === null || v === undefined ? NaN : Number(v));

// "Try your own numbers": stores a seller with two months of metrics.
// The diagnosis itself is always computed by the Python engine when the call starts.
export async function POST(req: Request) {
  const b = await req.json().catch(() => ({}));
  const months = ["prev", "curr"].map((p) => ({
    period: p,
    sales: num(b[`${p}_sales`]),
    orders: num(b[`${p}_orders`]),
    cancel: num(b[`${p}_cancel`]),
    oos: num(b[`${p}_oos`]),
  }));
  for (const m of months) {
    if (![m.sales, m.orders, m.cancel, m.oos].every((x) => Number.isFinite(x) && x >= 0) || m.orders < 1 || m.cancel > 100) {
      return NextResponse.json({ error: "Enter valid numbers for both months (orders at least 1, cancellation 0 to 100)." }, { status: 400 });
    }
  }
  const catalogue = Number.isFinite(num(b.catalogue_size)) && num(b.catalogue_size) > 0 ? Math.round(num(b.catalogue_size)) : null;
  const id = newId("C").toUpperCase();
  const name = String(b.name || "Custom seller").slice(0, 60);
  const owner = String(b.owner_name || "Seller").slice(0, 40);
  await q(
    `insert into sellers (id, name, owner_name, city, category, catalogue_size, is_custom, created_at)
     values ($1, $2, $3, $4, $5, $6, true, now())`,
    [id, name, owner, String(b.city || "India").slice(0, 40), String(b.category || "General").slice(0, 40), catalogue]
  );
  for (const m of months) {
    await q(
      `insert into monthly_metrics (seller_id, period, sales, orders, cancel_rate, asp, oos_products)
       values ($1, $2, $3, $4, $5, $6, $7)`,
      [id, m.period, m.sales, Math.round(m.orders), m.cancel, m.sales / m.orders, Math.round(m.oos)]
    );
  }
  return NextResponse.json({ id });
}
