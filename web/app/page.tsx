// Home page: three detailed mock sellers to call, a link to the full portfolio, the
// "try your own numbers" form, and a short explanation of what happens on a call.
import Link from "next/link";
import { q } from "@/lib/db";
import { causeLabel, inr, pct } from "@/lib/format";
import OwnNumbersForm from "@/components/OwnNumbersForm";

export const dynamic = "force-dynamic";

export default async function Home() {
  const sellers = await q(`
    select s.id, s.name, s.owner_name, s.city, s.category, s.is_custom,
           p.sales as sales_prev, c.sales as sales_curr, d.risk_level, d.primary_cause,
           d.gap_inr, d.result->'causes' as causes
    from sellers s
    join monthly_metrics p on p.seller_id = s.id and p.period = 'prev'
    join monthly_metrics c on c.seller_id = s.id and c.period = 'curr'
    left join diagnoses d on d.seller_id = s.id
    order by s.is_custom, s.id`);
  const portfolio = sellers.filter((s) => !s.is_custom);
  const demo = portfolio.filter((s) => ["S1", "S2", "S3"].includes(s.id));   // one seller per root cause
  const custom = sellers.filter((s) => s.is_custom).slice(-6);
  // The hero shows the seller from the assignment brief, with the diagnosis already done.
  const brief = portfolio.find((s) => s.id === "S1" && Number(s.gap_inr) > 0);
  const briefCauses: { key: string; title: string; impact_inr: number; share_pct: number }[] =
    (brief?.causes ?? []).filter((c: any) => c.impact_inr > 0);

  return (
    <>
      <section className="hero">
        <div>
          <h1>A voice account manager that finds why a seller's sales fell, and fixes it on the call.</h1>
          <p>
            Pick a seller and speak to Asha in English or Hinglish. She has already studied the account,
            asks only what the data cannot tell her, and acts when the seller says yes.
          </p>
        </div>
        {brief && (
          <div className="card herocard">
            <div className="muted small">Before the phone rings, Asha already knows this about {brief.name}</div>
            <div className="lost">{inr(brief.gap_inr)} <span>of sales lost this month</span></div>
            <div className="splitbar">
              {briefCauses.map((c, i) => (
                <span key={c.key} className={`seg s${i}`} style={{ width: `${c.share_pct}%` }}>{c.share_pct >= 18 ? inr(c.impact_inr) : ""}</span>
              ))}
            </div>
            <ul className="legend">
              {briefCauses.map((c, i) => (
                <li key={c.key}><i className={`s${i}`} />{c.title}<b>{c.share_pct}%</b></li>
              ))}
            </ul>
            <div className="row" style={{ marginTop: 14 }}>
              <Link className="btn primary" href={`/seller/${brief.id}`}>Call as this seller</Link>
              <Link className="btn" href={`/seller/${brief.id}/plan`}>See the plan</Link>
            </div>
          </div>
        )}
      </section>

      <div className="card sellers">
        {demo.map((s) => (
          <div className="srow" key={s.id}>
            <div>
              <div className="name">{s.name}</div>
              <div className="muted small">{s.owner_name}, {s.category}, {s.city}</div>
            </div>
            <div>
              <div className="fig">{inr(s.sales_prev)} to {inr(s.sales_curr)} <span className="down">{pct(s.sales_prev, s.sales_curr)}</span></div>
              <div className="muted small">Sales, last month to this month{s.id === "S1" ? " (the brief's data)" : ""}</div>
            </div>
            <div>
              <div>{causeLabel(s.primary_cause)}</div>
              <div className="muted small">Main cause found</div>
            </div>
            <div className="row">
              <Link className="btn primary" href={`/seller/${s.id}`}>Call as this seller</Link>
              <Link className="btn" href={`/seller/${s.id}?direction=proactive`}>Have Asha call</Link>
            </div>
          </div>
        ))}
      </div>
      {portfolio.length > demo.length && (
        <p className="muted small" style={{ marginTop: 10 }}>
          These three have different root causes. The portfolio has {portfolio.length} sellers:{" "}
          <Link href="/dashboard">see the call queue ranked by the rupees Asha could win back</Link>.
        </p>
      )}

      <div className="two">
        <div className="card">
          <h2>Try your own numbers</h2>
          <p className="muted small" style={{ marginBottom: 14 }}>
            Enter any seller's two months. Asha diagnoses that seller on the call, so you can check the reasoning is not scripted.
          </p>
          <OwnNumbersForm />
        </div>
        <div className="card">
          <h2>What happens on a call</h2>
          <ol className="steps">
            <li>Code ranks the causes of the drop in rupees before Asha says a word.</li>
            <li>She tells the seller what she found and asks what only they can know.</li>
            <li>She proposes actions that fit that seller. Nothing is saved until the seller says yes.</li>
            <li>She books a follow-up, and the next call opens with what was agreed.</li>
          </ol>
          <p className="small" style={{ marginTop: 12 }}><Link href="/how-it-works">How it works, models used and what is mocked</Link></p>
          {custom.length > 0 && (
            <>
              <h3 style={{ marginTop: 18, marginBottom: 6 }}>Sellers you entered</h3>
              {custom.map((s) => (
                <div key={s.id} className="row small" style={{ marginBottom: 4 }}>
                  <Link href={`/seller/${s.id}`}>{s.name}</Link>
                  <span className="muted num">{inr(s.sales_prev)} to {inr(s.sales_curr)}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </>
  );
}
