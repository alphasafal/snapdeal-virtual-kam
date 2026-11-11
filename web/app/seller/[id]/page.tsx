// One seller's page. The server part (this file) loads the seller's numbers and earlier calls;
// the live call itself is handled in the browser by components/CallScreen.tsx.
import Link from "next/link";
import { notFound } from "next/navigation";
import { q } from "@/lib/db";
import { causeLabel, inr, pct, shortDate } from "@/lib/format";
import CallScreen from "@/components/CallScreen";

export const dynamic = "force-dynamic";

export default async function SellerPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ direction?: string }>;
}) {
  const { id } = await params;
  const { direction } = await searchParams;
  const sellers = await q("select * from sellers where id = $1", [id]);
  if (!sellers.length) notFound();
  const seller = sellers[0];
  const metrics = await q("select * from monthly_metrics where seller_id = $1", [id]);
  const prev = metrics.find((m) => m.period === "prev");
  const curr = metrics.find((m) => m.period === "curr");
  if (!prev || !curr) notFound();
  const history = await q(
    `select c.id, c.ended_at, c.direction, c.root_cause,
            (select count(*) from actions a where a.call_id = c.id and a.status <> 'cancelled' and a.type not in ('followup','escalation')) as actions
     from calls c where c.seller_id = $1 and c.status = 'ended'
       and coalesce(c.summary->>'ended_reason', '') <> 'no_conversation'
     order by c.ended_at desc limit 5`, [id]);

  const oosChange = curr.oos_products - prev.oos_products;
  const rows: [string, string, string, string][] = [
    ["Sales", inr(prev.sales), inr(curr.sales), pct(prev.sales, curr.sales)],
    ["Orders", String(prev.orders), String(curr.orders), pct(prev.orders, curr.orders)],
    ["Cancellation rate", `${prev.cancel_rate}%`, `${curr.cancel_rate}%`, `${(curr.cancel_rate - prev.cancel_rate).toFixed(1)} pts`],
    ["Average selling price", inr(prev.asp), inr(curr.asp), pct(prev.asp, curr.asp)],
    ["Out-of-stock products", String(prev.oos_products), String(curr.oos_products), `${oosChange >= 0 ? "+" : ""}${oosChange}`],
  ];

  const dataCard = (
    <div className="card">
      <h2>Seller data</h2>
      <div className="scroll">
        <table>
          <thead><tr><th>Metric</th><th className="num">Last month</th><th className="num">This month</th><th className="num">Change</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r[0]}><td>{r[0]}</td><td className="num">{r[1]}</td><td className="num">{r[2]}</td><td className="num muted">{r[3]}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {seller.id === "S1" && <p className="muted small" style={{ marginTop: 10 }}>The exact table from the assignment brief. The product-level detail behind it is mock data.</p>}
    </div>
  );

  const historyCard = history.length > 0 ? (
    <div className="card">
      <h2>Earlier calls</h2>
      <table>
        <tbody>
          {history.map((h) => (
            <tr key={h.id}>
              <td>{shortDate(h.ended_at)}</td>
              <td>{h.direction === "proactive" ? "Asha called" : "Seller called"}</td>
              <td className="muted">{causeLabel(h.root_cause)}</td>
              <td className="num">{h.actions} actions</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : null;

  return (
    <>
      <div className="sellerhead">
        <h1>{seller.name}</h1>
        <span className="muted">{seller.owner_name}, {seller.category}, {seller.city}{seller.is_custom ? " (entered by you)" : ""}</span>
        {!seller.is_custom && <Link className="small" href={`/seller/${seller.id}/plan`}>What-if planner</Link>}
      </div>
      <CallScreen sellerId={seller.id} ownerName={seller.owner_name}
        initialDirection={direction === "proactive" ? "proactive" : "inbound"}
        hasHistory={history.length > 0} dataCard={dataCard} historyCard={historyCard} />
    </>
  );
}
