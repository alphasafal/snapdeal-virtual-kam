import { NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";
import { newId, q } from "@/lib/db";

export const dynamic = "force-dynamic";

// Creates the call row and a short-lived LiveKit token. The room name is the call id;
// the agent worker joins that room automatically and loads the seller from the call row.
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const sellerId = String(body.sellerId ?? "");
  const direction = body.direction === "proactive" ? "proactive" : "inbound";
  const language = body.language === "hinglish" ? "hinglish" : "en";
  const voice = body.voice === "gemini" ? "gemini" : body.voice === "sarvam" ? "sarvam" : null;

  const seller = await q("select id, owner_name from sellers where id = $1", [sellerId]);
  if (!seller.length) return NextResponse.json({ error: "Unknown seller" }, { status: 404 });

  // Cost guard for a public demo link: every call spends voice minutes.
  const cap = Number(process.env.MAX_CALLS_PER_HOUR ?? 60);
  const recent = await q("select count(*)::int as n from calls where started_at > now() - interval '1 hour'");
  if (recent[0].n >= cap) {
    return NextResponse.json({ error: "The demo is busy right now. Please try again in a few minutes." }, { status: 429 });
  }

  const callId = newId("call");
  await q(
    `insert into calls (id, seller_id, direction, language, voice_mode, status, notes, escalated)
     values ($1, $2, $3, $4, $5, 'created', '{}', false)`,
    [callId, sellerId, direction, language, voice]
  );

  const { LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET } = process.env;
  if (!LIVEKIT_URL || !LIVEKIT_API_KEY || !LIVEKIT_API_SECRET) {
    return NextResponse.json(
      { callId, error: "LiveKit keys are not set on the server (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)." },
      { status: 503 }
    );
  }
  const at = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
    identity: `seller-${sellerId}-${callId.slice(-4)}`,
    name: seller[0].owner_name,
    ttl: "15m",
  });
  at.addGrant({ roomJoin: true, room: callId, canPublish: true, canSubscribe: true });
  return NextResponse.json({ callId, url: LIVEKIT_URL, token: await at.toJwt() });
}
