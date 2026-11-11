// Team dashboard: the call queue (every seller the nightly scan flagged, ranked by the rupees
// that could be won back), headline numbers, and every call with its review status.
// Calls where the seller never spoke are left out.
import Link from "next/link";
import { ensurePlans, ensureReviews, q } from "@/lib/db";
import { causeLabel, day, inr, shortDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  await Promise.all([ensureReviews(), ensurePlans()]);
  // A call left "live" because its worker died is closed, so this page stays truthful.
  await q(`update calls set status = 'ended', ended_at = now(),
             summary = '{"issue": "This call ended without a record (the worker stopped).", "ended_reason": "connection_problem", "actions": [], "causes": []}'
           where status = 'live' and started_at < now() - interval '30 minutes'`);
  const [attention, calls, totals, portfolioRows] = await Promise.all([
    q(`select s.id, s.name, s.city, s.category, d.risk_level, d.primary_cause, d.gap_inr,
              coalesce(p.recoverable_inr, 0) as recoverable,
              (select max(ended_at) from calls c where c.seller_id = s.id and c.status = 'ended') as last_call,
              (select min(due_date) from followups f where f.seller_id = s.id and f.status in ('scheduled','due')) as next_followup
       from diagnoses d join sellers s on s.id = d.seller_id left join plans p on p.seller_id = s.id
       where d.gap_inr > 0 order by coalesce(p.recoverable_inr, 0) desc, d.gap_inr desc limit 25`),
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
    q(`select count(*) as sellers,
              count(*) filter (where d.gap_inr > 0) as falling,
              count(*) filter (where d.risk_level = 'high') as high_risk,
              coalesce(sum(d.gap_inr), 0) as lost,
              coalesce(sum(p.recoverable_inr), 0) as recoverable,
              count(*) filter (where d.gap_inr > 0 and not exists
                (select 1 from calls c where c.seller_id = s.id and c.status = 'ended')) as never_called
       from sellers s join diagnoses d on d.seller_id = s.id left join plans p on p.seller_id = s.id
       where not s.is_custom`),
  ]);
  const t = totals[0];
  const portfolio = portfolioRows[0];

  return (
    <>
      <h1>Team dashboard</h1>
      <p className="muted" style={{ marginTop: 8, maxWidth: "62ch" }}>
        Who to call first, what Asha did on each call, and what it cost. Open any call to read it in full and sign it off.
      </p>

      <div className="stats">
        <div><b>{portfolio.sellers}</b><span>Sellers monitored</span></div>
        <div><b>{portfolio.falling}</b><span>With falling sales</span></div>
        <div><b>{portfolio.high_risk}</b><span>High risk</span></div>
        <div><b>{portfolio.never_called}</b><span>Not called yet</span></div>
        <div><b>{inr(portfolio.lost)}</b><span>Sales lost this month</span></div>
        <div><b style={{ color: "var(--green)" }}>{inr(portfolio.recoverable)}</b><span>Could be won back each month (upper limit)</span></div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Call queue</h2>
        <p className="muted small" style={{ marginBottom: 8 }}>
          From the nightly scan, ranked by the sales that could be won back. Asha can call these sellers before they call us.
        </p>
        <div className="scroll">
          <table>
            <thead><tr><th className="num">#</th><th>Seller</th><th>Risk</th><th>Main cause</th><th className="num">Sales drop</th><th className="num">Could win back</th><th>Last call</th><th>Next follow-up</th><th /></tr></thead>
            <tbody>
              {attention.map((s, i) => (
                <tr key={s.id}>
                  <td className="num muted">{i + 1}</td>
                  <td><Link href={`/seller/${s.id}`}>{s.name}</Link><div className="muted small">{s.category}, {s.city}</div></td>
                  <td><span className={`pill ${s.risk_level}`}>{s.risk_level}</span></td>
                  <td>{causeLabel(s.primary_cause)}</td>
                  <td className="num">{inr(s.gap_inr)}</td>
                  <td className="num" style={{ color: "var(--green)", fontWeight: 600 }}>{Number(s.recoverable) ? `up to ${inr(s.recoverable)}` : ""}</td>
                  <td>{s.last_call ? shortDate(s.last_call) : <span className="muted">Never</span>}</td>
                  <td>{s.next_followup ? day(s.next_followup) : <span className="muted">None</span>}</td>
                  <td className="row" style={{ flexWrap: "nowrap" }}>
                    <Link className="btn" href={`/seller/${s.id}/plan`}>Plan</Link>
                    <Link className="btn primary" href={`/seller/${s.id}?direction=proactive`}>Have Asha call</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2 style={{ margin: "26px 0 0" }}>Calls so far</h2>
      <div className="stats" style={{ marginTop: 12 }}>
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
    </>
  );
}
