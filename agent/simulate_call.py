"""Dev tool: play a scripted call into the database without any audio.

Use it to check the web app (transcript, action panel, summary, dashboard) when
you have no microphone or keys handy. It calls the same tools the voice agent calls, and
every action goes through the same consent check as a live call. The stockout script
includes one deliberate early attempt (the seller only asked a question) so the call
record shows what a refusal looks like.

Run:  python simulate_call.py            (uses the newest call the web app created)
      python simulate_call.py <call_id>
"""
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import desc, select

load_dotenv()

from brain import db, repo  # noqa: E402
from brain.audit import audit_call  # noqa: E402
from brain.consent import gate_report, seller_agreed  # noqa: E402
from brain.tools import KamTools  # noqa: E402

PAUSE = 0.0 if "--fast" in sys.argv else 1.2
args = [a for a in sys.argv[1:] if not a.startswith("--")]

if args:
    call_id = args[0]
else:
    with db.engine().connect() as cx:
        row = cx.execute(select(db.calls.c.id).where(db.calls.c.status == "created")
                         .order_by(desc(db.calls.c.id)).limit(1)).first()
    call_id = row[0] if row else repo.create_call("S1")

call = repo.get_call(call_id)
t = KamTools(call["seller_id"], call_id)
started = datetime.now(timezone.utc)
repo.update_call(call_id, status="live", started_at=started, voice_mode="simulated")
name = t.seller["owner_name"].split()[0]
memory = t.memory_brief()


def did(text: str) -> None:
    """Tool activity, shown on screen the way the live agent records it."""
    repo.add_turn(call_id, "tool", text)


agent_said: list[str] = []
last = {"agent": "", "seller": ""}                    # the latest thing each side said
gate_log: list[tuple[str, str, str]] = []            # what the consent check decided, in order


def say(role: str, text: str) -> None:
    """Add one spoken line to the transcript ("agent" or "seller") and print it."""
    repo.add_turn(call_id, role, text)
    last[role] = text
    if role == "agent":
        agent_said.append(text)
    print(f"{role:>6}: {text}")
    time.sleep(PAUSE)


def act(action: str, fn, *args, saved: str, prepared: str) -> bool:
    """Try to save one action the way the live agent does: only if the seller's latest
    words are a clear yes to it (brain/consent.py). Returns True if it was saved."""
    agreed, why = seller_agreed(last["seller"], last["agent"], action)
    gate_log.append((action, "agreed" if agreed else why, last["seller"]))
    fn(*args, seller_confirmed=agreed)
    did(saved if agreed else prepared)
    return agreed


if memory:
    say("agent", f"Namaste {name} ji, Asha from Snapdeal. Last week we agreed on a restock plan. I can see part of it is back in stock, well done. What is holding up the rest?")
    say("seller", "The supplier says two more days for the remaining ones.")
    t.record_seller_input("supplier_delay", "Remaining restock arriving in two days")
    say("agent", "Understood. I will check again in three days so nothing slips.")
    t.schedule_followup(3)
else:
    top = t.diagnosis["causes"][0] if t.diagnosis["causes"] else None
    say("agent", f"Namaste {name} ji, this is Asha from Snapdeal. How can I help you today?")
    say("seller", "My sales have dropped significantly this month. I don't understand why. Can you help me?")
    say("agent", f"I have your account open. {t.diagnosis['headline']} The main cause I see: {top['title'].lower() if top else 'nothing unusual'}.")
    if top and top["key"] == "stockouts":
        say("agent", "Why did those products run out: supplier delay, cash tied up, or the stock level was missed?")
        say("seller", "My supplier delayed the shipment by two weeks.")
        t.record_seller_input("supplier_delay", "Supplier delayed shipment by two weeks")
        did("Noted what the seller explained")
        say("agent", "Then let us restock the six that lost the most first. Shall I create that restock plan?")
        say("seller", "Yes, do it.")
        act("restock_plan", t.create_restock_plan, 6,
            saved="Saved the restock plan", prepared="Prepared a restock proposal")
        say("agent", "Done. Shall I also pause the other out-of-stock listings, so orders stop getting cancelled?")
        say("seller", "What happens to those listings if I pause them?")
        # The deliberate early attempt: a question is not a yes, so the check refuses it.
        act("pause_listings", t.pause_unavailable_listings, False,
            saved="Paused the out-of-stock listings", prepared="Prepared to pause out-of-stock listings")
        say("agent", "Buyers stop seeing them until stock is back, so nobody orders what you cannot ship. Shall I pause them?")
        say("seller", "Okay, yes.")
        act("pause_listings", t.pause_unavailable_listings, False,
            saved="Paused the out-of-stock listings", prepared="Prepared to pause out-of-stock listings")
        say("agent", "Done. And a two-unit safety buffer on every listing, so stock never hits zero with orders open?")
        say("seller", "Yes, set the buffer.")
        act("stock_buffer", t.set_stock_buffer, 2,
            saved="Set the safety stock buffer", prepared="Prepared a safety stock buffer")
    elif top and top["key"] == "pricing":
        say("agent", "Rivals are cheaper on your best sellers. Shall I match their prices, within what your margin allows?")
        say("seller", "Yes, match the prices. I can go ten percent lower.")
        t.record_seller_input("pricing", "Margin allows up to ten percent lower")
        did("Noted what the seller explained")
        act("price_match", t.match_rival_prices, 5, 10,
            saved="Matched rival prices", prepared="Prepared a price match proposal")
    elif top:
        say("agent", "Most of the extra cancellations are for late dispatch. What changed in packing this month?")
        say("seller", "My packing staff left, so dispatch has been late.")
        t.record_seller_input("dispatch", "Packing staff left; dispatch running late")
        did("Noted what the seller explained")
        say("agent", "Shall I turn on a daily pickup reminder and dispatch deadline alerts?")
        say("seller", "Yes, please turn on the alerts.")
        act("dispatch_alerts", t.enable_dispatch_alerts,
            saved="Turned on dispatch alerts", prepared="Prepared dispatch alerts")
        t.raise_ticket("visibility review", "Re-check seller rating once dispatch is back on time")
        did("Raised a ticket with the Snapdeal team")
    t.schedule_followup(7)
    say("agent", "All saved. I will call you again in a week to check progress.")

t.wrap_up()
say("agent", "That is the plan. Thank you, and talk soon.")
ended = datetime.now(timezone.utc)
summary = t.build_summary()
summary["audit"] = audit_call(agent_said, [t.account_brief()])     # the same check a live call gets
summary["consent"] = gate_report(gate_log)                         # and the same consent record
repo.update_call(call_id, status="ended", ended_at=ended, duration_s=int((ended - started).total_seconds()),
                 est_cost_inr=0, avg_latency_ms=None, summary=summary)
print("call", call_id, "ended")
