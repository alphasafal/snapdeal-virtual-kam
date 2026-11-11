// Team dashboard: headline numbers, every call with its review status, and the sellers the
// nightly scan flagged as needing attention. Calls where the seller never spoke are left out.
import Link from "next/link";
import { ensureReviews, q } from "@/lib/db";
import { causeLabel, day, inr, shortDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  await ensureReviews();
  // A call left "live" because its worker died is closed, so this page stays truthful.
  await q(`update calls set status = 'ended', ended_at = now(),
             summary = '{"issue": "This call ended without a record (the worker stopped).", "ended_reason": "connection_problem", "actions": [], "causes": []}'
           where status = 'live' and started_at < now() - interval '30 minutes'`);
  const [attention, calls, totals] = await Promise.all([
    q(`select s.id, s.name, s.city, d.risk_level, d.primary_cause, d.gap_inr,
              (select max(ended_at) from calls c where c.seller_id = s.id and c.status = 'ended') as last_call,
              (select min(due_date) from followups f where f.seller_id = s.id and f.status in ('scheduled','due')) as next_followup
       from diagnoses d join sellers s on s.id = d.seller_id
       where d.gap_inr > 0 order by d.gap_inr desc limit 25`),
    q(`select c.*, s.name as seller_name, r.verdict,
              (select count(*) from actions a where a.call_id = c.id and a.status <> 'cancelled' and a.type not in ('followup','escalation')) as actions,
              (select coalesce(sum(expected_recovery_inr), 0) from actions a where a.call_id = c.id and a.status <> 'cancelled') as recovery
       from calls c join sellers s on s.id = c.seller_id left join call_reviews r on r.call_id = c.id
       where c.status in ('live','ended')
         and (c.status = 'live' or coalesce(c.summary->>'ended_reason', '') <> 'no_conversation')
       order by c.started_at desc nulls last limit 40`),
    q(`select count(*) filter (where status = 'ended' and coalesce(summary->>'ended_reason', '') <> 'no_conversation') as calls,
              count(*) filter (where escalated) as escalations,
              count(*) filter (where status = 'ended' and coalesce(summary->>'ended_reason', '') <> 'no_conversation'
                               and not exists (select 1 from call_reviews r where r.call_id = calls.id)) as unreviewed,
              avg(est_cost_inr) filter (where status = 'ended' and est_cost_inr > 0) as avg_cost,
              avg(avg_latency_ms) filter (where avg_latency_ms is not null) as avg_latency,
              (select count(*) from actions where status <> 'cancelled' and type not in ('followup','escalation')) as actions,
              (select coalesce(sum(expected_recovery_inr), 0) from actions where status <> 'cancelled') as recovery
       from calls`),
  ]);
  const t = totals[0];

  return (
    <>
      <h1>Team dashboard</h1>
      <p className="muted" style={{ marginTop: 8, maxWidth: "62ch" }}>
        Who needs attention, what Asha did on each call, and what it cost. Open any call to read it in full and sign it off.
      </p>

      <div className="stats">
        <div><b>{t.calls}</b><span>Calls handled</span></div>
        <div><b>{t.unreviewed}</b><span>Waiting for human review</span></div>
        <div><b>{t.actions}</b><span>Actions agreed</span></div>
        <div><b>{inr(t.recovery)}</b><span>Monthly sales targeted</span></div>
        <div><b>{t.avg_cost ? `₹${Number(t.avg_cost).toFixed(2)}` : "n/a"}</b><span>Average cost per call</span></div>
        <div><b>{t.avg_latency ? `${(t.avg_latency / 1000).toFixed(1)}s` : "n/a"}</b><span>Average reply delay</span></div>
        <div><b>{t.escalations}</b><span>Escalated to a human</span></div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Calls</h2>
        {calls.length === 0 && <p className="muted">No calls yet. Start one from the Sellers page.</p>}
        {calls.length > 0 && (
          <div className="scroll">
            <table>
              <thead><tr><th>When</th><th>Seller</th><th>Type</th><th>Root cause</th><th className="num">Actions</th><th className="num">Recovery targeted</th><th className="num">Length</th><th className="num">Cost</th><th>Review</th><th /></tr></thead>
              <tbody>
                {calls.map((c) => (
                  <tr key={c.id}>
                    <td>{shortDate(c.started_at)}</td>
                    <td>{c.seller_name}</td>
                    <td>{c.direction === "proactive" ? "Asha called" : "Seller called"}<div className="muted small">{c.voice_mode ?? ""}{c.language === "hinglish" ? ", Hinglish" : ", English"}</div></td>
                    <td>{causeLabel(c.root_cause)}</td>
                    <td className="num">{c.actions}</td>
                    <td className="num">{Number(c.recovery) ? inr(c.recovery) : ""}</td>
                    <td className="num">{c.duration_s ? `${c.duration_s}s` : ""}</td>
                    <td className="num">{Number(c.est_cost_inr) ? `₹${Number(c.est_cost_inr).toFixed(2)}` : ""}</td>
                    <td>
                      {c.status === "live" ? <span className="pill live">Live now</span>
                        : c.verdict === "ok" ? <span className="pill done">Reviewed</span>
                        : c.verdict === "needs_followup" ? <span className="pill medium">Flagged</span>
                        : <span className="pill plain">Not reviewed</span>}
                      {c.escalated && <div style={{ marginTop: 4 }}><span className="pill high">Escalated</span></div>}
                      {c.summary?.audit?.flags?.length > 0 && <div style={{ marginTop: 4 }}><span className="pill medium">Figures to check</span></div>}
                      {c.summary?.ended_reason === "connection_problem" && <div style={{ marginTop: 4 }}><span className="pill high">Dropped</span></div>}
                    </td>
                    <td><Link className="btn" href={`/dashboard/calls/${c.id}`}>Open call</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Sellers needing attention</h2>
        <p className="muted small" style={{ marginBottom: 8 }}>From the nightly scan. Asha can call these sellers before they call us.</p>
        <div className="scroll">
          <table>
            <thead><tr><th>Seller</th><th>Risk</th><th>Main cause</th><th className="num">Sales drop</th><th>Last call</th><th>Next follow-up</th><th /></tr></thead>
            <tbody>
              {attention.map((s) => (
                <tr key={s.id}>
                  <td><Link href={`/seller/${s.id}`}>{s.name}</Link><div className="muted small">{s.city}</div></td>
                  <td><span className={`pill ${s.risk_level}`}>{s.risk_level}</span></td>
                  <td>{causeLabel(s.primary_cause)}</td>
                  <td className="num">{inr(s.gap_inr)}</td>
                  <td>{s.last_call ? shortDate(s.last_call) : <span className="muted">Never</span>}</td>
                  <td>{s.next_followup ? day(s.next_followup) : <span className="muted">None</span>}</td>
                  <td><Link className="btn" href={`/seller/${s.id}?direction=proactive`}>Have Asha call</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
