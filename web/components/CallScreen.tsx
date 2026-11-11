"use client";
// The live call screen. This is the only part of the web app that touches audio.
//
// What it does, in order:
//   1. "Start call" asks our server for a call id and a LiveKit token   (start)
//   2. It joins the LiveKit room and switches the microphone on. The voice agent joins the
//      same room from its side and starts talking.
//   3. Once a second it asks our server for the call's state: transcript, actions, summary.
//      The agent writes those to the database as the call goes on                  (polling effect)
//   4. When the agent ends the call, or the seller clicks "End call", it leaves the room and
//      shows the summary.
//
// If no microphone is available the call still goes ahead in typing mode: the seller's words
// are sent as text over the same call (sendTyped) and Asha answers aloud as usual.
//
// The call moves through five phases: idle -> (ringing) -> connecting -> live -> ended.
// Left column: the call panel and the conversation. Right column: summary, what was agreed,
// what Asha found, and the seller's data.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Room, RoomEvent, Track } from "livekit-client";
import { day, inr, withoutRepeats } from "@/lib/format";

type Phase = "idle" | "ringing" | "connecting" | "live" | "ended";
type Turn = { id: number; role: "agent" | "seller" | "tool"; text: string };
type Action = { id: string; type: string; title: string; status: string; expected_recovery_inr: number | null; due_date: string | null; detail: any };
type Cause = { key: string; title: string; impact_inr: number; share_pct: number; confidence: string; evidence: string[] };
type State = { call: any; turns: Turn[]; actions: Action[]; diagnosis: any };

// How sure the diagnosis is about each cause, in words (see agent/brain/diagnosis.py).
const CONFIDENCE: Record<string, string> = {
  measured: "measured from product data",
  estimated: "estimated from totals",
  inferred: "the part left unexplained by the rest",
};

// Seconds as a call timer: 75 -> "1:15".
function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export default function CallScreen({ sellerId, ownerName, initialDirection, hasHistory, dataCard, historyCard }: {
  sellerId: string; ownerName: string; initialDirection: "inbound" | "proactive"; hasHistory: boolean;
  dataCard: ReactNode; historyCard: ReactNode;
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>(initialDirection === "proactive" ? "ringing" : "idle");
  const [direction] = useState(initialDirection);
  const [language, setLanguage] = useState<"en" | "hinglish">("en");
  const [voice, setVoice] = useState<"sarvam" | "gemini">("sarvam");
  const [callId, setCallId] = useState<string | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState("");
  const [speaker, setSpeaker] = useState<"agent" | "seller" | null>(null);
  const [muted, setMuted] = useState(false);
  const [simNote, setSimNote] = useState("");
  const [agentState, setAgentState] = useState("");
  const [agentJoined, setAgentJoined] = useState(false);
  const [waitedLong, setWaitedLong] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [micBlocked, setMicBlocked] = useState(false);     // no microphone: the seller types instead
  const [showTyping, setShowTyping] = useState(false);
  const [typed, setTyped] = useState("");
  const roomRef = useRef<Room | null>(null);
  const audioHost = useRef<HTMLDivElement>(null);
  const talkRef = useRef<HTMLDivElement>(null);
  const firstName = ownerName.split(" ")[0];

  // Start (or accept) the call: create it on our server, join the room, open the microphone.
  const start = useCallback(async () => {
    setError("");
    setPhase("connecting");
    try {
      const res = await fetch("/api/calls", { method: "POST", body: JSON.stringify({ sellerId, direction, language, voice }) });
      const out = await res.json();
      if (out.callId) setCallId(out.callId);
      if (!res.ok) throw new Error(out.error ?? "Could not start the call");

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio && audioHost.current) audioHost.current.appendChild(track.attach());
      });
      room.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => el.remove()));
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        if (!speakers.length) return setSpeaker(null);
        setSpeaker(speakers[0].isLocal ? "seller" : "agent");
      });
      room.on(RoomEvent.ParticipantConnected, () => setAgentJoined(true));
      room.on(RoomEvent.ParticipantAttributesChanged, (changed, participant) => {
        if (!participant.isLocal && changed["lk.agent.state"]) setAgentState(changed["lk.agent.state"]);
      });
      room.on(RoomEvent.Disconnected, () => { setPhase("ended"); setSpeaker(null); });
      // Safari and phones can refuse to play sound until the person taps; offer a button if so.
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => setAudioBlocked(!room.canPlaybackAudio));
      await room.connect(out.url, out.token);
      if (room.remoteParticipants.size > 0) setAgentJoined(true);
      // No microphone (blocked, missing, or refused)? Carry on: the seller can type instead.
      try {
        await room.localParticipant.setMicrophoneEnabled(true);
        setMicBlocked(false);
      } catch {
        setMicBlocked(true);
        setShowTyping(true);
      }
      await room.startAudio().catch(() => {});
      setAudioBlocked(!room.canPlaybackAudio);
      setSeconds(0);
      setPhase("live");
    } catch (e: any) {
      await roomRef.current?.disconnect().catch(() => {});
      roomRef.current = null;
      const msg = e?.message ?? String(e);
      setError(/permission|notallowed|denied/i.test(msg) ? "Microphone access was blocked. Allow the microphone for this site, then start the call again." : msg);
      setPhase("idle");
    }
  }, [sellerId, direction, language, voice]);

  // The seller hangs up.
  const end = useCallback(async () => {
    await roomRef.current?.disconnect();
    setPhase("ended");
  }, []);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    try {
      await room.localParticipant.setMicrophoneEnabled(muted);
      setMuted(!muted);
      setMicBlocked(false);
    } catch {
      setMicBlocked(true);
      setShowTyping(true);
    }
  }, [muted]);

  // Typed fallback: the seller's words go to Asha as text over the same call. She still answers
  // aloud, and everything else (tools, consent check, transcript) works exactly as for speech.
  const sendTyped = useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    const text = typed.trim();
    if (!text || !roomRef.current) return;
    setTyped("");
    await roomRef.current.localParticipant.sendText(text, { topic: "lk.chat" }).catch(() => setTyped(text));
  }, [typed]);

  // Leaving the page ends the call.
  useEffect(() => () => { roomRef.current?.disconnect(); }, []);

  // The call timer.

  useEffect(() => {
    if (phase !== "live") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  // If no agent picks up within 12 seconds, say so instead of leaving the seller in silence.
  useEffect(() => {
    if (phase !== "live" || agentJoined) { setWaitedLong(false); return; }
    const t = setTimeout(() => setWaitedLong(true), 12000);
    return () => clearTimeout(t);
  }, [phase, agentJoined]);

  // The agent closed the call (she hung up, or the connection failed): hang up on this side too.
  useEffect(() => {
    if (phase === "live" && state?.call?.status === "ended") roomRef.current?.disconnect();
  }, [phase, state?.call?.status]);

  // Transcript, actions and summary come from the database, once a second while a call is on.
  useEffect(() => {
    if (!callId) return;
    let stop = false;
    let quietAfterEnd = 0;
    const tick = async () => {
      try {
        const res = await fetch(`/api/calls/${callId}`, { cache: "no-store" });
        if (res.ok) {
          const s: State = await res.json();
          if (!stop) setState(s);
          if (s.call.status === "ended") quietAfterEnd += 1;
        }
      } catch { /* keep polling */ }
      if (!stop && quietAfterEnd < 3) setTimeout(tick, 1000);
    };
    tick();
    return () => { stop = true; };
  }, [callId]);

  useEffect(() => {
    talkRef.current?.scrollTo({ top: talkRef.current.scrollHeight, behavior: "smooth" });
  }, [state?.turns.length]);

  // Demo helper: pretend a week has passed, so the next call shows Asha following up.
  async function simulateWeek() {
    const res = await fetch("/api/simulate-week", { method: "POST", body: JSON.stringify({ sellerId }) });
    const out = await res.json();
    setSimNote(res.ok ? `A week has passed. ${out.notes?.join(" ") ?? ""} Start a new call to hear Asha follow up.` : out.error);
    router.refresh();
  }

  // ---- Everything below turns the latest state into what is shown on screen ----
  const turns = withoutRepeats(state?.turns ?? []);
  const kept = (state?.actions ?? []).filter((a) => a.status !== "cancelled");
  const removed = (state?.actions ?? []).filter((a) => a.status === "cancelled");
  const actions = kept.filter((a) => a.type !== "followup");
  const followup = kept.find((a) => a.type === "followup");
  const diagnosis = state?.diagnosis;

  // Where the call has got to, worked out from what has been said and saved so far.
  const agentTurns = turns.filter((t) => t.role === "agent").length;
  const sellerTurns = turns.filter((t) => t.role === "seller").length;
  const journey: [string, boolean][] = [
    ["Greet", agentTurns >= 1],
    ["Diagnose", agentTurns >= 2],
    ["Ask", sellerTurns >= 2],
    ["Act", actions.length >= 1],
    ["Follow-up", kept.some((a) => a.type === "followup")],
    ["Summarise", Boolean(state?.call?.summary?.issue)],
  ];
  const nextStep = journey.findIndex(([, done]) => !done);
  const summary = state?.call?.status === "ended" ? state.call.summary : null;
  const live = phase === "live";
  const dropped = summary?.ended_reason === "connection_problem";
  const total = actions.reduce((sum, a) => sum + (a.expected_recovery_inr ?? 0), 0);
  const who = !live ? null : speaker === "agent" || agentState === "speaking" ? "agent" : speaker === "seller" ? "seller" : null;

  // The big line in the call panel, and the hint under it, for each phase.
  let now = "Call your account manager";
  let hint = "Speak naturally, in English or Hinglish. You can interrupt her at any time.";
  if (phase === "ringing") { now = "Asha is calling"; hint = `She noticed a change in this account and wants two minutes with ${firstName}.`; }
  if (phase === "connecting") { now = "Connecting"; hint = "Allow the microphone if your browser asks."; }
  if (live) {
    hint = "";
    if (!agentJoined) hint = "Asha is picking up. This takes a few seconds.";
    now = !agentJoined ? "Ringing" : who === "agent" ? "Asha is speaking" : agentState === "thinking" ? "Asha is thinking" : who === "seller" ? "Listening to you" : "On the call";
  }
  if (phase === "ended") {
    now = "Call ended";
    hint = dropped ? "The call dropped because of a connection problem. Start a new call and Asha picks up from what was agreed."
      : summary?.ended_reason === "no_conversation" ? "The call ended before anything was said."
      : "The summary is saved. Asha will follow up on the date agreed.";
  }

  return (
    <div className="stage">
      <section className="stack">
        <div className="phone">
          <div className="status" aria-live="polite">
            <span className={`dot ${live ? "live" : phase === "ringing" ? "ring" : ""}`} aria-hidden />
            <span>{live ? "Live call with Asha, your Virtual KAM" : phase === "ringing" ? "Incoming call" : "Asha, your Virtual KAM"}</span>
            {(live || phase === "ended") && seconds > 0 && <span className="timer">{clock(seconds)}</span>}
          </div>
          <div className="now">{now}</div>
          {hint && <p className="hint">{hint}</p>}
          {live && waitedLong && <p className="hint">No agent has picked up. Check that the agent worker is running.</p>}
          {live && (
            <div className={`bars ${who ?? ""}`} aria-hidden>
              {Array.from({ length: 28 }, (_, i) => <i key={i} style={{ animationDelay: `${((i * 7) % 11) * 0.08}s` }} />)}
            </div>
          )}

          {(phase === "idle" || phase === "ringing") && (
            <div className="opts">
              <label>Language
                <select value={language} onChange={(e) => setLanguage(e.target.value as any)}>
                  <option value="en">English</option>
                  <option value="hinglish">Hinglish</option>
                </select>
              </label>
              <label>Voice
                <select value={voice} onChange={(e) => setVoice(e.target.value as any)}>
                  <option value="sarvam">Sarvam (default)</option>
                  <option value="gemini">Gemini Live (premium)</option>
                </select>
              </label>
            </div>
          )}
          <div className="controls">
            {phase === "idle" && <button className="btn go" onClick={start}>Start call</button>}
            {phase === "ringing" && <button className="btn go" onClick={start}>Accept call</button>}
            {phase === "connecting" && <button className="btn onDark" disabled>Connecting…</button>}
            {live && audioBlocked && (
              <button className="btn go" onClick={async () => { await roomRef.current?.startAudio().catch(() => {}); setAudioBlocked(!roomRef.current?.canPlaybackAudio); }}>
                Tap to hear Asha
              </button>
            )}
            {live && !micBlocked && <button className="btn onDark" onClick={toggleMute}>{muted ? "Unmute" : "Mute"}</button>}
            {live && <button className="btn stop" onClick={end}>End call</button>}
            {phase === "ended" && <button className="btn go" onClick={() => window.location.reload()}>New call</button>}
            {phase === "ended" && <button className="btn onDark" onClick={simulateWeek}>Simulate a week passing</button>}
          </div>
          {phase === "idle" && hasHistory && <p className="hint small" style={{ marginTop: 12 }}>This seller has an earlier call, so Asha will open by following up on it.</p>}
          {live && micBlocked && <p className="hint small" style={{ marginTop: 12 }}>No microphone was available, so this call is in typing mode. Asha still speaks; type your side under the conversation. To speak instead, allow the microphone for this site in your browser, then start a new call.</p>}
          {live && !showTyping && <p className="hint small" style={{ marginTop: 12 }}><button type="button" className="linkish" onClick={() => setShowTyping(true)}>Cannot speak right now? Type instead</button></p>}
          {simNote && <p className="hint small" style={{ marginTop: 12 }}>{simNote}</p>}
          {error && <div className="error" role="alert">{error}</div>}
          <div ref={audioHost} />
        </div>

        <div className="card">
          <h2>Conversation</h2>
          {callId && (
            <ol className="journey" aria-label="Progress of the call">
              {journey.map(([label, done], i) => (
                <li key={label} className={done ? "done" : i === nextStep && live ? "now" : ""}>
                  <i>{done ? "✓" : i + 1}</i>{label}
                </li>
              ))}
            </ol>
          )}
          <div className="talk" ref={talkRef}>
            {turns.length === 0 && <p className="muted">{callId ? "Waiting for the first words." : "The transcript appears here once the call starts."}</p>}
            {turns.map((t) => t.role === "tool"
              ? <div key={t.id} className="did">{t.text}</div>
              : <div key={t.id} className={`turn ${t.role}`}><small>{t.role === "agent" ? "Asha" : firstName}</small>{t.text}</div>)}
          </div>
          {live && showTyping && (
            <form className="typed" onSubmit={sendTyped}>
              <input value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Type your side of the call"
                placeholder="Type what you would say, then press Enter" autoComplete="off" />
              <button className="btn" type="submit" disabled={!typed.trim()}>Send</button>
            </form>
          )}
        </div>
      </section>

      <section className="stack">
        {summary && (
          <div className="card">
            <h2>Call summary</h2>
            <p>{summary.issue}</p>
            {summary.actions?.length > 0 && (
              <ul className="clean">
                {summary.actions.map((a: any) => (
                  <li key={a.title}>{a.title}{a.due ? `, by ${day(a.due)}` : ""}{a.expected_recovery_inr ? `, up to ${inr(a.expected_recovery_inr)} a month` : ""}</li>
                ))}
              </ul>
            )}
            <p style={{ marginTop: 10 }}>
              {summary.followup_date ? `Follow-up call on ${day(summary.followup_date)}. ` : ""}
              {summary.escalated ? "Handed over to a human account manager. " : ""}
            </p>
            <p className="muted small" style={{ marginTop: 6 }}>
              {[state?.call?.duration_s ? `${state.call.duration_s}s call` : "",
                state?.call?.voice_mode ? `${state.call.voice_mode} voice` : "",
                state?.call?.est_cost_inr ? `about ₹${Number(state.call.est_cost_inr).toFixed(2)} to run` : "",
                state?.call?.avg_latency_ms ? `replies began ${(state.call.avg_latency_ms / 1000).toFixed(1)}s after the seller stopped` : "",
                summary.audit ? (summary.audit.flags?.length ? `${summary.audit.flags.length} spoken figure(s) flagged for review`
                  : summary.audit.figures_checked ? `${summary.audit.figures_checked} spoken figures checked against the data, all match` : "") : "",
              ].filter(Boolean).join(", ")}
            </p>
          </div>
        )}

        {callId && (
          <div className="card ledger">
            <h2>Agreed on this call</h2>
            {actions.length === 0 && <p className="muted">Nothing yet. An action is written here the moment the seller says yes.</p>}
            {actions.map((a) => (
              <div className="entry" key={a.id}>
                <span className="tick" aria-hidden>✓</span>
                <div>
                  <b>{a.title}</b>
                  {Array.isArray(a.detail?.products) && (
                    <div className="muted small">{a.detail.products.slice(0, 4).map((p: any) => p.name).join(", ")}{a.detail.products.length > 4 ? ` and ${a.detail.products.length - 4} more` : ""}</div>
                  )}
                  {a.due_date && <div className="muted small">Due {day(a.due_date)}</div>}
                </div>
                <span className="amt">{a.expected_recovery_inr ? `up to ${inr(a.expected_recovery_inr)}` : ""}</span>
              </div>
            ))}
            {total > 0 && <div className="total"><span>Sales this could recover each month</span><span className="num">up to {inr(total)}</span></div>}
            {followup && <p className="small" style={{ marginTop: 12 }}>Follow-up call booked for {day(followup.due_date)}.</p>}
            {removed.length > 0 && <p className="small muted" style={{ marginTop: 8 }}>Removed at the seller's request: {removed.map((a) => a.title).join(", ")}.</p>}
          </div>
        )}

        {diagnosis?.status === "declining" && (
          <div className="card">
            <h2>What Asha found before speaking</h2>
            <p>{diagnosis.headline}</p>
            {(diagnosis.causes as Cause[]).some((c) => c.impact_inr > 0) && (
              <figure className="split">
                <figcaption className="muted small">Where the lost sales went</figcaption>
                <div className="splitbar">
                  {(diagnosis.causes as Cause[]).filter((c) => c.impact_inr > 0).map((c, i) => (
                    <span key={c.key} className={`seg s${i}`} style={{ width: `${c.share_pct}%` }} title={`${c.title}: ${inr(c.impact_inr)}`}>
                      {c.share_pct >= 18 ? inr(c.impact_inr) : ""}
                    </span>
                  ))}
                </div>
              </figure>
            )}
            {(diagnosis.causes as Cause[]).map((c) => (
              <div className="cause" key={c.key}>
                <div className="head"><b>{c.title}</b><span className="num">{c.impact_inr > 0 ? `${inr(c.impact_inr)}, ${c.share_pct}% of the drop` : "costs money, not part of the drop"}</span></div>
                <div className="bar"><i style={{ width: `${Math.min(100, c.share_pct)}%` }} /></div>
                <div className="muted small">{c.evidence[0]} ({CONFIDENCE[c.confidence] ?? c.confidence})</div>
              </div>
            ))}
            {diagnosis.assumptions?.length > 0 && <p className="muted small" style={{ marginTop: 12 }}>Assumptions: {diagnosis.assumptions.join(" ")}</p>}
          </div>
        )}
        {diagnosis?.status === "not_declining" && (
          <div className="card"><h2>What Asha found before speaking</h2><p>{diagnosis.headline}</p></div>
        )}

        {dataCard}
        {historyCard}
      </section>
    </div>
  );
}
