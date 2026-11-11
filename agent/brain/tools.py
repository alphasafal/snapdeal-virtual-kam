"""Everything the voice agent can look up or do for a seller.

Plain Python: no language model and no audio. The agent's tools in agent.py are thin
wrappers around the `KamTools` class here, so all of it can be tested without a microphone.

One `KamTools` object is created per call, for one seller. Its methods fall into five groups:

  1. Context      what the agent is told before it speaks (account_brief, memory_brief)
  2. Look-ups     read-only answers (stockout_products, cancellation_breakdown, pricing_gaps)
  3. Actions      things the seller can agree to (restock plan, pause listings, stock buffer,
                  price match, dispatch alerts, ticket, follow-up, escalation) and cancel_action
  4. Playbook     which of those actions fit this seller, biggest problem first
  5. Wrap-up      the call summary

HOW AN ACTION WORKS
  Every action that changes something takes `seller_confirmed`.
    seller_confirmed=False  -> nothing is saved; a proposal is returned for the agent to ask about
    seller_confirmed=True   -> the action is saved and its mock effect applied
  agent.py only passes True after its consent gate has checked the seller's own words.

WHAT IS MOCKED
  An action is a saved record plus a mock effect on the product table (for example a paused
  listing). Nothing is sent to a real Snapdeal system.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Optional

from . import repo
from .diagnosis import inr, newly_out_of_stock, undercut_products

# Returned by an action when the seller has not agreed yet.
NEEDS_CONFIRMATION = {
    "status": "needs_confirmation",
    "instruction": "Do not say this is done. Ask the seller for a clear yes first, then call again with seller_confirmed=true.",
}

RESTOCK_BUFFER = 1.2          # restock 20% above last month's units, to avoid running out again
MAX_PRICE_CUT_PCT = 40.0      # never propose cutting a price by more than this, whatever is asked
RECOMMENDED_ACTIONS = 3       # how many playbook actions Asha recommends unprompted (the brief asks for 2-3)


def spoken(amount: float) -> str:
    """A rupee amount rounded the way a person would say it aloud.

    45,450 -> "about 45 thousand rupees";  1,35,000 -> "about 1.35 lakh rupees"."""
    a = abs(amount)
    if a >= 100000:
        return f"about {a / 100000:.2f}".rstrip("0").rstrip(".") + " lakh rupees"
    if a >= 10000:
        return f"about {round(a / 1000)} thousand rupees"
    if a >= 1000:
        return f"about {int(round(a, -2)):,} rupees"
    return f"about {int(round(a / 50) * 50)} rupees"


def money(amount: float) -> str:
    """The exact figure plus how to say it, for the agent: "₹45,450 (say: about 45 thousand rupees)"."""
    return f"{inr(amount)} (say: {spoken(amount)})"


class KamTools:
    """What the agent knows and can do for one seller on one call."""

    # Actions the seller can ask to undo, and the reasons a hand-over to a person is allowed.
    CANCELLABLE = ("restock_plan", "pause_listings", "stock_buffer", "price_match", "dispatch_alerts",
                   "ticket", "followup")
    ESCALATION_CATEGORIES = ("payments", "account_or_policy", "complaint_about_snapdeal",
                             "seller_asked_for_a_person", "technical_problem", "other")

    def __init__(self, seller_id: str, call_id: str):
        self.seller_id = seller_id
        self.call_id = call_id
        self.seller = repo.get_seller(seller_id)
        if not self.seller:
            raise LookupError(f"unknown seller {seller_id}")
        # The diagnosis is computed once, before the agent says anything.
        self.diagnosis = repo.run_diagnosis(seller_id)
        repo.update_call(call_id, root_cause=self.diagnosis["primary_cause"])

    # =========================================================================================
    # 1. Context: what the agent is told before it speaks
    # =========================================================================================

    def account_brief(self) -> str:
        """The seller's numbers, the diagnosis and the playbook, as text for the agent's instructions.

        Every figure the agent is allowed to say about this account appears in here."""
        d, s = self.diagnosis, self.seller
        snap = d["snapshot"]
        lines = [
            f"Seller: {s['name']} ({s['category']}, {s['city']}). Owner: {s['owner_name']}.",
            f"Sales: {inr(snap['sales_prev'])} last month -> {inr(snap['sales_curr'])} this month ({snap['sales_change_pct']}%).",
            f"Orders: {snap['orders_prev']} -> {snap['orders_curr']}. Average selling price: {inr(snap['asp_prev'])} -> {inr(snap['asp_curr'])}.",
            f"Cancellation rate: {snap['cancel_rate_prev']:g}% -> {snap['cancel_rate_curr']:g}%. "
            f"Out-of-stock products: {snap['oos_prev']} -> {snap['oos_curr']}.",
            "", "DIAGNOSIS (computed by the diagnosis engine):", d["headline"],
        ]
        if d["status"] == "not_declining":
            lines.append("Sales are not falling. Reassure the seller, then mention the watch items below if any.")
            lines += [f"- Watch: {w}" for w in d["watch"]]
        for i, c in enumerate(d["causes"], 1):
            if c["impact_inr"] > 0:
                lines.append(f"Cause {i}: {c['title']} - {money(c['impact_inr'])} of the drop, {c['share_pct']}% [{c['confidence']}]")
            else:
                lines.append(f"Cause {i}: {c['title']} - not a measurable part of the drop, but it is costing money (see evidence)")
            lines += [f"   - {e}" for e in c["evidence"]]
            lines.append(f"   - Ask the seller: {c['question']}")
        can = d["cancellations"]
        lines.append(f"Cancellations: {can['cancelled_orders_curr']} orders worth {money(can['cancelled_value_inr'])} cancelled this month.")
        lines.append("Assumptions behind these numbers: " + " ".join(d["assumptions"]))

        steps = self.playbook() if d["status"] == "declining" else []
        if steps:
            # The assignment asks for two or three recommended actions, so the top three are
            # the recommendation and anything further is held back unless the seller asks.
            recommend, extra = steps[:RECOMMENDED_ACTIONS], steps[RECOMMENDED_ACTIONS:]
            lines += ["", "PLAYBOOK", "RECOMMEND (these, in this order, one at a time):"]
            lines += [f"{i}. {step}" for i, step in enumerate(recommend, 1)]
            if extra:
                lines += ["ONLY IF ASKED (offer only if the seller asks what else can be done):"]
                lines += [f"- {step}" for step in extra]
        lines += ["", f"Today is {repo.today_ist().strftime('%A, %d %B %Y')} (India time)."]
        return "\n".join(lines)

    def memory_brief(self) -> Optional[str]:
        """What was agreed on the most recent call where something was agreed, and progress since.

        Returns None when there is nothing to remember, so the agent opens as a first call."""
        for last in repo.recent_ended_calls(self.seller_id, before_call_id=self.call_id):
            acts = repo.get_actions(call_id=last["id"])
            notes = last.get("notes") or {}
            if not acts and not notes:
                continue                      # a dropped or empty call is not worth recalling
            when = "earlier"
            if last.get("ended_at"):
                when = (last["ended_at"] + repo.IST).strftime("%d %b")
            issue = (last.get("summary") or {}).get("issue") or last.get("root_cause")
            lines = [f"PREVIOUS CALL ({when}). Main issue then: {issue}"]
            for a in acts:
                status = a["progress"] or a["status"].replace("_", " ")
                lines.append(f"- Agreed: {a['title']} (due {a['due_date'] or 'n/a'}). Status now: {status}.")
            lines += [f"- Seller told us ({k}): {v}" for k, v in notes.items()]
            return "\n".join(lines)
        return None

    # =========================================================================================
    # Helpers shared by the look-ups and actions below
    # =========================================================================================

    def _existing(self, type_: str) -> Optional[dict]:
        """The action of this type already saved on this call, if any."""
        return next((a for a in repo.get_actions(call_id=self.call_id) if a["type"] == type_), None)

    def _due(self, days: int) -> str:
        """A due date `days` from today (India time), as YYYY-MM-DD."""
        return (repo.today_ist() + timedelta(days=days)).isoformat()

    def _planned_product_ids(self, type_: str) -> set[str]:
        """Products already covered by this kind of action on an EARLIER call,
        so a follow-up call does not propose the same thing twice."""
        ids: set[str] = set()
        for a in repo.get_actions(seller_id=self.seller_id):
            if a["type"] == type_ and a["call_id"] != self.call_id:
                ids |= {p["id"] for p in (a.get("detail") or {}).get("products", [])}
        return ids

    def _cancel_count(self, period: str, reason: str) -> int:
        """Orders cancelled for `reason` in "prev" (last month) or "curr" (this month)."""
        reasons = repo.get_cancel_reasons(self.seller_id)
        return sum(r["count"] for r in reasons[period] if r["reason"] == reason)

    def _cancel_rise(self, reason: str) -> int:
        """How many more orders were cancelled for `reason` this month than last month."""
        return self._cancel_count("curr", reason) - self._cancel_count("prev", reason)

    def _has_cancel_reasons(self) -> bool:
        """False for a seller entered with totals only: we know the rate, not the reasons."""
        return bool(repo.get_cancel_reasons(self.seller_id)["curr"])

    def _new_stockouts_without_names(self) -> int:
        """For a seller entered with totals only: how many more products are out of stock."""
        snap = self.diagnosis["snapshot"]
        return max(0, int(snap["oos_curr"]) - int(snap["oos_prev"]))

    def _stockout_estimate(self) -> float:
        """The rupees the diagnosis puts down to stockouts (0 if stockouts are not a cause)."""
        return next((c["impact_inr"] for c in self.diagnosis["causes"] if c["key"] == "stockouts"), 0)

    # =========================================================================================
    # 2. Look-ups: read-only, no confirmation needed
    # =========================================================================================

    def stockout_products(self, limit: int = 5) -> dict[str, Any]:
        """Which products ran out this month and what each one cost in sales."""
        products = repo.get_products(self.seller_id)
        if not products:
            n = self._new_stockouts_without_names()
            return {"count": n, "product_names_available": False,
                    "estimated_lost_sales": money(self._stockout_estimate()) if n else None,
                    "speaking_tip": "Product names are not on file for this seller. Ask which products ran out."}
        items = newly_out_of_stock(products)
        limit = max(1, min(int(limit), 10))
        return {
            "count": len(items),
            "total_lost_sales": money(sum(p.lost_sales for p in items)),
            "still_out_of_stock": sum(1 for p in items if not p.in_stock),
            "top": [dict(name=p.name, sold_last_month=p.units_prev, sold_this_month=p.units_curr,
                         days_out_of_stock=p.days_oos_curr, lost_sales=money(p.lost_sales),
                         back_in_stock_now=p.in_stock)
                    for p in items[:limit]],
            "speaking_tip": "Name at most three products aloud, then give the total.",
        }

    def cancellation_breakdown(self) -> dict[str, Any]:
        """Who is cancelling (the seller or the buyers) and the top reasons."""
        reasons = repo.get_cancel_reasons(self.seller_id)
        can = self.diagnosis["cancellations"]
        if not reasons["curr"]:
            return {"breakdown_available": False, "cancelled_orders_this_month": can["cancelled_orders_curr"],
                    "value_cancelled": money(can["cancelled_value_inr"]),
                    "speaking_tip": "The split by reason is not on file. Ask the seller who is cancelling and why."}

        def cancelled_by(period: str, side: str) -> int:
            """Orders cancelled by the "seller" or the "buyer" side in that month."""
            return sum(r["count"] for r in reasons[period] if r["side"] == side)

        top = sorted(reasons["curr"], key=lambda r: r["count"], reverse=True)
        return {
            "this_month": dict(seller_side=cancelled_by("curr", "seller"), buyer_side=cancelled_by("curr", "buyer")),
            "last_month": dict(seller_side=cancelled_by("prev", "seller"), buyer_side=cancelled_by("prev", "buyer")),
            "top_reasons_this_month": [f"{r['reason']} ({r['side']} side): {r['count']} orders" for r in top[:3]],
            "value_cancelled": money(can["cancelled_value_inr"]),
        }

    def pricing_gaps(self, limit: int = 5) -> dict[str, Any]:
        """In-stock products where a rival is cheaper, and what each one cost in sales."""
        done_before = self._planned_product_ids("price_match")
        items = [p for p in undercut_products(repo.get_products(self.seller_id)) if p.id not in done_before]
        limit = max(1, min(int(limit), 10))
        return {
            "already_matched_on_earlier_call": len(done_before),
            "count": len(items),
            "total_lost_sales": money(sum(p.lost_sales for p in items)),
            "top": [dict(name=p.name, your_price=inr(p.price), cheapest_rival=inr(p.competitor_price),
                         rival_cheaper_by_pct=round((p.price - p.competitor_price) / p.price * 100),
                         lost_sales=money(p.lost_sales)) for p in items[:limit]],
        }

    def record_seller_input(self, topic: str, detail: str) -> dict[str, Any]:
        """Save what the seller explained, and suggest how it should shape the plan."""
        repo.add_note(self.call_id, topic.strip().lower().replace(" ", "_")[:40], detail.strip()[:300])
        advice = {
            "supplier_delay": "Restock the top sellers first and pause listings the supplier cannot deliver within a week.",
            "cash_flow": "Restock only the top three by lost sales; they recover the most per rupee spent.",
            "missed_tracking": "Set a stock buffer so listings switch off before stock hits zero.",
            "discontinued": "Pause those listings so they stop causing cancellations.",
        }
        # Match on the topic, or on its first word appearing in what the seller said ("cash", "supplier").
        key = next((k for k in advice if k in topic.lower() or k.split("_")[0] in detail.lower()), None)
        return {"status": "noted", "suggestion": advice.get(key, "Use this when choosing which actions to propose.")}

    # =========================================================================================
    # 3. Actions: each one needs the seller's yes (seller_confirmed=True)
    # =========================================================================================

    def create_restock_plan(self, top_n: int = 5, seller_confirmed: bool = False) -> dict[str, Any]:
        """Restock the products that lost the most sales by running out.

        `top_n` lets the seller restock fewer products when cash is tight. Calling it again
        with a different number changes the saved plan instead of adding a second one."""
        products = repo.get_products(self.seller_id)
        if not products:
            return self._restock_plan_without_names(seller_confirmed)

        on_order = self._planned_product_ids("restock_plan")      # agreed on an earlier call
        out_now = [p for p in newly_out_of_stock(products) if not p.in_stock]
        items = [p for p in out_now if p.id not in on_order]
        if not items:
            if out_now:
                return {"status": "not_applicable", "reason": f"All {len(out_now)} products still out of stock "
                        "are already on the earlier restock plan. Ask what is delaying them instead."}
            return {"status": "not_applicable", "reason": "No products are out of stock right now."}

        chosen = items[:max(1, min(int(top_n), len(items)))]
        recovery = sum(p.lost_sales for p in chosen)
        if not seller_confirmed:
            return {**NEEDS_CONFIRMATION, "proposal": f"Restock the top {len(chosen)} products; "
                    f"they lost {money(recovery)} this month.", "products": [p.name for p in chosen[:3]]}

        detail = {"products": [dict(id=p.id, name=p.name, quantity=math.ceil(p.units_prev * RESTOCK_BUFFER),
                                    lost_sales_inr=p.lost_sales) for p in chosen]}
        title = f"Restock {len(chosen)} top products"
        existing = self._existing("restock_plan")
        if existing:                          # the seller changed their mind about how many
            if len(existing["detail"]["products"]) == len(chosen):
                return {"status": "already_done", "note": "This restock plan is already saved."}
            repo.update_action(existing["id"], title=title, detail=detail, expected_recovery_inr=recovery)
            action_id, due, status = existing["id"], existing["due_date"], "updated"
        else:
            act = repo.add_action(self.call_id, self.seller_id, "restock_plan", title, detail, recovery, self._due(3))
            action_id, due, status = act["id"], act["due_date"], "done"
        repo.set_products([p.id for p in chosen], status="active")   # never leave a restocked listing paused
        return {"status": status, "action_id": action_id, "due": due,
                "expected_recovery_per_month": "up to " + money(recovery),
                "quantities": "20% above last month's units for each product",
                "products": [p.name for p in chosen]}

    def _restock_plan_without_names(self, seller_confirmed: bool) -> dict[str, Any]:
        """The restock plan for a seller entered with totals only.

        We know how many products ran out but not which, so the plan covers all of them and
        the recovery figure is the diagnosis estimate, labelled as an estimate."""
        n = self._new_stockouts_without_names()
        if n == 0:
            return {"status": "not_applicable", "reason": "Out-of-stock products did not rise this month."}
        already = any(a["type"] == "restock_plan" for a in repo.get_actions(seller_id=self.seller_id)
                      if a["call_id"] != self.call_id)
        if already:
            return {"status": "not_applicable", "reason": "A restock plan from an earlier call is still open. "
                    "Ask what is delaying it instead."}
        estimate = self._stockout_estimate()
        if not seller_confirmed:
            return {**NEEDS_CONFIRMATION, "proposal": f"Restock the {n} products that ran out this month; the estimate "
                    f"is that they cost {money(estimate)} in sales. Ask which of them sell best, to restock those first."}
        if self._existing("restock_plan"):
            return {"status": "already_done", "note": "This restock plan is already saved."}
        act = repo.add_action(self.call_id, self.seller_id, "restock_plan",
                              f"Restock the {n} products that ran out", {"count": n, "estimated": True},
                              estimate or None, self._due(3))
        out = {"status": "done", "action_id": act["id"], "due": act["due_date"]}
        if estimate:
            out["expected_recovery_per_month"] = "up to " + money(estimate) + " (an estimate from totals)"
        return out

    def pause_unavailable_listings(self, include_recently_out: bool = False,
                                   seller_confirmed: bool = False) -> dict[str, Any]:
        """Pause out-of-stock listings that are not being restocked, so buyers cannot order
        them and trigger cancellations.

        Without a restock plan only listings dead for two months are paused, so a product
        the seller may still restock is never switched off by accident."""
        products = repo.get_products(self.seller_id)
        plan = self._existing("restock_plan")
        keep = {p["id"] for p in (plan or {}).get("detail", {}).get("products", [])}
        keep |= self._planned_product_ids("restock_plan")
        has_plan = bool(keep)
        targets = [p for p in products if not p.in_stock and p.id not in keep and p.status == "active"
                   and (p.oos_prev or has_plan or include_recently_out)]
        if not targets:
            return {"status": "not_applicable", "reason": "No other out-of-stock listings to pause."}
        if not seller_confirmed:
            return {**NEEDS_CONFIRMATION, "proposal": f"Pause {len(targets)} out-of-stock listings that are not being "
                    "restocked, so buyers cannot order them and trigger cancellations."}

        repo.set_products([p.id for p in targets], status="paused")
        detail = {"products": [dict(id=p.id, name=p.name) for p in targets]}
        existing = self._existing("pause_listings")
        if existing:                          # asked a second time: add to the same action
            merged = existing["detail"]["products"] + detail["products"]
            repo.update_action(existing["id"], title=f"Pause {len(merged)} out-of-stock listings",
                               detail={"products": merged})
            return {"status": "updated", "action_id": existing["id"], "paused": len(merged)}
        act = repo.add_action(self.call_id, self.seller_id, "pause_listings",
                              f"Pause {len(targets)} out-of-stock listings", detail, None, self._due(0))
        out = {"status": "done", "action_id": act["id"], "paused": len(targets)}
        if not has_plan and not include_recently_out:
            out["note"] = ("Only listings out of stock for two months were paused. Products that ran out this "
                           "month are left for the restock plan.")
        return out

    def set_stock_buffer(self, buffer_units: int = 2, seller_confirmed: bool = False) -> dict[str, Any]:
        """Hold back a few units per product, so a listing switches off before stock hits zero.

        The recovery figure is the extra "out of stock after order" cancellations this month,
        valued at the average selling price."""
        reason = "Out of stock after order"
        _, curr = repo.get_months(self.seller_id)
        recovery = max(0, self._cancel_rise(reason)) * curr.asp
        buffer_units = max(1, min(int(buffer_units), 10))
        if not seller_confirmed:
            why = (f" {self._cancel_count('curr', reason)} orders were cancelled this month for 'out of stock after order'."
                   if self._has_cancel_reasons() else "")
            return {**NEEDS_CONFIRMATION, "proposal": f"Keep a safety buffer of {buffer_units} units so listings switch off "
                    f"before stock runs out.{why}"}
        if self._existing("stock_buffer"):
            return {"status": "already_done"}
        act = repo.add_action(self.call_id, self.seller_id, "stock_buffer",
                              f"Safety stock buffer of {buffer_units} units on all listings",
                              {"buffer_units": buffer_units, "oos_after_order_cancels": self._cancel_count("curr", reason)},
                              recovery or None, self._due(0))
        out = {"status": "done", "action_id": act["id"]}
        if recovery:
            out["expected_recovery_per_month"] = "up to " + money(recovery)
        return out

    def match_rival_prices(self, top_n: int = 5, max_discount_pct: float = 15,
                           seller_confirmed: bool = False) -> dict[str, Any]:
        """Lower prices to the cheapest rival's on the products losing the most sales.

        A price is never cut by more than `max_discount_pct`, which is the limit the seller's
        margin allows. The new prices are stored on the action; the product table is left
        alone so the month being diagnosed is not rewritten."""
        done_before = self._planned_product_ids("price_match")
        items = [p for p in undercut_products(repo.get_products(self.seller_id)) if p.id not in done_before]
        if not items:
            reason = ("Prices on the undercut products were already matched on an earlier call."
                      if done_before else "No in-stock products are being undercut.")
            return {"status": "not_applicable", "reason": reason}

        chosen = items[:max(1, min(int(top_n), len(items)))]
        lowest_allowed = 1 - max(0.0, min(float(max_discount_pct), MAX_PRICE_CUT_PCT)) / 100
        plan = [dict(id=p.id, name=p.name, old_price=p.price,
                     new_price=float(max(p.competitor_price, round(p.price * lowest_allowed))),
                     lost_sales_inr=p.lost_sales) for p in chosen]
        recovery = sum(p.lost_sales for p in chosen)
        if not seller_confirmed:
            return {**NEEDS_CONFIRMATION, "proposal": f"Match the cheapest rival on {len(chosen)} products "
                    f"(never more than {max_discount_pct:g}% off). They lost {money(recovery)} this month.",
                    "example": f"{plan[0]['name']}: {inr(plan[0]['old_price'])} to {inr(plan[0]['new_price'])}",
                    "ask_first": "Confirm the seller's margin allows this discount."}
        if self._existing("price_match"):
            return {"status": "already_done"}
        act = repo.add_action(self.call_id, self.seller_id, "price_match",
                              f"Match rival prices on {len(chosen)} products", {"products": plan},
                              recovery, self._due(1))
        return {"status": "done", "action_id": act["id"],
                "expected_recovery_per_month": "up to " + money(recovery)}

    def enable_dispatch_alerts(self, seller_confirmed: bool = False) -> dict[str, Any]:
        """Turn on a daily pickup reminder and an alert when an order nears its dispatch deadline.

        The recovery figure is the extra "late dispatch" cancellations this month, valued at
        the average selling price."""
        reason = "Late dispatch"
        _, curr = repo.get_months(self.seller_id)
        recovery = max(0, self._cancel_rise(reason)) * curr.asp
        if not seller_confirmed:
            return {**NEEDS_CONFIRMATION, "proposal": "Turn on a daily pickup reminder and an alert when an order is close "
                    f"to its dispatch deadline. {self._cancel_count('curr', reason)} orders were cancelled for late dispatch this month."}
        if self._existing("dispatch_alerts"):
            return {"status": "already_done"}
        act = repo.add_action(self.call_id, self.seller_id, "dispatch_alerts",
                              "Daily pickup reminder and dispatch deadline alerts",
                              {"late_dispatch_cancels": self._cancel_count("curr", reason)}, recovery or None, self._due(0))
        out = {"status": "done", "action_id": act["id"]}
        if recovery:
            out["expected_recovery_per_month"] = "up to " + money(recovery)
        return out

    def raise_ticket(self, category: str, note: str) -> dict[str, Any]:
        """Ask the Snapdeal team to look at something (for example a visibility review).

        No confirmation is needed because it changes nothing for the seller. One ticket per
        category per call."""
        label = f"Ticket to Snapdeal team: {category.strip()[:60]}"
        same = next((a for a in repo.get_actions(call_id=self.call_id)
                     if a["type"] == "ticket" and a["title"].lower() == label.lower()), None)
        # The reference number is kept on screen and in the record. It is not handed to the
        # model to read aloud: on a live call Asha spelled it out as "zero A four three C E".
        heard = "Tell the seller the team will reply within two working days. Do not read out a reference number."
        if same:
            return {"status": "already_done", "say": heard}
        act = repo.add_action(self.call_id, self.seller_id, "ticket", label,
                              {"category": category, "note": note.strip()[:400]}, None, self._due(2))
        return {"status": "done", "action_id": act["id"], "say": heard}

    def schedule_followup(self, days: int = 7, on_date: Optional[str] = None) -> dict[str, Any]:
        """Book the follow-up call, or move it if the seller prefers another day.

        Give either `days` from today or a specific `on_date` (YYYY-MM-DD). The date must be
        from tomorrow onwards and within 30 days."""
        today = repo.today_ist()
        if on_date:
            try:
                target = date.fromisoformat(on_date.strip())
            except ValueError:
                return {"status": "invalid_date", "instruction": "Pass on_date as YYYY-MM-DD, or use days."}
        else:
            target = today + timedelta(days=max(1, min(int(days), 30)))
        if target <= today:
            return {"status": "invalid_date", "earliest": (today + timedelta(days=1)).isoformat(),
                    "instruction": "A follow-up must be from tomorrow onwards. Offer tomorrow or a later day."}
        if target > today + timedelta(days=30):
            return {"status": "invalid_date", "instruction": "Keep the follow-up within 30 days."}

        due = target.isoformat()
        days_away = (target - today).days
        title = f"Follow-up call on {target.strftime('%d %b')}"
        existing = self._existing("followup")
        if existing:
            if existing["due_date"] == due:
                return {"status": "already_done", "date": due, "say_date": target.strftime("%A, %d %B")}
            repo.update_action(existing["id"], title=title, due_date=due, detail={"days": days_away})
            repo.update_followup(self.call_id, due)
            status = "rescheduled"
        else:
            repo.add_followup(self.seller_id, self.call_id, due, "Check progress on agreed actions")
            repo.add_action(self.call_id, self.seller_id, "followup", title, {"days": days_away}, None, due)
            status = "done"
        return {"status": status, "date": due, "say_date": target.strftime("%A, %d %B")}

    def escalate_to_human(self, category: str, reason: str) -> dict[str, Any]:
        """Hand over to a human account manager.

        Refused for thanks, goodbyes or changing a follow-up date: on a test call the model
        escalated for exactly those, which would waste a person's time."""
        category = category.strip().lower().replace(" ", "_")
        if category not in self.ESCALATION_CATEGORIES:
            category = "other"
        text = reason.lower()
        routine = any(w in text for w in ("follow-up", "follow up", "followup", "reschedul", "gratitude",
                                          "thank", "satisf", "no further action", "goodbye"))
        if routine and category in ("other", "seller_asked_for_a_person"):
            return {"status": "not_needed", "instruction": "This does not need a person. To change the follow-up "
                    "day call schedule_followup again; for thanks or goodbye just close the call politely."}
        repo.update_call(self.call_id, escalated=True)
        if not self._existing("escalation"):
            repo.add_action(self.call_id, self.seller_id, "escalation", "Escalated to a human account manager",
                            {"category": category, "reason": reason.strip()[:400]}, None, self._due(1))
        return {"status": "done", "say": "A human account manager will call back within one working day."}

    def cancel_action(self, action: str = "all") -> dict[str, Any]:
        """Undo something saved on this call when the seller did not want it or changed their mind.

        `action` is "all" or one of CANCELLABLE. The action is marked cancelled (kept for the
        record, hidden everywhere else) and its mock effect is reversed."""
        wanted = action.strip().lower().replace(" ", "_")
        aliases = {"restock": "restock_plan", "pause": "pause_listings", "buffer": "stock_buffer",
                   "price": "price_match", "prices": "price_match", "dispatch": "dispatch_alerts",
                   "alerts": "dispatch_alerts", "follow_up": "followup", "follow-up": "followup"}
        wanted = aliases.get(wanted, wanted)
        if wanted != "all" and wanted not in self.CANCELLABLE:
            return {"status": "unknown_action", "choose_from": ["all", *self.CANCELLABLE]}
        targets = [a for a in repo.get_actions(call_id=self.call_id)
                   if a["type"] in self.CANCELLABLE and (wanted == "all" or a["type"] == wanted)]
        if not targets:
            return {"status": "nothing_to_cancel", "note": "Nothing matching is saved on this call."}
        for a in targets:
            if a["type"] == "pause_listings":           # switch those listings back on
                repo.set_products([p["id"] for p in a["detail"].get("products", [])], status="active")
            if a["type"] == "followup":
                repo.cancel_followup(self.call_id)
            repo.update_action(a["id"], status="cancelled", progress="cancelled at the seller's request")
        return {"status": "cancelled", "cancelled": [a["title"] for a in targets],
                "say": "Tell the seller plainly that it has been removed and nothing will happen without their yes."}

    # =========================================================================================
    # 4. Playbook: which actions fit this seller, biggest problem first
    # =========================================================================================

    def playbook(self) -> list[str]:
        """The actions the agent should propose for this seller, in order.

        Decided here in code, so the agent never proposes something irrelevant (on a test
        call the model offered price cuts to a seller whose pricing was fine). Each step is
        "tool_name - what to propose". Steps are ranked by the rupees at stake."""
        impact = {c["key"]: c["impact_inr"] for c in self.diagnosis["causes"]}
        cancellations = self.diagnosis["cancellations"]
        _, curr = repo.get_months(self.seller_id)
        has_products = bool(repo.get_products(self.seller_id))
        has_reasons = self._has_cancel_reasons()
        ranked: list[tuple[float, str]] = []      # (rupees at stake, step)

        # Stockouts: restock, then pause what is not being restocked.
        if "stockouts" in impact:
            proposal = self.create_restock_plan(5)
            if proposal["status"] == "needs_confirmation":
                tip = " Use fewer products if cash is tight." if has_products else ""
                ranked.append((impact["stockouts"], f"create_restock_plan - {proposal['proposal']}{tip}"))
                if has_products:
                    ranked.append((impact["stockouts"] - 1, "pause_unavailable_listings - after the restock plan, "
                                   "pause the out-of-stock listings that are not being restocked."))

        # Orders cancelled because stock ran out after the order: a safety buffer prevents that.
        oos_cancel_rise = self._cancel_rise("Out of stock after order")
        if oos_cancel_rise > 0:
            ranked.append((oos_cancel_rise * curr.asp, f"set_stock_buffer - {self.set_stock_buffer(2)['proposal']}"))
        elif not has_reasons and "stockouts" in impact and cancellations["rate_change_points"] >= 2:
            ranked.append((cancellations["extra_vs_last_month_inr"],
                           "set_stock_buffer - keep a safety buffer of 2 units so listings switch off before stock "
                           "runs out. First ask whether the extra cancellations came from stock running out."))

        # Rivals are cheaper: match their prices, within the seller's margin.
        if "pricing" in impact:
            proposal = self.match_rival_prices(5)
            if proposal["status"] == "needs_confirmation":
                ranked.append((impact["pricing"], f"match_rival_prices - {proposal['proposal']} "
                               "Ask what discount their margin allows first."))

        # Orders cancelled for late dispatch: reminders and deadline alerts.
        late_rise = self._cancel_rise("Late dispatch")
        if late_rise > 0:
            ranked.append((late_rise * curr.asp, f"enable_dispatch_alerts - {self.enable_dispatch_alerts()['proposal']}"))
        elif not has_reasons and cancellations["rate_change_points"] >= 2:
            ranked.append((0, "enable_dispatch_alerts - only if the seller says orders have been going out late."))

        steps = [step for _, step in sorted(ranked, key=lambda pair: pair[0], reverse=True)][:4]

        # Lost visibility has no direct fix the seller can make; ask the Snapdeal team to review it.
        if "service_quality" in impact or "traffic" in impact:
            steps.append("raise_ticket - ask the Snapdeal team for a visibility review once the fixes above are "
                         "in place. No rupee figure for this one.")
        return steps

    # =========================================================================================
    # 5. Wrap-up: the call summary
    # =========================================================================================

    def build_summary(self) -> dict[str, Any]:
        """The call's summary, built fresh from the database: the issue, causes, what the
        seller said, what was agreed, what was cancelled, and the follow-up date."""
        d = self.diagnosis
        everything = repo.get_actions(call_id=self.call_id, include_cancelled=True)
        agreed = [a for a in everything if a["status"] != "cancelled"]
        call = repo.get_call(self.call_id) or {}
        followup = next((a for a in agreed if a["type"] == "followup"), None)
        return {
            "issue": d["headline"],
            "causes": [f"{c['title']}: {inr(c['impact_inr'])} ({c['share_pct']}% of the drop)" for c in d["causes"]],
            "seller_said": call.get("notes") or {},
            "actions": [dict(title=a["title"], due=a["due_date"],
                             expected_recovery_inr=a["expected_recovery_inr"]) for a in agreed
                        if a["type"] != "followup"],
            "cancelled": [a["title"] for a in everything if a["status"] == "cancelled"],
            "expected_recovery_inr": sum(a["expected_recovery_inr"] or 0 for a in agreed),
            "followup_date": followup["due_date"] if followup else None,
            "escalated": bool(call.get("escalated")),
            "sent_via": "WhatsApp summary (mock, not actually sent)",
        }

    def wrap_up(self) -> dict[str, Any]:
        """Save the summary and hand it to the agent to read out. Called once, near the end."""
        summary = self.build_summary()
        repo.update_call(self.call_id, summary=summary)
        out = {"status": "saved", "summary": summary,
               "speaking_tip": "Say the main issue in one sentence, then each action with its deadline, "
                               "then the follow-up date. Under 20 seconds."}
        if summary["expected_recovery_inr"]:
            out["total_expected_recovery"] = "up to " + money(summary["expected_recovery_inr"]) + " per month"
        return out
