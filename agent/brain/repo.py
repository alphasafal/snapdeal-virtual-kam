"""Reading and writing the database.

Every other module goes through these functions instead of writing SQL itself, so there
is one place to look for "how is a call saved?" or "where do actions come from?".

Nothing is cached here: each function opens a connection, does one thing and returns
plain Python data (dicts, lists, small dataclasses). That keeps the voice agent
stateless, which is what lets many agent workers run side by side.

Sections, in order:
  1. Small helpers (time, ids)
  2. Sellers and their data
  3. Calls and transcripts
  4. Actions and follow-ups
  5. Products
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import desc, insert, select, update

from . import db
from .diagnosis import Month, Product, diagnose

# Columns copied from a database row into the Month / Product dataclasses.
METRIC_FIELDS = ("sales", "orders", "cancel_rate", "asp", "oos_products", "visits", "rating",
                 "price_gap_pct", "late_dispatch_rate")
PRODUCT_FIELDS = ("id", "name", "price", "units_prev", "units_curr", "in_stock", "oos_prev",
                  "days_oos_curr", "competitor_price", "status")

IST = timedelta(hours=5, minutes=30)       # India Standard Time is UTC+5:30, with no daylight saving


# ---- 1. Small helpers ---------------------------------------------------------------

def now() -> datetime:
    """The current moment in UTC. Timestamps are always stored in UTC."""
    return datetime.now(timezone.utc)


def today_ist() -> date:
    """Today's date in India. Sellers are in India, so due dates must not depend on
    which time zone the server happens to run in."""
    return (now() + IST).date()


def new_id(prefix: str) -> str:
    """A short unique id such as 'call_3f9a1c22b7' or 'act_0d4e9b1a55'."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---- 2. Sellers and their data ---------------------------------------------------------

def get_seller(seller_id: str) -> Optional[dict]:
    """The seller's profile row, or None if there is no such seller."""
    with db.engine().connect() as cx:
        row = cx.execute(select(db.sellers).where(db.sellers.c.id == seller_id)).mappings().first()
        return dict(row) if row else None


def get_months(seller_id: str) -> tuple[Month, Month]:
    """The seller's two months of metrics as (last month, this month)."""
    with db.engine().connect() as cx:
        rows = {r["period"]: r for r in cx.execute(
            select(db.monthly_metrics).where(db.monthly_metrics.c.seller_id == seller_id)).mappings()}
    if "prev" not in rows or "curr" not in rows:
        raise LookupError(f"no metrics for seller {seller_id}")

    def to_month(row) -> Month:
        """Copy the metric columns of one database row into a Month."""
        return Month(**{field: row[field] for field in METRIC_FIELDS})

    return to_month(rows["prev"]), to_month(rows["curr"])


def get_products(seller_id: str) -> list[Product]:
    """The seller's product catalogue. Empty for a seller entered with totals only."""
    with db.engine().connect() as cx:
        rows = cx.execute(select(db.products).where(db.products.c.seller_id == seller_id)
                          .order_by(db.products.c.id)).mappings().all()
    return [Product(**{field: r[field] for field in PRODUCT_FIELDS}) for r in rows]


def get_cancel_reasons(seller_id: str) -> dict[str, list[dict]]:
    """Why orders were cancelled, as {"prev": [...], "curr": [...]}.
    Each item is {"side": "seller" | "buyer", "reason": str, "count": int}."""
    out: dict[str, list[dict]] = {"prev": [], "curr": []}
    with db.engine().connect() as cx:
        for r in cx.execute(select(db.cancel_reasons).where(
                db.cancel_reasons.c.seller_id == seller_id)).mappings():
            out[r["period"]].append(dict(side=r["side"], reason=r["reason"], count=r["count"]))
    return out


def run_diagnosis(seller_id: str, save: bool = True) -> dict[str, Any]:
    """Run the diagnosis engine for one seller and (by default) store the result.

    The stored copy is what the dashboard's "sellers needing attention" list and the
    call screen's "what Asha found" card read."""
    seller = get_seller(seller_id)
    if not seller:
        raise LookupError(f"unknown seller {seller_id}")
    prev, curr = get_months(seller_id)
    result = diagnose(prev, curr, get_products(seller_id), seller.get("catalogue_size"))
    if save:
        with db.engine().begin() as cx:
            cx.execute(db.diagnoses.delete().where(db.diagnoses.c.seller_id == seller_id))
            cx.execute(insert(db.diagnoses).values(
                seller_id=seller_id, computed_at=now(), risk_level=result["risk_level"],
                primary_cause=result["primary_cause"], gap_inr=result["gap_inr"],
                headline=result["headline"], result=result))
    return result


# ---- 3. Calls and transcripts ------------------------------------------------------------

def create_call(seller_id: str, direction: str = "inbound", call_id: Optional[str] = None,
                language: str = "en") -> str:
    """Create a call row and return its id. The id doubles as the LiveKit room name.

    direction: "inbound" (the seller calls) or "proactive" (the agent calls first).
    language:  "en" or "hinglish", the language the agent replies in."""
    call_id = call_id or new_id("call")
    with db.engine().begin() as cx:
        cx.execute(insert(db.calls).values(id=call_id, seller_id=seller_id, direction=direction,
                                           language=language, status="created", notes={},
                                           escalated=False))
    return call_id


def get_call(call_id: str) -> Optional[dict]:
    """One call row, or None."""
    with db.engine().connect() as cx:
        row = cx.execute(select(db.calls).where(db.calls.c.id == call_id)).mappings().first()
        return dict(row) if row else None


def update_call(call_id: str, **values: Any) -> None:
    """Change any columns of a call, for example update_call(id, status="ended")."""
    with db.engine().begin() as cx:
        cx.execute(update(db.calls).where(db.calls.c.id == call_id).values(**values))


def add_note(call_id: str, topic: str, detail: str) -> None:
    """Remember something the seller told us on this call (topic -> what they said)."""
    call = get_call(call_id) or {}
    notes = dict(call.get("notes") or {})
    notes[topic] = detail
    update_call(call_id, notes=notes)


def add_turn(call_id: str, role: str, text: str) -> None:
    """Append one line to the transcript.

    role: "seller", "agent", or "tool" (a short note of something the agent did)."""
    if not text.strip():
        return
    with db.engine().begin() as cx:
        cx.execute(insert(db.call_turns).values(call_id=call_id, role=role, text=text.strip(), at=now()))


def get_turns(call_id: str) -> list[dict]:
    """The whole transcript of a call, in the order it was spoken."""
    with db.engine().connect() as cx:
        return [dict(r) for r in cx.execute(select(db.call_turns).where(
            db.call_turns.c.call_id == call_id).order_by(db.call_turns.c.id)).mappings()]


def recent_ended_calls(seller_id: str, before_call_id: Optional[str] = None, limit: int = 5) -> list[dict]:
    """Finished calls for this seller, newest first. This is the agent's memory:
    what was agreed last time. `before_call_id` leaves the current call out."""
    q = (select(db.calls).where(db.calls.c.seller_id == seller_id, db.calls.c.status == "ended")
         .order_by(desc(db.calls.c.ended_at)).limit(limit + 1))
    with db.engine().connect() as cx:
        return [dict(r) for r in cx.execute(q).mappings() if r["id"] != before_call_id][:limit]


def close_stale_calls(max_minutes: int = 30) -> int:
    """Close calls that have been "live" for too long and return how many were closed.

    A call is left "live" only if its worker died mid-call. Closing it keeps the dashboard truthful."""
    cutoff = now() - timedelta(minutes=max_minutes)
    with db.engine().begin() as cx:
        res = cx.execute(update(db.calls).where(db.calls.c.status == "live", db.calls.c.started_at < cutoff)
                         .values(status="ended", ended_at=now(),
                                 summary={"issue": "This call ended without a record (the worker stopped).",
                                          "ended_reason": "connection_problem", "actions": [], "causes": []}))
        return res.rowcount or 0


# ---- 4. Actions and follow-ups ---------------------------------------------------------------

def add_action(call_id: str, seller_id: str, type_: str, title: str, detail: dict,
               expected_recovery_inr: Optional[float] = None, due_date: Optional[str] = None) -> dict:
    """Save something the seller agreed to, and return the saved row.

    type_:  restock_plan, pause_listings, stock_buffer, price_match, dispatch_alerts,
            ticket, followup or escalation.
    detail: anything specific to that action, for example the list of products.
    expected_recovery_inr: the most this could win back per month, when we can put a number on it."""
    row = dict(id=new_id("act"), call_id=call_id, seller_id=seller_id, type=type_, title=title,
               detail=detail, expected_recovery_inr=expected_recovery_inr, status="confirmed",
               due_date=due_date, created_at=now())
    with db.engine().begin() as cx:
        cx.execute(insert(db.actions).values(**row))
    return row


def update_action(action_id: str, **values: Any) -> None:
    """Change any columns of an action, for example its status or due date."""
    with db.engine().begin() as cx:
        cx.execute(update(db.actions).where(db.actions.c.id == action_id).values(**values))


def get_actions(call_id: Optional[str] = None, seller_id: Optional[str] = None,
                include_cancelled: bool = False) -> list[dict]:
    """Actions for a call or for a seller, oldest first.

    Cancelled actions are left out unless asked for, so the rest of the code can treat a
    cancelled action as if it had never been agreed."""
    q = select(db.actions).order_by(db.actions.c.created_at)
    if call_id:
        q = q.where(db.actions.c.call_id == call_id)
    if seller_id:
        q = q.where(db.actions.c.seller_id == seller_id)
    if not include_cancelled:
        q = q.where(db.actions.c.status != "cancelled")
    with db.engine().connect() as cx:
        return [dict(r) for r in cx.execute(q).mappings()]


def add_followup(seller_id: str, call_id: str, due_date: str, purpose: str) -> dict:
    """Book a follow-up call for this seller on `due_date` (YYYY-MM-DD)."""
    row = dict(id=new_id("fu"), seller_id=seller_id, call_id=call_id, due_date=due_date,
               purpose=purpose, status="scheduled")
    with db.engine().begin() as cx:
        cx.execute(insert(db.followups).values(**row))
    return row


def update_followup(call_id: str, due_date: str) -> None:
    """Move the follow-up booked on this call to another date."""
    with db.engine().begin() as cx:
        cx.execute(update(db.followups).where(db.followups.c.call_id == call_id).values(due_date=due_date))


def cancel_followup(call_id: str) -> None:
    """Cancel the follow-up booked on this call."""
    with db.engine().begin() as cx:
        cx.execute(update(db.followups).where(db.followups.c.call_id == call_id).values(status="cancelled"))


# ---- 5. Products --------------------------------------------------------------------------------

def set_products(product_ids: list[str], **values: Any) -> None:
    """Change columns on several products at once, for example status="paused"."""
    if not product_ids:
        return
    with db.engine().begin() as cx:
        cx.execute(update(db.products).where(db.products.c.id.in_(product_ids)).values(**values))
