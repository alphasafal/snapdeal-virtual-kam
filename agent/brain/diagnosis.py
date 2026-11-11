"""The diagnosis engine: why did this seller's sales fall, and by how much for each reason?

This is plain arithmetic. No language model is involved. The voice agent never works out
a number itself; it only speaks the numbers this module returns.

HOW IT WORKS, using the seller from the assignment brief
---------------------------------------------------------
    Last month:  sales ₹2,00,000   orders 400   price ₹500   cancellations 8%    out of stock 5
    This month:  sales ₹1,35,000   orders 270   price ₹500   cancellations 14%   out of stock 18

  Step 0. The drop.        ₹2,00,000 - ₹1,35,000 = ₹65,000 lost.
  Step 1. Price or volume? Price is unchanged, orders fell by 130, so all ₹65,000 is lost volume.
  Step 2. Stockouts.       13 more products ran out. Add up the sales those products lost:
                           ₹45,450 (70% of the drop). This is MEASURED from product data.
  Step 3. Pricing.         No rival is undercutting the in-stock products: ₹0.
  Step 4. What is left.    ₹65,000 - ₹45,450 = ₹19,550 (30%). Cancellations rose sharply and
                           the rating slipped, so this leftover is put down to lost visibility
                           from poor service. This is INFERRED, not measured, and says so.
  Separately: cancelled orders are worth ₹18,900 this month. Sales in the data are counted
  before cancellations, so this is money lost on top of the ₹65,000.

HOW SURE EACH NUMBER IS
-----------------------
  measured   read straight from product-level data
  estimated  worked out from the monthly totals, with the assumption written down
  inferred   the part of the drop left over once the measured causes are taken out

THE FOUR POSSIBLE CAUSES (the `key` of a Cause)
-----------------------------------------------
  stockouts        products ran out of stock
  pricing          the seller cut prices, or rivals are cheaper
  service_quality  cancellations and late dispatch are hurting rating and visibility
  traffic          fewer buyers are seeing the listings, for a reason the data does not show
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---- The data the engine works on -------------------------------------------------------

@dataclass
class Month:
    """One month of a seller's numbers. The first five fields are the ones in the brief."""
    sales: float                                # rupees, before cancellations
    orders: int
    cancel_rate: float                          # percent, for example 14.0
    asp: float                                  # average selling price, in rupees
    oos_products: int                           # how many products are out of stock
    # Optional extras. The brief does not give these; the mock sellers have them.
    visits: Optional[int] = None                # visits to the seller's listings
    rating: Optional[float] = None              # seller rating out of 5
    price_gap_pct: Optional[float] = None       # how much dearer than the cheapest rival, on top products
    late_dispatch_rate: Optional[float] = None  # percent of orders dispatched late


@dataclass
class Product:
    """One product in the seller's catalogue."""
    id: str
    name: str
    price: float
    units_prev: int                             # units sold last month
    units_curr: int                             # units sold this month
    in_stock: bool                              # in stock right now?
    oos_prev: bool = False                      # was it already out of stock last month?
    days_oos_curr: int = 0                      # days out of stock this month
    competitor_price: Optional[float] = None    # the cheapest rival's price, if known
    status: str = "active"                      # "active" or "paused"

    @property
    def lost_units(self) -> int:
        """How many fewer units it sold this month than last month (never negative)."""
        return max(0, self.units_prev - self.units_curr)

    @property
    def lost_sales(self) -> float:
        """Those lost units in rupees."""
        return self.lost_units * self.price


@dataclass
class Cause:
    """One reason for the drop, with its size in rupees and the evidence for it."""
    key: str                                    # stockouts | pricing | service_quality | traffic
    title: str                                  # a plain-language name the agent can say
    impact_inr: float                           # sales lost this month because of this cause
    confidence: str                             # measured | estimated | inferred
    evidence: list[str] = field(default_factory=list)
    question: str = ""                          # what only the seller can tell us about it
    share_pct: float = 0.0                      # impact as a share of the whole drop


# ---- Thresholds, named so the rules below read like sentences ---------------------------

RIVAL_CHEAPER_BY = 0.05           # a rival counts as undercutting when it is 5% or more cheaper
OWN_PRICE_MOVED_PCT = 3           # the seller's own average price moved by 3% or more
RIVAL_GAP_WIDENED_POINTS = 5      # the gap to the cheapest rival grew by 5 points or more
CANCELLATIONS_JUMPED_POINTS = 4   # the cancellation rate rose by 4 points or more
RATING_SLIPPED = 0.3              # the seller rating fell by 0.3 or more
LEFTOVER_WORTH_NAMING = 0.05      # only name the leftover if it is 5% or more of the drop
HIGH_RISK_DROP_PCT = 25           # sales down 25% or more: high risk
MEDIUM_RISK_DROP_PCT = 10         # sales down 10% or more: medium risk
DEFAULT_CATALOGUE_SIZE = 60       # used when a seller entered by hand gives no catalogue size

STOCKOUT_QUESTION = "Why did these products run out: supplier delay, cash tied up, or the stock level was missed?"


# ---- Small helpers ------------------------------------------------------------------------

def inr(amount: float) -> str:
    """Format rupees with Indian digit grouping: 135000 -> ₹1,35,000."""
    n = int(round(amount))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]          # the last three digits, then groups of two
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}"


def _pct_change(prev: float, curr: float) -> float:
    """Percentage change from prev to curr, to one decimal place (0 if prev is 0)."""
    return 0.0 if not prev else round((curr - prev) / prev * 100, 1)


def newly_out_of_stock(products: list[Product]) -> list[Product]:
    """Products that ran out this month (they were sellable last month), biggest loss first."""
    items = [p for p in products if not p.oos_prev and (not p.in_stock or p.days_oos_curr > 0)]
    return sorted(items, key=lambda p: p.lost_sales, reverse=True)


def undercut_products(products: list[Product]) -> list[Product]:
    """In-stock products where a rival is clearly cheaper and we sold less, biggest loss first."""
    items = [
        p for p in products
        if p.in_stock and p.days_oos_curr == 0 and p.competitor_price
        and p.price > p.competitor_price * (1 + RIVAL_CHEAPER_BY)
        and p.lost_units > 0
    ]
    return sorted(items, key=lambda p: p.lost_sales, reverse=True)


def _watch_items(prev: Month, curr: Month) -> list[str]:
    """Things worth mentioning even when sales are not falling."""
    items = []
    if curr.oos_products > prev.oos_products:
        items.append(f"Out-of-stock products up from {prev.oos_products} to {curr.oos_products}.")
    if curr.cancel_rate > prev.cancel_rate + 1:
        items.append(f"Cancellation rate up from {prev.cancel_rate:g}% to {curr.cancel_rate:g}%.")
    return items


# ---- The engine ------------------------------------------------------------------------------

def diagnose(prev: Month, curr: Month, products: Optional[list[Product]] = None,
             catalogue_size: Optional[int] = None) -> dict[str, Any]:
    """Explain the change in sales between two months.

    prev, curr       last month and this month
    products         the catalogue, if we have it (a seller entered by hand has none)
    catalogue_size   how many products are listed, used only when `products` is empty

    Returns a dict with: status ("declining" or "not_declining"), headline, gap_inr,
    causes (ranked, biggest first), primary_cause, risk_level, cancellations, snapshot,
    assumptions and watch. See the module docstring for a worked example.
    """
    products = products or []
    assumptions: list[str] = [
        "Sales are counted before cancellations (sales = orders x average selling price in the data).",
    ]

    # Step 0: how big is the drop?
    gap = prev.sales - curr.sales
    orders_gap = prev.orders - curr.orders
    snapshot = {
        "sales_prev": prev.sales, "sales_curr": curr.sales,
        "sales_change_pct": _pct_change(prev.sales, curr.sales),
        "orders_prev": prev.orders, "orders_curr": curr.orders,
        "orders_change_pct": _pct_change(prev.orders, curr.orders),
        "asp_prev": prev.asp, "asp_curr": curr.asp,
        "cancel_rate_prev": prev.cancel_rate, "cancel_rate_curr": curr.cancel_rate,
        "oos_prev": prev.oos_products, "oos_curr": curr.oos_products,
    }

    # Cancelled orders are money lost on top of the sales drop, because sales are counted
    # before cancellations. "extra" is how much more was cancelled than at last month's rate.
    cancelled_value = curr.orders * curr.cancel_rate / 100 * curr.asp
    extra_cancel_value = curr.orders * max(0.0, curr.cancel_rate - prev.cancel_rate) / 100 * curr.asp
    cancellations = {
        "cancelled_orders_curr": round(curr.orders * curr.cancel_rate / 100),
        "cancelled_value_inr": round(cancelled_value),
        "extra_vs_last_month_inr": round(extra_cancel_value),
        "rate_change_points": round(curr.cancel_rate - prev.cancel_rate, 1),
    }

    if gap <= 0:        # sales did not fall: say so, and never invent a problem
        return {
            "status": "not_declining",
            "headline": f"Sales are not down: {inr(prev.sales)} last month, {inr(curr.sales)} this month.",
            "gap_inr": 0, "orders_gap": 0, "snapshot": snapshot, "causes": [],
            "primary_cause": None, "risk_level": "low", "cancellations": cancellations,
            "price_effect_inr": 0, "volume_effect_inr": 0, "assumptions": assumptions,
            "watch": _watch_items(prev, curr),
        }

    # Step 1: is it price or volume?
    #   price effect  = change in price  x orders now      (negative means lower prices cost sales)
    #   volume effect = change in orders x price last month (negative means fewer orders cost sales)
    # The two add up to the change in sales.
    price_effect = (curr.asp - prev.asp) * curr.orders
    volume_effect = (curr.orders - prev.orders) * prev.asp
    volume_gap = max(0.0, -volume_effect)         # rupees lost because fewer orders came in
    own_price_change_pct = _pct_change(prev.asp, curr.asp)

    causes: list[Cause] = []

    # Step 2: how much of the lost volume is stockouts?
    stock_loss = _stockout_cause(prev, curr, products, catalogue_size, volume_gap, causes, assumptions)

    # Step 3: how much is pricing?
    pricing_loss = _pricing_cause(prev, curr, products, gap, price_effect, own_price_change_pct,
                                  volume_gap - stock_loss, causes)

    # Step 4: whatever is left is lost visibility; label it by what the service numbers say.
    leftover = max(0.0, volume_gap - stock_loss - pricing_loss)
    _leftover_cause(prev, curr, gap, leftover, cancelled_value, extra_cancel_value, causes)

    # Tidy up: drop a measured cause that explains nothing, round, rank biggest first.
    causes = [c for c in causes if not (c.confidence == "measured" and c.impact_inr <= 0)]
    for c in causes:
        c.impact_inr = round(c.impact_inr)
        c.share_pct = round(c.impact_inr / gap * 100) if gap else 0
    causes.sort(key=lambda c: c.impact_inr, reverse=True)

    drop_pct = abs(snapshot["sales_change_pct"])
    if drop_pct >= HIGH_RISK_DROP_PCT:
        risk = "high"
    elif drop_pct >= MEDIUM_RISK_DROP_PCT:
        risk = "medium"
    else:
        risk = "low"

    headline = (f"Sales fell {inr(gap)} ({drop_pct:g}%): {inr(prev.sales)} to {inr(curr.sales)}, "
                f"with {orders_gap} fewer orders.")
    if abs(own_price_change_pct) < OWN_PRICE_MOVED_PCT:
        headline += " Price per order is unchanged, so this is a volume problem."

    return {
        "status": "declining",
        "headline": headline,
        "gap_inr": round(gap), "orders_gap": orders_gap,
        "snapshot": snapshot,
        "price_effect_inr": round(price_effect), "volume_effect_inr": round(volume_effect),
        "causes": [c.__dict__ for c in causes],
        "primary_cause": causes[0].key if causes else None,
        "risk_level": risk,
        "cancellations": cancellations,
        "assumptions": assumptions,
        "watch": _watch_items(prev, curr),
    }


def _stockout_cause(prev: Month, curr: Month, products: list[Product], catalogue_size: Optional[int],
                    volume_gap: float, causes: list[Cause], assumptions: list[str]) -> float:
    """Step 2. Add a stockout cause if products ran out, and return the rupees it explains.

    With product data the loss is measured: the sales those products lost. Without it the
    loss is estimated from totals, and the assumption is written into `assumptions`.
    Either way it can never be more than the lost volume."""
    stock_items = newly_out_of_stock(products)
    if stock_items:
        lost = sum(p.lost_sales for p in stock_items)
        stock_loss = min(lost, volume_gap)
        top = stock_items[0]
        causes.append(Cause(
            "stockouts", "Products ran out of stock", stock_loss, "measured",
            [f"Out-of-stock products went from {prev.oos_products} to {curr.oos_products}.",
             f"{len(stock_items)} product(s) ran out this month and sold {inr(lost)} less than last month.",
             f"Biggest single loss: {top.name}, down {inr(top.lost_sales)}."],
            STOCKOUT_QUESTION))
        return stock_loss

    new_oos_count = max(0, curr.oos_products - prev.oos_products)
    if new_oos_count == 0:
        return 0.0

    # No product rows: assume each product that ran out sold like an average product.
    size = catalogue_size or DEFAULT_CATALOGUE_SIZE
    if not catalogue_size:
        assumptions.append(f"Catalogue size not given; assumed {DEFAULT_CATALOGUE_SIZE} listed products.")
    selling_last_month = max(1, size - prev.oos_products)
    stock_loss = min(new_oos_count * prev.sales / selling_last_month, volume_gap)
    assumptions.append("No product-level data: each newly out-of-stock product is assumed to have sold "
                       "like an average product and to have been unavailable all month (upper estimate).")
    causes.append(Cause(
        "stockouts", "Products ran out of stock", stock_loss, "estimated",
        [f"Out-of-stock products went from {prev.oos_products} to {curr.oos_products}.",
         f"{new_oos_count} more products unavailable out of about {size} listed."],
        STOCKOUT_QUESTION))
    return stock_loss


def _pricing_cause(prev: Month, curr: Month, products: list[Product], gap: float, price_effect: float,
                   own_price_change_pct: float, volume_left: float, causes: list[Cause]) -> float:
    """Step 3. Add a pricing cause if there is one, and return the rupees it explains.

    Three cases, checked in this order:
      a) the seller's own average price fell noticeably
      b) product data shows rivals undercutting in-stock products that then sold less
      c) no product data, but the gap to the cheapest rival widened (flagged, with no rupee figure)
    """
    undercut = undercut_products(products)
    gap_rise = None
    if prev.price_gap_pct is not None and curr.price_gap_pct is not None:
        gap_rise = curr.price_gap_pct - prev.price_gap_pct

    if price_effect < 0 and abs(own_price_change_pct) >= OWN_PRICE_MOVED_PCT:      # case a
        pricing_loss = min(-price_effect, gap)    # if orders grew, price explains the whole drop, not more
        evidence = [f"Average selling price moved from {inr(prev.asp)} to {inr(curr.asp)} ({own_price_change_pct}%)."]
        if curr.orders > prev.orders:
            evidence.append(f"Orders actually rose from {prev.orders} to {curr.orders}; "
                            "lower prices more than cancelled that out.")
        causes.append(Cause("pricing", "Average selling price fell", pricing_loss, "measured", evidence,
                            "Did you cut prices or run heavier discounts this month?"))
        return pricing_loss

    if undercut:                                                                   # case b
        lost = sum(p.lost_sales for p in undercut)
        pricing_loss = min(lost, max(0.0, volume_left))
        top = undercut[0]
        cheaper_pct = round((top.price - top.competitor_price) / top.price * 100)
        evidence = [
            f"{len(undercut)} in-stock products are priced above the cheapest rival and lost {inr(lost)} in sales.",
            f"Example: {top.name} is {inr(top.price)}, a rival sells it at {inr(top.competitor_price)} ({cheaper_pct}% cheaper).",
        ]
        if gap_rise is not None:
            evidence.append(f"Price gap to the cheapest rival on top products went from "
                            f"{prev.price_gap_pct}% to {curr.price_gap_pct}%.")
        causes.append(Cause(
            "pricing", "Rivals are undercutting your prices", pricing_loss, "measured", evidence,
            "Did you know rivals dropped their prices? How much room do you have in your margin on these products?"))
        return pricing_loss

    if gap_rise is not None and gap_rise >= RIVAL_GAP_WIDENED_POINTS:              # case c
        causes.append(Cause(
            "pricing", "Rivals are undercutting your prices", 0.0, "inferred",
            [f"Price gap to the cheapest rival on top products went from {prev.price_gap_pct}% to {curr.price_gap_pct}%."],
            "Did you know rivals dropped their prices?"))
    return 0.0


def _leftover_cause(prev: Month, curr: Month, gap: float, leftover: float, cancelled_value: float,
                    extra_cancel_value: float, causes: list[Cause]) -> None:
    """Step 4. Name the part of the drop that stockouts and pricing do not explain.

    If cancellations jumped or the rating slipped, the leftover is put down to poor service
    hurting visibility. Otherwise it is honestly labelled as traffic we cannot explain."""
    cancel_rise = curr.cancel_rate - prev.cancel_rate
    rating_drop = (prev.rating - curr.rating) if (prev.rating and curr.rating) else 0.0
    service_is_worse = cancel_rise >= CANCELLATIONS_JUMPED_POINTS or rating_drop >= RATING_SLIPPED

    worth_naming = leftover >= LEFTOVER_WORTH_NAMING * gap
    costing_money = service_is_worse and extra_cancel_value > 0     # worth raising even with no leftover
    if not (worth_naming or costing_money):
        return

    evidence = []
    if curr.visits and prev.visits:
        evidence.append(f"Listing visits moved from {prev.visits:,} to {curr.visits:,} "
                        f"({_pct_change(prev.visits, curr.visits)}%).")

    if service_is_worse:
        evidence.insert(0, f"Cancellation rate rose from {prev.cancel_rate:g}% to {curr.cancel_rate:g}%.")
        if rating_drop >= 0.1:
            evidence.append(f"Seller rating slipped from {prev.rating} to {curr.rating}.")
        if curr.late_dispatch_rate is not None and prev.late_dispatch_rate is not None \
                and curr.late_dispatch_rate - prev.late_dispatch_rate >= 5:
            evidence.append(f"Late dispatch rose from {prev.late_dispatch_rate:g}% to {curr.late_dispatch_rate:g}%.")
        evidence.append(f"Cancelled orders are worth {inr(cancelled_value)} this month, "
                        f"{inr(extra_cancel_value)} more than at last month's rate.")
        causes.append(Cause(
            "service_quality", "Cancellations are hurting rating and visibility", leftover, "inferred", evidence,
            "Who is cancelling more: are you cancelling because stock or dispatch failed, or are buyers cancelling?"))
    else:
        evidence.append("Stock, price and cancellations do not explain this part of the drop.")
        causes.append(Cause(
            "traffic", "Fewer buyers are seeing your listings", leftover, "inferred", evidence,
            "Did anything change in your listings this month: titles, photos, categories or promotions you stopped?"))
