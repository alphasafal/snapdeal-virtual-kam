"use client";
// Sends the call summary to the seller. Sellers in India run their business on WhatsApp, so
// the first button opens WhatsApp with the summary already written; the second copies it.
// Nothing is sent automatically: the person presses Send in WhatsApp themselves.
import { useState } from "react";
import { day, inr } from "@/lib/format";

type Summary = {
  issue?: string;
  actions?: { title: string; due?: string | null; expected_recovery_inr?: number | null }[];
  followup_date?: string | null;
};

// The summary as plain text, the way it would read in a message.
export function summaryText(sellerName: string, summary: Summary): string {
  const lines = [`Snapdeal call summary for ${sellerName}`, "", summary.issue ?? ""];
  if (summary.actions?.length) {
    lines.push("", "What we agreed:");
    summary.actions.forEach((a, i) => lines.push(
      `${i + 1}. ${a.title}${a.due ? `, by ${day(a.due)}` : ""}${a.expected_recovery_inr ? ` (up to ${inr(a.expected_recovery_inr)} a month)` : ""}`));
  }
  if (summary.followup_date) lines.push("", `Follow-up call: ${day(summary.followup_date)}`);
  lines.push("", "Asha, your Snapdeal account manager");
  return lines.join("\n").trim();
}

export default function ShareSummary({ sellerName, summary }: { sellerName: string; summary: Summary }) {
  const [copied, setCopied] = useState(false);
  const text = summaryText(sellerName, summary);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* clipboard blocked */ }
  };
  return (
    <div className="row" style={{ marginTop: 12 }}>
      <a className="btn" href={`https://wa.me/?text=${encodeURIComponent(text)}`} target="_blank" rel="noreferrer">Send summary on WhatsApp</a>
      <button type="button" className="btn" onClick={copy}>{copied ? "Copied" : "Copy summary"}</button>
    </div>
  );
}
