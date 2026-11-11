"use client";
// The what-if planner. Tick the actions a seller could take and see the sales that could
// come back next month. The options and their rupee figures are worked out by the Python
// planner (agent/brain/planner.py) during the nightly scan; this component only adds them up.
import { useMemo, useState } from "react";
import Link from "next/link";
import { inr } from "@/lib/format";

export type PlanOption = {
  key: string;                 // for example "restock_top"
  title: string;
  detail: string;
  when: string;                // how soon it can be done, for example "within 3 days"
  recover_inr: number | null;  // the most it could win back per month; null = no honest figure
};

export default function Planner({ sellerId, salesPrev, salesCurr, gap, options }: {
  sellerId: string; salesPrev: number; salesCurr: number; gap: number; options: PlanOption[];
}) {
  // Start with every action that has a rupee figure ticked.
  const [chosen, setChosen] = useState<Set<string>>(
    () => new Set(options.filter((o) => o.recover_inr).map((o) => o.key)));

  const toggle = (key: string) => setChosen((old) => {
    const next = new Set(old);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  // Never show more recovered than was lost: the figures are upper limits and can overlap.
  const recovered = useMemo(() => Math.min(gap,
    options.filter((o) => chosen.has(o.key)).reduce((sum, o) => sum + (o.recover_inr ?? 0), 0)),
  [chosen, options, gap]);
  const projected = salesCurr + recovered;
  const share = (amount: number) => `${Math.max(2, Math.round((amount / salesPrev) * 100))}%`;

  return (
    <div className="stage">
      <div className="card">
        <h2>Actions open to this seller</h2>
        <p className="muted small" style={{ marginBottom: 6 }}>Biggest first. Untick any the seller cannot do.</p>
        {options.map((o) => (
          <label className="opt" key={o.key}>
            <input type="checkbox" checked={chosen.has(o.key)} onChange={() => toggle(o.key)} />
            <span>
              <b>{o.title}</b>
              <span className="muted small" style={{ display: "block" }}>{o.detail}</span>
              <span className="muted small">Can be done {o.when}</span>
            </span>
            <span className="amt">{o.recover_inr ? `up to ${inr(o.recover_inr)}` : "no rupee figure"}</span>
          </label>
        ))}
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
        <p className="muted small" style={{ marginTop: 8 }}>
          That is {Math.round((recovered / gap) * 100)}% of the {inr(gap)} drop. Each figure is an upper limit:
          it assumes the action works fully for a whole month. Asha quotes the same figures on the call.
        </p>
        <div className="row" style={{ marginTop: 16 }}>
          <Link className="btn primary" href={`/seller/${sellerId}?direction=proactive`}>Have Asha call to agree this plan</Link>
          <Link className="btn" href={`/seller/${sellerId}`}>Seller page</Link>
        </div>
      </div>
    </div>
  );
}
