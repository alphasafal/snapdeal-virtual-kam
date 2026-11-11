"""Mock data. Seller S1 uses the exact table from the Snapdeal assignment brief.

Everything beyond that table (product names, per-product units, visits, rating,
cancellation reasons, sellers S2 and S3) is an assumption added so the agent can
recommend specific actions. Product rows are generated so they add up exactly to
the monthly totals.

Run:  python -m brain.seed
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from sqlalchemy import delete, insert

from . import db

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731

SELLERS = [
    dict(id="S1", name="Sharma Home Essentials", owner_name="Rajesh Sharma", city="Jaipur",
         category="Home & Kitchen", catalogue_size=60),
    dict(id="S2", name="Trendz Fashion Hub", owner_name="Meena Patel", city="Surat",
         category="Women's Ethnic Wear", catalogue_size=40),
    dict(id="S3", name="Gadget Galaxy", owner_name="Imran Khan", city="Delhi",
         category="Mobile Accessories", catalogue_size=30),
]

METRICS = {
    # S1: the brief's table. visits / rating / late dispatch are added assumptions.
    "S1": dict(
        prev=dict(sales=200000, orders=400, cancel_rate=8, asp=500, oos_products=5,
                  visits=20000, rating=4.3, price_gap_pct=2, late_dispatch_rate=6),
        curr=dict(sales=135000, orders=270, cancel_rate=14, asp=500, oos_products=18,
                  visits=15800, rating=3.9, price_gap_pct=3, late_dispatch_rate=8)),
    # S2: stock and cancellations are fine; rivals undercut the best sellers.
    "S2": dict(
        prev=dict(sales=320000, orders=400, cancel_rate=7, asp=800, oos_products=4,
                  visits=26000, rating=4.2, price_gap_pct=2, late_dispatch_rate=5),
        curr=dict(sales=232000, orders=290, cancel_rate=8, asp=800, oos_products=5,
                  visits=25200, rating=4.2, price_gap_pct=14, late_dispatch_rate=5)),
    # S3: stock and price are fine; late dispatch drives cancellations and rating down.
    "S3": dict(
        prev=dict(sales=450000, orders=300, cancel_rate=6, asp=1500, oos_products=3,
                  visits=30000, rating=4.3, price_gap_pct=1, late_dispatch_rate=5),
        curr=dict(sales=315000, orders=210, cancel_rate=19, asp=1500, oos_products=4,
                  visits=22500, rating=3.6, price_gap_pct=2, late_dispatch_rate=27)),
}

CANCEL_REASONS = {
    "S1": dict(prev=[("seller", "Out of stock after order", 6), ("seller", "Late dispatch", 4),
                     ("buyer", "Changed mind", 14), ("buyer", "Found cheaper elsewhere", 8)],
               curr=[("seller", "Out of stock after order", 19), ("seller", "Late dispatch", 5),
                     ("buyer", "Changed mind", 9), ("buyer", "Found cheaper elsewhere", 5)]),
    "S2": dict(prev=[("seller", "Out of stock after order", 4), ("seller", "Late dispatch", 3),
                     ("buyer", "Changed mind", 13), ("buyer", "Found cheaper elsewhere", 8)],
               curr=[("seller", "Out of stock after order", 3), ("seller", "Late dispatch", 2),
                     ("buyer", "Changed mind", 7), ("buyer", "Found cheaper elsewhere", 11)]),
    "S3": dict(prev=[("seller", "Out of stock after order", 3), ("seller", "Late dispatch", 3),
                     ("buyer", "Changed mind", 8), ("buyer", "Found cheaper elsewhere", 4)],
               curr=[("seller", "Late dispatch", 24), ("seller", "Out of stock after order", 4),
                     ("buyer", "Delivery too slow", 8), ("buyer", "Changed mind", 4)]),
}

NAMES = {
    "S1": ["Steel Tiffin Box 3-Tier", "Non-Stick Tawa 28cm", "Pressure Cooker 5L", "Cotton Bedsheet Double",
           "Kitchen Storage Jar Set", "Copper Water Bottle 1L", "Insulated Casserole Set", "Mixer Grinder Jar",
           "Plastic Drawer Organiser", "Door Mat Set of 2", "Steel Kadai 2L", "Wall Clock Wooden",
           "Curtain Set 7ft", "Glass Tumbler Set of 6", "Chopping Board Bamboo", "Lunch Bag Insulated",
           "Spice Rack 16 Jar", "Mop with Bucket", "Gas Lighter Pack of 3", "Water Jug 2L",
           "Cushion Cover Set of 5", "Dish Drying Rack", "Roti Box Steel", "Table Runner Cotton",
           "Laundry Basket Foldable", "Knife Set 5 Piece", "Idli Maker 4 Plate", "Bathroom Shelf Corner",
           "Ceramic Mug Set of 4", "Shoe Rack 4 Tier", "Thermos Flask 500ml", "Bed Blanket Single",
           "Fridge Organiser Bins", "Oil Dispenser 1L", "Towel Set of 4", "Fruit Basket Steel",
           "Pooja Thali Brass", "Hanger Pack of 12", "Vegetable Chopper", "Wall Shelf Floating",
           "Bottle Set of 6", "Apron Cotton", "Rolling Pin Board Set", "Pillow Cover Pair",
           "Dustbin Pedal 10L", "Tea Coffee Sugar Set", "Kitchen Towel Pack of 6", "Soap Dispenser",
           "Cutlery Set 24 Piece", "Tray Set of 3", "Ironing Board Cover", "Sink Strainer Steel",
           "Coaster Set of 6", "Bread Box Steel", "Measuring Cup Set", "Napkin Holder",
           "Storage Trunk Small", "Jar Opener", "Clothes Clip Pack", "Old Stock Hand Blender"],
    "S2": ["Cotton Anarkali Kurti", "Printed Straight Kurta", "Rayon Kurti Palazzo Set", "Bandhani Dupatta",
           "Embroidered Kurta Set", "Chikankari Kurti", "Silk Blend Saree", "Georgette Saree Printed",
           "Leggings Pack of 3", "Cotton Palazzo Pants", "Festive Lehenga Choli", "Block Print Kurti",
           "Party Wear Gown", "Banarasi Dupatta", "Kurti with Jacket", "Linen Kurta Plain",
           "Patiala Salwar", "Sharara Set", "Net Dupatta", "Kaftan Kurti", "Denim Kurti", "Shrug Long",
           "Kota Doria Saree", "Cotton Nighty", "Ethnic Skirt", "Angrakha Kurti", "Peplum Top Ethnic",
           "Dhoti Pants", "Cape Kurti", "Tunic Short", "Handloom Saree", "Kalamkari Kurti",
           "Velvet Kurta Set", "Churidar Pack of 2", "Stole Woollen", "Ikat Kurti", "Maxi Dress Ethnic",
           "Jacket Koti", "Petticoat Cotton", "Blouse Readymade"],
    "S3": ["Fast Charger 25W", "Type-C Cable 1.5m", "Wireless Earbuds", "Power Bank 10000mAh",
           "Tempered Glass Pack of 2", "Phone Back Cover", "Car Mobile Holder", "Bluetooth Speaker Mini",
           "Neckband Earphones", "Selfie Stick Tripod", "Wired Earphones", "OTG Adapter",
           "Laptop Stand Foldable", "Smart Watch Strap", "Ring Light 10 inch", "Memory Card 64GB",
           "USB Hub 4 Port", "Phone Stand Desk", "Car Charger Dual", "Aux Cable", "Mouse Wireless",
           "Keyboard Mini", "Webcam HD", "Cable Organiser", "Pop Socket Pack", "Camera Lens Protector",
           "Charging Dock", "Gaming Trigger", "Stylus Pen", "Screen Cleaner Kit"],
}


def _allocate(weights: list[float], total: int) -> list[int]:
    """Split `total` units across weights (largest remainder)."""
    s = sum(weights) or 1
    raw = [w / s * total for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[: total - sum(out)]:
        out[i] += 1
    return out


def _fix_revenue(units: list[int], prices: list[int], target: int, free: list[int]) -> None:
    """Move single units between `free` products until sum(units*price) == target."""
    def rev():
        """Total revenue for the current split of units."""
        return sum(u * p for u, p in zip(units, prices))
    for _ in range(5000):
        diff = target - rev()
        if diff == 0:
            return
        best = None
        for i in free:
            if units[i] <= 0:
                continue
            for j in free:
                d = prices[j] - prices[i]
                if d != 0 and abs(diff - d) < abs(diff) and (best is None or abs(diff - d) < best[0]):
                    best = (abs(diff - d), i, j)
        if best is None:
            break
        _, i, j = best
        units[i] -= 1
        units[j] += 1
    raise RuntimeError(f"could not hit revenue target {target}, got {rev()}")


def build_products(seller_id: str) -> list[dict]:
    """Invent a product catalogue for one mock seller that adds up exactly to its monthly totals.

    The same catalogue is produced every time (the random generator is seeded with the
    seller id), so tests and demos always see the same numbers. Each seller gets a different
    story built in:
      S1  the best sellers ran out of stock part-way through the month
      S2  rivals undercut the top eight products
      S3  every product sold a bit less (late dispatch hurt the whole shop)
    """
    rnd = random.Random(f"snapdeal-{seller_id}")
    names = NAMES[seller_id]
    m = METRICS[seller_id]
    n = len(names)
    prev_orders, curr_orders = m["prev"]["orders"], m["curr"]["orders"]
    asp = int(m["prev"]["asp"])
    step = 50 if asp < 1000 else 100
    prices = [max(step * 2, asp + step * rnd.randint(-4, 4)) for _ in range(n)]

    old_oos = set(range(n - m["prev"]["oos_products"], n))          # dead both months
    new_oos_n = m["curr"]["oos_products"] - m["prev"]["oos_products"]
    # S1: the best sellers ran out. S2/S3: one mid-catalogue product ran out.
    new_oos = set(range(new_oos_n)) if seller_id == "S1" else set(range(n // 2, n // 2 + new_oos_n))
    live = [i for i in range(n) if i not in old_oos]

    # last month: best sellers first (weights fall off down the list)
    def boost(i: int) -> float:
        """Extra weight for the products that matter in this seller's story, so they were the
        big sellers last month."""
        if seller_id == "S1" and i in new_oos:
            return 1.35
        if seller_id == "S2" and i < 8:
            return 2.2
        return 1.0
    w_prev = [0 if i in old_oos else boost(i) * (1.6 - i / n) for i in range(n)]
    units_prev = _allocate(w_prev, prev_orders)
    _fix_revenue(units_prev, prices, int(m["prev"]["sales"]), live)

    days_oos = [0] * n
    competitor = [None] * n
    factor = [0.0] * n
    for i in live:
        if seller_id == "S1":
            if i in new_oos:
                days_oos[i] = rnd.randint(14, 24)
                factor[i] = (30 - days_oos[i]) / 30 * 1.1
            else:
                factor[i] = 0.84          # milder dip from lower visibility
        elif seller_id == "S2":
            if i < 8:                     # top 8 are undercut by rivals
                competitor[i] = round(prices[i] * rnd.uniform(0.84, 0.88) / 10) * 10
                factor[i] = 0.45
            else:
                competitor[i] = round(prices[i] * rnd.uniform(0.98, 1.06) / 10) * 10
                factor[i] = 0.98
            if i in new_oos:
                days_oos[i] = 6
        else:                             # S3: even decline across the catalogue
            competitor[i] = round(prices[i] * rnd.uniform(0.98, 1.05) / 10) * 10
            factor[i] = 0.70
            if i in new_oos:
                days_oos[i] = 5

    units_curr = _allocate([units_prev[i] * factor[i] for i in range(n)], curr_orders)
    # never let a product sell more than last month in a declining month
    free = [i for i in live if i not in new_oos and (seller_id != "S2" or i >= 8)]
    _fix_revenue(units_curr, prices, int(m["curr"]["sales"]), free)

    rows = []
    for i, name in enumerate(names):
        oos_now = i in old_oos or i in new_oos
        rows.append(dict(
            id=f"{seller_id}-P{i + 1:02d}", seller_id=seller_id, name=name, price=float(prices[i]),
            units_prev=units_prev[i], units_curr=units_curr[i],
            in_stock=not oos_now, oos_prev=i in old_oos,
            days_oos_curr=30 if i in old_oos else days_oos[i],
            competitor_price=float(competitor[i]) if competitor[i] else None, status="active"))
    return rows


def seed(reset_calls: bool = True) -> None:
    """Create the tables and load the three mock sellers, replacing whatever was there.

    reset_calls=True also wipes call history, actions and reviews (a clean slate)."""
    db.create_schema()
    with db.engine().begin() as cx:
        tables = [db.products, db.cancel_reasons, db.monthly_metrics, db.diagnoses, db.sellers]
        if reset_calls:
            tables = [db.call_reviews, db.call_turns, db.actions, db.followups, db.calls] + tables
        for t in tables:
            cx.execute(delete(t))
        for s in SELLERS:
            cx.execute(insert(db.sellers).values(**s, is_custom=False, created_at=NOW()))
            for period in ("prev", "curr"):
                cx.execute(insert(db.monthly_metrics).values(seller_id=s["id"], period=period,
                                                             **METRICS[s["id"]][period]))
                for side, reason, count in CANCEL_REASONS[s["id"]][period]:
                    cx.execute(insert(db.cancel_reasons).values(
                        seller_id=s["id"], period=period, side=side, reason=reason, count=count))
            cx.execute(insert(db.products), build_products(s["id"]))
    from .jobs import scan_all
    scan_all()


def is_seeded() -> bool:
    """True if sellers are already loaded. start.sh uses this to keep call history across restarts."""
    from sqlalchemy import func, select
    db.create_schema()
    with db.engine().connect() as cx:
        return bool(cx.execute(select(func.count()).select_from(db.sellers)).scalar())


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    where = db.database_url().split("@")[-1]
    if "--if-empty" in sys.argv and is_seeded():
        print("Sellers already present in", where, "- keeping existing data (use --reset to wipe).")
    else:
        seed()
        print("Seeded 3 sellers into", where)
