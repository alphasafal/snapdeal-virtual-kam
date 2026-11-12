"use client";
// The what-if planner. Tick the actions a seller could take and see the sales that could
// come back next month, and what the plan needs: stock to buy, or margin given up.
// The options and their rupee figures are worked out by the Python planner
// (agent/brain/planner.py) during the nightly scan; this component only adds them up.
import { useMemo, useState } from "react";
import Link from "next/link";
import { inr } from "@/lib/format";

export type RestockItem = {
  name: string;
  units: number;               // the quantity Asha's restock plan orders
  stock_value_inr: number;     // those units at the selling price
  recover_inr: number;         // the sales this product lost this month
};

export type PlanOption = {
  key: string;                 // for example "restock_top"
  title: string;
  detail: string;
  when: string;                // how soon it can be done, for example "within 3 days"
  recover_inr: number | null;  // the most it could win back per month; null = no honest figure
  items?: RestockItem[];       // restock options only: one line per product, biggest loss first
  cost_share?: number;         // restock options only: assumed purchase cost as a share of the selling price
  margin_inr?: number;         // price options only: margin given up each month
};

// One ticked action: what it recovers and costs. `late` means the cash ran out on an earlier action.
type Line = { recover: number; cost: number; units: number; fit: number; of: number; names: string; late: boolean };

const RESTOCK_ORDER = ["restock_top", "restock_rest"];   // the order Asha restocks in

export default function Planner({ sellerId, salesPrev, salesCurr, gap, options }: {
  sellerId: string; salesPrev: number; salesCurr: number; gap: number; options: PlanOption[];
}) {
  // Start with every action that has a rupee figure ticked.
  const [chosen, setChosen] = useState<Set<string>>(
    () => new Set(options.filter((o) => o.recover_inr).map((o) => o.key)));
  const assumedShare = options.find((o) => o.cost_share)?.cost_share ?? 0.6;
  const [costPct, setCostPct] = useState(String(Math.round(assumedShare * 100)));
  const [cash, setCash] = useState("");                  // empty = no limit
  const needsStock = options.some((o) => o.items?.length);

  const toggle = (key: string) => setChosen((old) => {
    const next = new Set(old);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  // What each ticked action recovers and costs. When cash is limited, products are bought in
  // the order of the sales they lost and buying stops at the first one that does not fit,
  // which is how Asha shortens a restock plan on the call.
  const lines = useMemo(() => {
    const typedPct = Number(costPct);
    const share = typedPct > 0 && typedPct <= 100 ? typedPct / 100 : assumedShare;   // nonsense typed: keep the assumption
    const typed = cash.replace(/[^0-9.]/g, "");
    let left = typed === "" ? Infinity : Number(typed) || 0;
    let stop = false;
    const out = new Map<string, Line>();
    const restock = RESTOCK_ORDER.map((key) => options.find((o) => o.key === key)).filter(Boolean) as PlanOption[];
    for (const o of restock) {
      if (!chosen.has(o.key)) continue;
      const items = o.items ?? [];
      const late = stop;
      const bought: RestockItem[] = [];
      for (const item of items) {
        const cost = item.stock_value_inr * share;
        if (stop || cost > left) { stop = true; break; }
        left -= cost;
        bought.push(item);
      }
      out.set(o.key, {
        recover: items.length ? bought.reduce((sum, i) => sum + i.recover_inr, 0) : o.recover_inr ?? 0,
        cost: bought.reduce((sum, i) => sum + i.stock_value_inr * share, 0),
        units: bought.reduce((sum, i) => sum + i.units, 0),
        fit: bought.length, of: items.length, late,
        names: bought.slice(0, 3).map((i) => i.name).join(", ") + (bought.length > 3 ? ` and ${bought.length - 3} more` : ""),
      });
    }
    for (const o of options) {
      if (!chosen.has(o.key) || out.has(o.key)) continue;
      out.set(o.key, { recover: o.recover_inr ?? 0, cost: 0, units: 0, fit: 0, of: 0, names: "", late: false });
    }
    return out;
  }, [chosen, options, costPct, cash, assumedShare]);

  const all = [...lines.values()];
  // Never show more recovered than was lost: the figures are upper limits and can overlap.
  const recovered = Math.min(gap, all.reduce((sum, l) => sum + l.recover, 0));
  const stockCost = all.reduce((sum, l) => sum + l.cost, 0);
  const stockUnits = all.reduce((sum, l) => sum + l.units, 0);
  const margin = options.filter((o) => chosen.has(o.key)).reduce((sum, o) => sum + (o.margin_inr ?? 0), 0);
  const projected = salesCurr + recovered;
  const share = (amount: number) => `${Math.max(2, Math.round((amount / salesPrev) * 100))}%`;

  return (
    <div className="stage">
      <div className="card">
        <h2>Actions open to this seller</h2>
        <p className="muted small" style={{ marginBottom: 6 }}>Biggest first. Untick any the seller cannot do.</p>
        {options.map((o) => {
          const line = lines.get(o.key);
          const short = !!line && line.of > 0 && line.fit < line.of;
          const amount = line && o.items?.length ? line.recover : o.recover_inr;
          return (
            <label className="opt" key={o.key}>
              <input type="checkbox" checked={chosen.has(o.key)} onChange={() => toggle(o.key)} />
              <span>
                <b>{o.title}</b>
                <span className="muted small" style={{ display: "block" }}>{o.detail}</span>
                <span className="muted small" style={{ display: "block" }}>Can be done {o.when}</span>
                {line && line.of > 0 && !short && (
                  <span className="small needs">Stock to buy: {line.units} units, about {inr(line.cost)}</span>)}
                {short && (
                  <span className="small needs short">
                    {line.fit > 0
                      ? `The cash covers ${line.fit} of ${line.of} products (${line.names}): ${line.units} units, about ${inr(line.cost)}.`
                      : line.late ? "No cash is left for these after the products above."
                      : "The cash entered does not cover the first product."}
                  </span>)}
                {!!o.margin_inr && <span className="small needs">Gives up about {inr(o.margin_inr)} of margin a month</span>}
              </span>
              <span className={amount ? "amt" : "amt none"}>
                {amount ? `up to ${inr(amount)}` : o.recover_inr ? "not within this cash" : "no rupee figure"}
              </span>
            </label>
          );
        })}

        {needsStock && (
          <>
            <div className="plancash">
              <label htmlFor="cash">Cash the seller can put into stock (₹)</label>
              <input id="cash" inputMode="numeric" placeholder="No limit" value={cash} onChange={(e) => setCash(e.target.value)} />
              <label htmlFor="costpct">Stock costs this % of the selling price</label>
              <input id="costpct" inputMode="numeric" value={costPct} onChange={(e) => setCostPct(e.target.value)} />
            </div>
            <p className="muted small" style={{ marginTop: 8 }}>
              The {Math.round(assumedShare * 100)}% is an assumption, not seller data: change it to the seller's real margin.
              Quantities are 20% above last month's units, the same as Asha's restock plan. When cash is short,
              products are restocked in order of the sales they lost.
            </p>
          </>
        )}
      </div>

      <div className="card">
        <h2>What that could do</h2>
        <div className="planbars">
          <div><span>Last month</span><div className="bar"><i style={{ width: "100%", background: "var(--ink-3)" }} /></div><b>{inr(salesPrev)}</b></div>
          <div><span>This month</span><div className="bar"><i style={{ width: share(salesCurr) }} /></div><b>{inr(salesCurr)}</b></div>
          <div><span>Next month, with this plan</span><div className="bar"><i style={{ width: share(projected), background: "var(--green)" }} /></div><b>{inr(projected)}</b></div>
        </div>
        <div className="total">
          <span>Sales this plan could recover each month</span>
          <span style={{ color: "var(--green)" }}>up to {inr(recovered)}</span>
        </div>
        {stockCost > 0 && (
          <div className="costline"><span>Stock to buy first</span><b>about {inr(stockCost)} for {stockUnits} units</b></div>)}
        {margin > 0 && (
          <div className="costline"><span>Margin given up each month</span><b>about {inr(margin)}</b></div>)}
        <p className="muted small" style={{ marginTop: 8 }}>
          That is {Math.round((recovered / gap) * 100)}% of the {inr(gap)} drop. Each figure is an upper limit:
          it assumes the action works fully for a whole month. Asha quotes the same recovery figures on the call.
        </p>
        <div className="row" style={{ marginTop: 16 }}>
          <Link className="btn primary" href={`/seller/${sellerId}?direction=proactive`}>Have Asha call to agree this plan</Link>
          <Link className="btn" href={`/seller/${sellerId}`}>Seller page</Link>
        </div>
      </div>
    </div>
  );
}
