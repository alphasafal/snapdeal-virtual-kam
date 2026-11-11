"use client";
// The human review box on a call record: mark the call as reviewed, or flag it for
// follow-up, with the reviewer's name and an optional note.
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function ReviewForm({ callId, current }: {
  callId: string; current: { verdict: string; reviewer: string | null; note: string | null } | null;
}) {
  const router = useRouter();
  const [reviewer, setReviewer] = useState(current?.reviewer ?? "");
  const [note, setNote] = useState(current?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(verdict: "ok" | "needs_followup") {
    setBusy(true);
    setError("");
    const res = await fetch(`/api/calls/${callId}/review`, { method: "POST", body: JSON.stringify({ verdict, reviewer, note }) });
    if (!res.ok) setError((await res.json()).error ?? "Could not save the review");
    setBusy(false);
    router.refresh();
  }

  return (
    <div className="stack" style={{ gap: 10 }}>
      <label className="small">Your name
        <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Reviewer" />
      </label>
      <label className="small">Note for the team (optional)
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What should happen next, or what Asha got wrong" />
      </label>
      <div className="row">
        <button className="btn go" disabled={busy} onClick={() => save("ok")}>Mark as reviewed</button>
        <button className="btn" disabled={busy} onClick={() => save("needs_followup")}>Flag for follow-up</button>
      </div>
      {error && <div className="error" role="alert">{error}</div>}
    </div>
  );
}
