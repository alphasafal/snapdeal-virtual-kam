// GET /api/calls/<id>/report
// The whole call record as one text file a team member can download, attach to a ticket or
// hand to the seller's human account manager: summary, what was agreed, the checks, and
// the conversation.
import { NextResponse } from "next/server";
import { ensureReviews, q } from "@/lib/db";
import { causeLabel, day, inr, shortDate, withoutRepeats } from "@/lib/format";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await ensureReviews();
  const calls = await q(
    `select c.*, s.name as seller_name, s.owner_name, s.city from calls c join sellers s on s.id = c.seller_id where c.id = $1`, [id]);
  if (!calls.length) return NextResponse.json({ error: "No such call" }, { status: 404 });
  const call = calls[0];
  const [turns, actions, reviews] = await Promise.all([
    q("select id, role, text from call_turns where call_id = $1 order by id", [id]),
    q("select * from actions where call_id = $1 order by created_at", [id]),
    q("select * from call_reviews where call_id = $1", [id]),
  ]);
  const summary = call.summary ?? {};
  const notes: Record<string, string> = call.notes ?? {};
  const firstName = String(call.owner_name).split(" ")[0];
  // The follow-up is stored as an action too; the report gives it its own line.
  const kept = actions.filter((a) => a.status !== "cancelled" && a.type !== "followup");
  const cancelled = actions.filter((a) => a.status === "cancelled");
  const total = kept.reduce((sum, a) => sum + (a.expected_recovery_inr ?? 0), 0);

  const out: string[] = [
    `# Call with ${call.seller_name} (${call.owner_name}, ${call.city})`,
    "",
    `- When: ${shortDate(call.started_at)}`,
    `- Type: ${call.direction === "proactive" ? "Asha called the seller" : "The seller called Asha"}`,
    `- Voice and language: ${call.voice_mode ?? "not recorded"}, ${call.language === "hinglish" ? "Hinglish" : "English"}`,
    `- Length: ${call.duration_s ? `${call.duration_s} seconds` : "not recorded"}`,
    `- Root cause found: ${causeLabel(call.root_cause)}`,
    "",
    "## Summary",
    "",
    summary.issue ?? "No summary was saved for this call.",
    ...(summary.causes ?? []).map((c: string) => `- ${c}`),
    "",
    "## What was agreed",
    "",
    ...(kept.length ? kept.map((a, i) =>
      `${i + 1}. ${a.title}${a.due_date ? `, by ${day(a.due_date)}` : ""}${a.expected_recovery_inr ? ` (up to ${inr(a.expected_recovery_inr)} a month)` : ""}`)
      : ["Nothing was agreed on this call."]),
    ...(total ? ["", `Sales this could recover each month: up to ${inr(total)}`] : []),
    ...(cancelled.length ? ["", "Removed at the seller's request: " + cancelled.map((a) => a.title).join("; ")] : []),
    ...(summary.followup_date ? ["", `Follow-up call: ${day(summary.followup_date)}`] : []),
  ];

  if (Object.keys(notes).length) {
    out.push("", "## What the seller told Asha", "", ...Object.entries(notes).map(([k, v]) => `- ${k.replace(/_/g, " ")}: ${v}`));
  }

  out.push("", "## Checks", "");
  const audit = summary.audit;
  if (!audit) out.push("- Figure check: not run for this call.");
  else if (!audit.flags?.length) out.push(`- Figure check: ${audit.figures_checked} rupee figures spoken, all match the account data or a tool result.`);
  else out.push(`- Figure check: ${audit.flags.length} of ${audit.figures_checked} spoken figures match nothing in the account data:`,
    ...audit.flags.map((f: { value: number; said: string }) => `  - ${inr(f.value)} ("${f.said}")`));
  const consent = summary.consent;
  if (!consent) out.push("- Consent check: not recorded for this call.");
  else {
    const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
    out.push(`- Consent check: ${count(consent.allowed, "action", "actions")} saved after the seller's clear yes; ` +
      `${count(consent.refused.length, "attempt", "attempts")} refused.`,
      ...consent.refused.map((r: { action: string; why: string; seller_said: string }) => `  - ${r.action}: ${r.why}. The seller had said: "${r.seller_said}"`));
  }
  const review = reviews[0];
  out.push(review
    ? `- Human review: ${review.verdict === "ok" ? "reviewed" : "flagged for follow-up"}${review.reviewer ? ` by ${review.reviewer}` : ""} on ${shortDate(review.reviewed_at)}.${review.note ? ` Note: ${review.note}` : ""}`
    : "- Human review: not reviewed yet.");

  out.push("", "## Conversation", "");
  for (const t of withoutRepeats(turns)) {
    if (t.role === "tool") out.push(`    [${t.text}]`);
    else out.push(`${t.role === "agent" ? "Asha" : firstName}: ${t.text}`);
  }
  out.push("", "Mock data. Prototype for the Snapdeal AI First Intern assignment.", "");

  return new NextResponse(out.join("\n"), {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": `attachment; filename="call-report-${id}.md"`,
    },
  });
}
