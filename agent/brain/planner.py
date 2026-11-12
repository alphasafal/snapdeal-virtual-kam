"""The what-if planner: which actions are open to a seller, and what each could win back.

The web app's planner page lets a team member (or the seller) tick actions and see the
sales that could come back. The options and their rupee figures are worked out here, in
plain Python, with the same arithmetic the voice agent's tools use (see tools.py). The
nightly scan (jobs.py) stores the result so the web app only has to read it.

Every figure is an upper limit: it assumes the action works fully for a whole month.

What an action costs is worked out too, because "how much money do I need?" is the first
thing a seller asks. A restock needs stock to be bought; a price match gives up margin. The
purchase cost of stock is not in the data, so it is an ASSUMPTION (60% of the selling price)
that the planner page lets the user change.
"""
from __future__ import annotations

from typing import Any

import math

from . import repo
from .diagnosis import newly_out_of_stock, undercut_products
from .tools import RESTOCK_BUFFER

FIRST_BATCH = 5             # how many products the first restock or price-match step covers
STOCK_COST_SHARE = 0.60     # ASSUMED: stock is bought at 60% of its selling price (editable on the page)
MATCH_DISCOUNT_LIMIT = 0.15  # a price is matched down by at most 15%, the limit Asha proposes by default


def _cancel_rise(reasons: dict[str, list[dict]], reason: str) -> int:
    """How many more orders were cancelled for this reason this month than last month."""
    def count(period: str) -> int:
        return sum(r["count"] for r in reasons[period] if r["reason"] == reason)
    return count("curr") - count("prev")


def _more_orders(count: int) -> str:
    """ "1 more order was" or "13 more orders were", so the sentence reads right for one."""
    return f"{count} more order was" if count == 1 else f"{count} more orders were"


def _names(products: list) -> str:
    """A short, readable list of product names: the first three, then how many more."""
    shown = ", ".join(p.name for p in products[:3])
    return shown + (f" and {len(products) - 3} more" if len(products) > 3 else "")


def restock_lines(products: list) -> list[dict[str, Any]]:
    """What restocking each product takes, biggest loss first.

    units            the quantity Asha's restock plan orders: 20% above last month's sales
    stock_value_inr  those units at the selling price (the page applies the cost share to it)
    recover_inr      the sales the product lost this month"""
    return [dict(name=p.name, units=math.ceil(p.units_prev * RESTOCK_BUFFER),
                 stock_value_inr=float(math.ceil(p.units_prev * RESTOCK_BUFFER) * p.price),
                 recover_inr=float(p.lost_sales)) for p in products]


def margin_given_up(products: list) -> float:
    """Rupees of margin a month a price match gives up: the price cut on last month's volume."""
    lowest = 1 - MATCH_DISCOUNT_LIMIT
    return float(sum((p.price - max(p.competitor_price, round(p.price * lowest))) * p.units_prev for p in products))


def plan_options(seller_id: str, diagnosis: dict[str, Any]) -> dict[str, Any]:
    """The actions open to this seller, biggest first, and the most they could recover together.

    Returns {"options": [...], "recoverable_inr": float, "gap_inr": float}. Each option is
    {"key", "title", "detail", "recover_inr", "when"}; recover_inr is None when no rupee
    figure can honestly be put on it. Restock options also carry "items" (one line per
    product, see restock_lines) with the assumed "cost_share"; price options carry "margin_inr"."""
    gap = float(diagnosis.get("gap_inr") or 0)
    if gap <= 0:
        return {"options": [], "recoverable_inr": 0.0, "gap_inr": 0.0}

    causes = {c["key"] for c in diagnosis["causes"] if c["impact_inr"] > 0}
    products = repo.get_products(seller_id)
    _, this_month = repo.get_months(seller_id)
    reasons = repo.get_cancel_reasons(seller_id)
    options: list[dict[str, Any]] = []

    def add(key: str, title: str, detail: str, recover: float | None, when: str, **cost: Any) -> None:
        options.append(dict(key=key, title=title, detail=detail, when=when,
                            recover_inr=float(recover) if recover else None, **cost))

    # Products that ran out: restock the biggest losers first, then the rest.
    if "stockouts" in causes and products:
        out_now = [p for p in newly_out_of_stock(products) if not p.in_stock]
        first, rest = out_now[:FIRST_BATCH], out_now[FIRST_BATCH:]
        if first:
            add("restock_top", f"Restock the top {len(first)} products that ran out", _names(first),
                sum(p.lost_sales for p in first), "within 3 days", items=restock_lines(first), cost_share=STOCK_COST_SHARE)
        if rest:
            add("restock_rest", f"Restock the other {len(rest)} products that ran out", _names(rest),
                sum(p.lost_sales for p in rest), "within 2 weeks", items=restock_lines(rest), cost_share=STOCK_COST_SHARE)

    # Orders cancelled because stock ran out after the order was placed.
    oos_cancels = _cancel_rise(reasons, "Out of stock after order")
    if oos_cancels > 0:
        add("stock_buffer", "Keep a safety buffer of 2 units on every listing",
            f"Listings switch off before stock hits zero. {_more_orders(oos_cancels)} cancelled "
            "for 'out of stock after order' this month.", oos_cancels * this_month.asp, "today")

    # Rivals are cheaper on the products that lost the most.
    if "pricing" in causes and products:
        undercut = undercut_products(products)
        first, rest = undercut[:FIRST_BATCH], undercut[FIRST_BATCH:]
        if first:
            add("price_top", f"Match the cheapest rival on the top {len(first)} products", _names(first),
                sum(p.lost_sales for p in first), "tomorrow", margin_inr=margin_given_up(first))
        if rest:
            add("price_rest", f"Match the cheapest rival on {len(rest)} more products", _names(rest),
                sum(p.lost_sales for p in rest), "this week", margin_inr=margin_given_up(rest))

    # Orders cancelled because they were dispatched late.
    late_cancels = _cancel_rise(reasons, "Late dispatch")
    if late_cancels > 0:
        add("dispatch_alerts", "Daily pickup reminder and dispatch-deadline alerts",
            f"{_more_orders(late_cancels)} cancelled for late dispatch this month.",
            late_cancels * this_month.asp, "today")

    # Lost visibility has no direct fix the seller can make.
    if "service_quality" in causes or "traffic" in causes:
        add("visibility_review", "Ask the Snapdeal team for a visibility review",
            "Rating and search position recover slowly once service is fixed; a review can speed that up.",
            None, "after the fixes above")

    options.sort(key=lambda option: option["recover_inr"] or 0, reverse=True)
    total = sum(option["recover_inr"] or 0 for option in options)
    return {"options": options, "recoverable_inr": min(total, gap), "gap_inr": gap}
