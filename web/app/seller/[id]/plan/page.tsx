// What-if planner for one seller. The server part (this file) loads the seller's numbers and
// the options stored by the nightly scan; components/Planner.tsx does the ticking and adding up.
import Link from "next/link";
import { notFound } from "next/navigation";
import { ensurePlans, q } from "@/lib/db";
import { inr, pct } from "@/lib/format";
import Planner, { PlanOption } from "@/components/Planner";

export const dynamic = "force-dynamic";

export default async function PlanPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await ensurePlans();
  const sellers = await q("select * from sellers where id = $1", [id]);
  if (!sellers.length) notFound();
  const seller = sellers[0];
  const metrics = await q("select period, sales from monthly_metrics where seller_id = $1", [id]);
  const prev = metrics.find((m) => m.period === "prev");
  const curr = metrics.find((m) => m.period === "curr");
  if (!prev || !curr) notFound();
  const [plan] = await q("select * from plans where seller_id = $1", [id]);
  const [diagnosis] = await q("select headline from diagnoses where seller_id = $1", [id]);
  const options: PlanOption[] = plan?.options ?? [];
  const gap = Number(plan?.gap_inr ?? 0);

  return (
    <>
      <div className="sellerhead">
        <h1>What-if planner</h1>
        <span className="muted">{seller.name}, {seller.category}, {seller.city}</span>
      </div>
      <p className="muted" style={{ maxWidth: "70ch", marginBottom: 18 }}>
        {diagnosis?.headline ?? `Sales: ${inr(prev.sales)} last month, ${inr(curr.sales)} this month (${pct(prev.sales, curr.sales)}).`}
      </p>

      {!plan && (
        <div className="card">
          <p>No plan has been worked out for this seller yet. Plans are produced by the nightly scan
            (<code>python -m brain.jobs</code> in the agent folder).</p>
          <p style={{ marginTop: 12 }}><Link className="btn" href={`/seller/${id}`}>Back to the seller page</Link></p>
        </div>
      )}
      {plan && options.length === 0 && (
        <div className="card">
          <p>Sales did not fall for this seller, so there is nothing to recover. Asha will not invent a problem.</p>
          <p style={{ marginTop: 12 }}><Link className="btn" href="/dashboard">Back to the call queue</Link></p>
        </div>
      )}
      {plan && options.length > 0 && (
        <Planner sellerId={id} salesPrev={Number(prev.sales)} salesCurr={Number(curr.sales)} gap={gap} options={options} />
      )}
    </>
  );
}
