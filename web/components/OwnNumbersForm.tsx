"use client";
// The "try your own numbers" form. It saves a seller with two months of totals, then opens
// that seller's call screen. The diagnosis is done by the Python engine when the call starts.
import { useRouter } from "next/navigation";
import { useState } from "react";

const ROWS = [
  { key: "sales", label: "Sales (₹)", prev: "200000", curr: "135000" },
  { key: "orders", label: "Orders", prev: "400", curr: "270" },
  { key: "cancel", label: "Cancellation rate (%)", prev: "8", curr: "14" },
  { key: "oos", label: "Out-of-stock products", prev: "5", curr: "18" },
];

export default function OwnNumbersForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(e.currentTarget).entries());
    const res = await fetch("/api/sellers", { method: "POST", body: JSON.stringify(data) });
    const out = await res.json();
    if (!res.ok) { setError(out.error ?? "Could not save"); setBusy(false); return; }
    router.push(`/seller/${out.id}`);
  }

  return (
    <form className="own" onSubmit={submit}>
      <label htmlFor="name">Seller name</label>
      <input id="name" name="name" placeholder="Any store name" style={{ gridColumn: "span 2" }} />
      <label htmlFor="owner_name">Owner's name</label>
      <input id="owner_name" name="owner_name" placeholder="Used in the greeting" style={{ gridColumn: "span 2" }} />
      <span /><span className="h">Last month</span><span className="h">This month</span>
      {ROWS.map((r) => (
        <div key={r.key} style={{ display: "contents" }}>
          <label>{r.label}</label>
          <input name={`prev_${r.key}`} defaultValue={r.prev} inputMode="decimal" required aria-label={`${r.label} last month`} />
          <input name={`curr_${r.key}`} defaultValue={r.curr} inputMode="decimal" required aria-label={`${r.label} this month`} />
        </div>
      ))}
      <label htmlFor="catalogue_size">Total products listed</label>
      <input id="catalogue_size" name="catalogue_size" defaultValue="60" inputMode="numeric" />
      <span className="muted small">optional</span>
      <div style={{ gridColumn: "1 / -1" }}>
        <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Create seller and open the call screen"}</button>
        {error && <div className="error">{error}</div>}
      </div>
    </form>
  );
}
