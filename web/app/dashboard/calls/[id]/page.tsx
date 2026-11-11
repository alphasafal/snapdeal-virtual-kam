// The full record of one call, for a person on the team: summary, every action (including
// cancelled ones), the whole conversation, the automatic figure check, and the review form.
import Link from "next/link";
import { notFound } from "next/navigation";
import { ensureReviews, q } from "@/lib/db";
import { causeLabel, day, inr, shortDate, withoutRepeats } from "@/lib/format";
import ReviewForm from "@/components/ReviewForm";

export const dynamic = "force-dynamic";

// Everything about one call, for a person on the team who wants to check Asha's work.
export default async function CallDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await ensureReviews();
  const calls = await q(
    `select c.*, s.name as seller_name, s.owner_name, s.city from calls c join sellers s on s.id = c.seller_id where c.id = $1`, [id]);
  if (!calls.length) notFound();
  const call = calls[0];
  const [allTurns, actions, reviews] = await Promise.all([
    q("select id, role, text, at from call_turns where call_id = $1 order by id", [id]),
    q("select * from actions where call_id = $1 order by created_at", [id]),
    q("select * from call_reviews where call_id = $1", [id]),
  ]);
  const turns = withoutRepeats(allTurns);
  const review = reviews[0] ?? null;
  const summary = call.summary ?? {};
  const notes: Record<string, string> = call.notes ?? {};
  const firstName = String(call.owner_name).split(" ")[0];
  const kept = actions.filter((a) => a.status !== "cancelled");
  const total = kept.reduce((sum, a) => sum + (a.expected_recovery_inr ?? 0), 0);
  const audit = summary.audit as { figures_checked: number; flags: { said: string; value: number; in: string }[] } | undefined;
  const facts: [string, string][] = [
    ["When", shortDate(call.started_at)],
    ["Type", call.direction === "proactive" ? "Asha called the seller" : "Seller called Asha"],
    ["Voice and language", `${call.voice_mode ?? "not recorded"}, ${call.language === "hinglish" ? "Hinglish" : "English"}`],
    ["Length", call.duration_s ? `${call.duration_s} seconds` : "not recorded"],
    ["Cost to run (estimate)", call.est_cost_inr ? `₹${Number(call.est_cost_inr).toFixed(2)}` : "not recorded"],
    ["Reply delay (average)", call.avg_latency_ms ? `${(call.avg_latency_ms / 1000).toFixed(1)} seconds` : "not recorded"],
    ["Root cause found", causeLabel(call.root_cause)],
  ];

  return (
    <>
      <p className="small"><Link href="/dashboard">Back to the team dashboard</Link></p>
      <div className="sellerhead" style={{ marginTop: 8 }}>
        <h1>Call with {call.seller_name}</h1>
        {review ? <span className={`pill ${review.verdict === "ok" ? "done" : "medium"}`}>{review.verdict === "ok" ? "Reviewed" : "Flagged for follow-up"}</span>
          : call.status === "ended" ? <span className="pill plain">Not reviewed yet</span> : <span className="pill live">Live now</span>}
        {call.escalated && <span className="pill high">Escalated to a human</span>}
        {summary.ended_reason === "connection_problem" && <span className="pill high">Dropped: connection problem</span>}
        {audit && audit.flags.length > 0 && <span className="pill medium">Figures to check</span>}
      </div>

      <div className="stage">
        <section className="stack">
          <div className="card">
            <h2>Summary</h2>
            <p>{summary.issue ?? "No summary was saved for this call."}</p>
            {Array.isArray(summary.causes) && summary.causes.length > 0 && (
              <ul className="clean">{summary.causes.map((c: string) => <li key={c}>{c}</li>)}</ul>
            )}
            {summary.followup_date && <p style={{ marginTop: 10 }}>Follow-up call on {day(summary.followup_date)}.</p>}
          </div>

          <div className="card">
            <h2>What Asha did</h2>
            {actions.length === 0 && <p className="muted">No actions were agreed on this call.</p>}
            {actions.map((a) => (
              <div className="entry" key={a.id} style={{ animation: "none", opacity: a.status === "cancelled" ? 0.6 : 1 }}>
                <span className="tick" aria-hidden style={a.status === "cancelled" ? { background: "var(--ink-3)" } : undefined}>{a.status === "cancelled" ? "×" : "✓"}</span>
                <div>
                  <b style={a.status === "cancelled" ? { textDecoration: "line-through" } : undefined}>{a.title}</b>
                  {Array.isArray(a.detail?.products) && <div className="muted small">{a.detail.products.map((p: any) => p.name).join(", ")}</div>}
                  {a.detail?.reason && <div className="muted small">Reason: {a.detail.reason}</div>}
                  {a.detail?.note && <div className="muted small">{a.detail.note}</div>}
                  <div className="muted small">{a.due_date && a.status !== "cancelled" ? `Due ${day(a.due_date)}. ` : ""}Status: {a.progress ?? a.status.replace("_", " ")}</div>
                </div>
                <span className="amt">{a.expected_recovery_inr && a.status !== "cancelled" ? `up to ${inr(a.expected_recovery_inr)}` : ""}</span>
              </div>
            ))}
            {total > 0 && <div className="total"><span>Sales this could recover each month</span><span className="num">up to {inr(total)}</span></div>}
          </div>

          <div className="card">
            <h2>Full conversation</h2>
            <div className="talk" style={{ maxHeight: "none" }}>
              {turns.length === 0 && <p className="muted">Nothing was said on this call.</p>}
              {turns.map((t) => t.role === "tool"
                ? <div key={t.id} className="did">{t.text}</div>
                : <div key={t.id} className={`turn ${t.role}`}><small>{t.role === "agent" ? "Asha" : firstName}</small>{t.text}</div>)}
            </div>
          </div>
        </section>

        <section className="stack">
          <div className="card">
            <h2>Human review</h2>
            {review && (
              <p style={{ marginBottom: 12 }}>
                {review.verdict === "ok" ? "Reviewed" : "Flagged for follow-up"}{review.reviewer ? ` by ${review.reviewer}` : ""} on {shortDate(review.reviewed_at)}.
                {review.note ? ` Note: ${review.note}` : ""}
              </p>
            )}
            {call.status === "ended"
              ? <ReviewForm callId={call.id} current={review as any} />
              : <p className="muted">This call is still in progress. It can be reviewed once it ends.</p>}
          </div>

          <div className="card">
            <h2>Automatic figure check</h2>
            {!audit && <p className="muted">Not run for this call.</p>}
            {audit && audit.flags.length === 0 && (
              <p>{audit.figures_checked > 0
                ? `Asha spoke ${audit.figures_checked} rupee figures. Every one matches the account data or a tool result.`
                : "Asha spoke no rupee figures on this call."}</p>
            )}
            {audit && audit.flags.length > 0 && (
              <>
                <p>{audit.flags.length} of {audit.figures_checked} spoken figures match nothing in the account data. Please check them.</p>
                <ul className="clean">
                  {audit.flags.map((f) => <li key={f.value}><b>{inr(f.value)}</b> ("{f.said}") in: <span className="muted">{f.in}</span></li>)}
                </ul>
              </>
            )}
            <p className="muted small" style={{ marginTop: 8 }}>Checks amounts of ₹1,000 and above in English, Hindi and Hinglish. It cannot judge whether a correct figure was used with the right meaning.</p>
          </div>

          <div className="card">
            <h2>Call details</h2>
            <table><tbody>{facts.map(([k, v]) => <tr key={k}><td className="muted">{k}</td><td>{v}</td></tr>)}</tbody></table>
          </div>

          {Object.keys(notes).length > 0 && (
            <div className="card">
              <h2>What the seller told Asha</h2>
              <ul className="clean">{Object.entries(notes).map(([k, v]) => <li key={k}><b>{k.replace(/_/g, " ")}:</b> {v}</li>)}</ul>
            </div>
          )}
          <p className="small"><Link href={`/seller/${call.seller_id}`}>Open this seller's call screen</Link></p>
        </section>
      </div>
    </>
  );
}
