import { NextResponse } from "next/server";
import { q } from "@/lib/db";

export const dynamic = "force-dynamic";

// Health check for a load balancer or uptime monitor. It answers 200 only if the database is
// reachable, and says whether the LiveKit keys are set (without revealing them).
export async function GET() {
  const { LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET } = process.env;
  const voiceConfigured = Boolean(LIVEKIT_URL && LIVEKIT_API_KEY && LIVEKIT_API_SECRET);
  try {
    const [row] = await q("select count(*)::int as sellers from sellers");
    return NextResponse.json({ ok: true, database: "up", sellers: row.sellers, voiceConfigured });
  } catch {
    return NextResponse.json({ ok: false, database: "down", voiceConfigured }, { status: 503 });
  }
}
