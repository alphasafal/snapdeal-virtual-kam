import { NextResponse } from "next/server";
import { ensureReviews, q } from "@/lib/db";

export const dynamic = "force-dynamic";

// A team member signs off a finished call, or flags it for follow-up.
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = await req.json().catch(() => ({}));
  const verdict = body.verdict === "needs_followup" ? "needs_followup" : body.verdict === "ok" ? "ok" : null;
  if (!verdict) return NextResponse.json({ error: "Choose a verdict." }, { status: 400 });
  const call = await q("select id from calls where id = $1 and status = 'ended'", [id]);
  if (!call.length) return NextResponse.json({ error: "Only finished calls can be reviewed." }, { status: 404 });
  await ensureReviews();
  await q(
    `insert into call_reviews (call_id, verdict, reviewer, note, reviewed_at) values ($1, $2, $3, $4, now())
     on conflict (call_id) do update set verdict = excluded.verdict, reviewer = excluded.reviewer,
       note = excluded.note, reviewed_at = now()`,
    [id, verdict, String(body.reviewer || "").slice(0, 60) || null, String(body.note || "").slice(0, 1000) || null]
  );
  return NextResponse.json({ ok: true });
}
