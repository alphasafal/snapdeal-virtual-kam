import { NextResponse } from "next/server";
import { q } from "@/lib/db";

export const dynamic = "force-dynamic";

// Demo helper: pretend a week passed since the seller's last call.
// Two thirds of the restock list arrives; one-step actions are marked done.
// This lets the next call show the agent remembering and checking progress.
export async function POST(req: Request) {
  const { sellerId } = await req.json().catch(() => ({}));
  const calls = await q(
    `select c.id from calls c where c.seller_id = $1 and c.status = 'ended'
       and exists (select 1 from actions a where a.call_id = c.id and a.status <> 'cancelled')
     order by c.ended_at desc limit 1`,
    [sellerId]
  );
  if (!calls.length) return NextResponse.json({ error: "No finished call with agreed actions for this seller yet." }, { status: 400 });
  const callId = calls[0].id;
  await q("update calls set started_at = started_at - interval '7 days', ended_at = ended_at - interval '7 days' where id = $1", [callId]);

  const actions = await q("select id, type, detail from actions where call_id = $1 and status <> 'cancelled'", [callId]);
  const notes: string[] = [];
  for (const a of actions) {
    if (a.type === "restock_plan") {
      const products: { id: string; name: string }[] = a.detail?.products ?? [];
      const arrived = products.slice(0, Math.ceil((products.length * 2) / 3));
      const pending = products.slice(arrived.length);
      if (arrived.length) {
        await q("update products set in_stock = true where id = any($1)", [arrived.map((p) => p.id)]);
      }
      const progress = pending.length
        ? `${arrived.length} of ${products.length} products back in stock; still pending: ${pending.map((p) => p.name).join(", ")}`
        : `all ${products.length} products back in stock`;
      await q("update actions set status = $2, progress = $3 where id = $1", [a.id, pending.length ? "partly_done" : "done", progress]);
      notes.push(progress);
    } else if (a.type !== "followup") {
      await q("update actions set status = 'done', progress = 'done' where id = $1", [a.id]);
    }
  }
  await q("update followups set status = 'due' where call_id = $1", [callId]);
  return NextResponse.json({ ok: true, notes });
}
