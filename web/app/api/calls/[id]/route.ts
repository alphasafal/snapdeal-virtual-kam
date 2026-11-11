import { NextResponse } from "next/server";
import { q } from "@/lib/db";

export const dynamic = "force-dynamic";

// Live state of one call: the page polls this once a second while a call is on.
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const calls = await q("select * from calls where id = $1", [id]);
  if (!calls.length) return NextResponse.json({ error: "Unknown call" }, { status: 404 });
  const call = calls[0];
  const [turns, actions, diagnosis] = await Promise.all([
    q("select id, role, text, at from call_turns where call_id = $1 order by id", [id]),
    q("select id, type, title, detail, expected_recovery_inr, status, progress, due_date from actions where call_id = $1 order by created_at", [id]),
    q("select result, computed_at from diagnoses where seller_id = $1", [call.seller_id]),
  ]);
  return NextResponse.json({ call, turns, actions, diagnosis: diagnosis[0]?.result ?? null });
}
