"""Mock data. Seller S1 uses the exact table from the Snapdeal assignment brief.

Everything beyond that table (product names, per-product units, visits, rating,
cancellation reasons, and every other seller) is an assumption added so the agent can
recommend specific actions. Product rows are generated so they add up exactly to
the monthly totals.

There are twelve sellers. S1 to S3 are the detailed ones used for calls in the demo.
S4 to S12 fill out the portfolio so the team dashboard works as a ranked call queue;
each follows one of four stories (see STORY) and can be called in the same way.

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
    # The rest of the portfolio.
    dict(id="S4", name="Verma Footwear", owner_name="Anil Verma", city="Kanpur",
         category="Footwear", catalogue_size=24),
    dict(id="S5", name="Lakshmi Silks", owner_name="Lakshmi Iyer", city="Coimbatore",
         category="Sarees", catalogue_size=24),
    dict(id="S6", name="Kapoor Toy World", owner_name="Simran Kapoor", city="Ludhiana",
         category="Toys & Games", catalogue_size=24),
    dict(id="S7", name="Deccan Home Appliances", owner_name="Farhan Qureshi", city="Hyderabad",
         category="Small Appliances", catalogue_size=24),
    dict(id="S8", name="Bengal Handloom House", owner_name="Ananya Banerjee", city="Kolkata",
         category="Home Furnishing", catalogue_size=24),
    dict(id="S9", name="Malabar Spice Box", owner_name="Biju Nair", city="Kochi",
         category="Grocery & Gourmet", catalogue_size=24),
    dict(id="S10", name="Joshi Sports Corner", owner_name="Neha Joshi", city="Pune",
         category="Sports & Fitness", catalogue_size=24),
    dict(id="S11", name="Singh Auto Accessories", owner_name="Harpreet Singh", city="Chandigarh",
         category="Car Accessories", catalogue_size=24),
    dict(id="S12", name="Mehta Beauty Store", owner_name="Pooja Mehta", city="Ahmedabad",
         category="Beauty & Personal Care", catalogue_size=24),
]

# What happened to each seller. build_products() shapes the product data to match.
#   stockout  the best sellers ran out of stock part-way through the month
#   pricing   rivals undercut the top products
#   dispatch  orders went out late, so every product sold a bit less
#   growing   sales went up: nothing is wrong, and Asha must not invent a problem
STORY = {"S1": "stockout", "S2": "pricing", "S3": "dispatch", "S4": "stockout", "S5": "pricing",
         "S6": "dispatch", "S7": "stockout", "S8": "pricing", "S9": "dispatch", "S10": "growing",
         "S11": "stockout", "S12": "pricing"}

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
    # S4 to S12: the wider portfolio. In every row, sales = orders x average price.
    "S4": dict(
        prev=dict(sales=360000, orders=600, cancel_rate=7, asp=600, oos_products=3,
                  visits=31000, rating=4.2, price_gap_pct=2, late_dispatch_rate=5),
        curr=dict(sales=252000, orders=420, cancel_rate=12, asp=600, oos_products=11,
                  visits=25500, rating=3.9, price_gap_pct=2, late_dispatch_rate=6)),
    "S5": dict(
        prev=dict(sales=540000, orders=450, cancel_rate=6, asp=1200, oos_products=2,
                  visits=28000, rating=4.4, price_gap_pct=3, late_dispatch_rate=4),
        curr=dict(sales=396000, orders=330, cancel_rate=7, asp=1200, oos_products=3,
                  visits=27300, rating=4.4, price_gap_pct=16, late_dispatch_rate=4)),
    "S6": dict(
        prev=dict(sales=210000, orders=350, cancel_rate=6, asp=600, oos_products=2,
                  visits=19000, rating=4.3, price_gap_pct=1, late_dispatch_rate=6),
        curr=dict(sales=153000, orders=255, cancel_rate=17, asp=600, oos_products=3,
                  visits=14800, rating=3.7, price_gap_pct=2, late_dispatch_rate=24)),
    "S7": dict(
        prev=dict(sales=480000, orders=320, cancel_rate=6, asp=1500, oos_products=2,
                  visits=24000, rating=4.3, price_gap_pct=2, late_dispatch_rate=5),
        curr=dict(sales=372000, orders=248, cancel_rate=9, asp=1500, oos_products=9,
                  visits=21000, rating=4.1, price_gap_pct=2, late_dispatch_rate=5)),
    "S8": dict(
        prev=dict(sales=264000, orders=330, cancel_rate=7, asp=800, oos_products=3,
                  visits=21000, rating=4.2, price_gap_pct=2, late_dispatch_rate=5),
        curr=dict(sales=211200, orders=264, cancel_rate=8, asp=800, oos_products=3,
                  visits=20600, rating=4.2, price_gap_pct=11, late_dispatch_rate=5)),
    "S9": dict(
        prev=dict(sales=150000, orders=500, cancel_rate=5, asp=300, oos_products=2,
                  visits=26000, rating=4.4, price_gap_pct=1, late_dispatch_rate=4),
        curr=dict(sales=117000, orders=390, cancel_rate=13, asp=300, oos_products=3,
                  visits=22100, rating=3.9, price_gap_pct=1, late_dispatch_rate=19)),
    "S10": dict(
        prev=dict(sales=240000, orders=300, cancel_rate=6, asp=800, oos_products=2,
                  visits=20000, rating=4.3, price_gap_pct=2, late_dispatch_rate=5),
        curr=dict(sales=276000, orders=345, cancel_rate=5, asp=800, oos_products=2,
                  visits=23000, rating=4.4, price_gap_pct=2, late_dispatch_rate=4)),
    "S11": dict(
        prev=dict(sales=300000, orders=300, cancel_rate=6, asp=1000, oos_products=3,
                  visits=18000, rating=4.2, price_gap_pct=2, late_dispatch_rate=5),
        curr=dict(sales=264000, orders=264, cancel_rate=8, asp=1000, oos_products=7,
                  visits=17100, rating=4.1, price_gap_pct=2, late_dispatch_rate=5)),
    "S12": dict(
        prev=dict(sales=180000, orders=450, cancel_rate=6, asp=400, oos_products=2,
                  visits=23000, rating=4.3, price_gap_pct=2, late_dispatch_rate=4),
        curr=dict(sales=162000, orders=405, cancel_rate=6, asp=400, oos_products=2,
                  visits=22800, rating=4.3, price_gap_pct=9, late_dispatch_rate=4)),
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

# S4 to S12 get 24 products each: eight items in three variants.
_ITEMS = {
    "S4": (["Running Shoes", "Leather Sandals", "Canvas Sneakers", "Formal Shoes", "Sports Slides",
            "Kolhapuri Chappal", "Ankle Boots", "Loafers"], ["Black", "Brown", "Blue"]),
    "S5": (["Kanjivaram Silk Saree", "Soft Silk Saree", "Cotton Silk Saree", "Mysore Silk Saree",
            "Banarasi Silk Saree", "Linen Saree", "Tussar Saree", "Chiffon Saree"], ["Maroon", "Green", "Blue"]),
    "S6": (["Building Blocks Set", "Remote Control Car", "Soft Toy Teddy", "Board Game Ludo",
            "Puzzle 500 Piece", "Doll House Kit", "Cricket Set Kids", "Art and Craft Kit"],
           ["Small", "Medium", "Large"]),
    "S7": (["Electric Kettle", "Sandwich Maker", "Hand Blender", "Induction Cooktop", "Steam Iron",
            "Room Heater", "Rice Cooker", "Air Fryer"], ["Basic", "Plus", "Pro"]),
    "S8": (["Handloom Bedcover", "Cotton Dohar", "Jute Table Mat Set", "Kantha Cushion Cover",
            "Block Print Curtain", "Cotton Rug", "Handwoven Throw", "Khadi Table Cloth"],
           ["Indigo", "Rust", "Ivory"]),
    "S9": (["Kerala Black Pepper", "Green Cardamom", "Cinnamon Sticks", "Turmeric Powder",
            "Cloves Whole", "Garam Masala", "Coconut Oil Cold Pressed", "Banana Chips"],
           ["100g", "250g", "500g"]),
    "S10": (["Yoga Mat", "Skipping Rope", "Dumbbell Pair", "Badminton Racket", "Cricket Bat Tennis",
             "Football Size 5", "Resistance Band Set", "Gym Gloves"], ["Standard", "Pro", "Kids"]),
    "S11": (["Car Seat Cover", "Dashboard Camera", "Car Vacuum Cleaner", "Steering Cover",
             "Car Body Cover", "Tyre Inflator", "Car Perfume", "Floor Mat Set"],
            ["Hatchback", "Sedan", "SUV"]),
    "S12": (["Face Wash Neem", "Hair Oil Onion", "Sunscreen SPF 50", "Lip Balm Tinted", "Kajal Pencil",
             "Body Lotion Almond", "Shampoo Herbal", "Face Serum Vitamin C"], ["Small", "Regular", "Value Pack"]),
}
for _sid, (_bases, _variants) in _ITEMS.items():
    # Item by item within a variant, so the first eight products are eight different items.
    NAMES[_sid] = [f"{base} {variant}" for variant in _variants for base in _bases]


def _allocate_reasons(story: str, period: str, total: int) -> list[tuple[str, str, int]]:
    """Split a seller's cancelled orders across reasons in a way that fits their story."""
    usual = [("seller", "Out of stock after order", 0.19), ("seller", "Late dispatch", 0.12),
             ("buyer", "Changed mind", 0.44), ("buyer", "Found cheaper elsewhere", 0.25)]
    this_month = {
        "stockout": [("seller", "Out of stock after order", 0.50), ("seller", "Late dispatch", 0.13),
                     ("buyer", "Changed mind", 0.24), ("buyer", "Found cheaper elsewhere", 0.13)],
        "pricing": [("seller", "Out of stock after order", 0.13), ("seller", "Late dispatch", 0.09),
                    ("buyer", "Changed mind", 0.30), ("buyer", "Found cheaper elsewhere", 0.48)],
        "dispatch": [("seller", "Late dispatch", 0.60), ("seller", "Out of stock after order", 0.10),
                     ("buyer", "Delivery too slow", 0.20), ("buyer", "Changed mind", 0.10)],
        "growing": usual,
    }
    shares = usual if period == "prev" else this_month[story]
    counts = _allocate([share for _, _, share in shares], total)
    return [(side, reason, count) for (side, reason, _), count in zip(shares, counts)]


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


def cancel_reasons(seller_id: str, period: str) -> list[tuple[str, str, int]]:
    """Why orders were cancelled, as (side, reason, count). S1 to S3 are written out by hand
    above; the rest are generated so the counts add up to orders x cancellation rate."""
    if seller_id in CANCEL_REASONS:
        return CANCEL_REASONS[seller_id][period]
    month = METRICS[seller_id][period]
    return _allocate_reasons(STORY[seller_id], period, round(month["orders"] * month["cancel_rate"] / 100))


def build_products(seller_id: str) -> list[dict]:
    """Invent a product catalogue for one mock seller that adds up exactly to its monthly totals.

    The same catalogue is produced every time (the random generator is seeded with the
    seller id), so tests and demos always see the same numbers. The seller's story (see
    STORY) decides the shape:
      stockout  the best sellers ran out of stock part-way through the month
      pricing   rivals undercut the top eight products
      dispatch  every product sold a bit less (late dispatch hurt the whole shop)
      growing   every product sold a bit more
    """
    story = STORY[seller_id]
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
    # Stockout story: the best sellers ran out. Otherwise: a mid-catalogue product ran out.
    new_oos = set(range(new_oos_n)) if story == "stockout" else set(range(n // 2, n // 2 + new_oos_n))
    live = [i for i in range(n) if i not in old_oos]

    # last month: best sellers first (weights fall off down the list)
    def boost(i: int) -> float:
        """Extra weight for the products that matter in this seller's story, so they were the
        big sellers last month."""
        if story == "stockout" and i in new_oos:
            return 1.35
        if story == "pricing" and i < 8:
            return 2.2
        return 1.0
    w_prev = [0 if i in old_oos else boost(i) * (1.6 - i / n) for i in range(n)]
    units_prev = _allocate(w_prev, prev_orders)
    _fix_revenue(units_prev, prices, int(m["prev"]["sales"]), live)

    days_oos = [0] * n
    competitor = [None] * n
    factor = [0.0] * n
    for i in live:
        if story == "stockout":
            if i in new_oos:
                days_oos[i] = rnd.randint(14, 24)
                factor[i] = (30 - days_oos[i]) / 30 * 1.1
            else:
                factor[i] = 0.84          # milder dip from lower visibility
        elif story == "pricing":
            if i < 8:                     # top 8 are undercut by rivals
                competitor[i] = round(prices[i] * rnd.uniform(0.84, 0.88) / 10) * 10
                factor[i] = 0.45
            else:
                competitor[i] = round(prices[i] * rnd.uniform(0.98, 1.06) / 10) * 10
                factor[i] = 0.98
            if i in new_oos:
                days_oos[i] = 6
        else:                             # dispatch or growing: an even change across the catalogue
            competitor[i] = round(prices[i] * rnd.uniform(0.98, 1.05) / 10) * 10
            factor[i] = 1.15 if story == "growing" else 0.70
            if i in new_oos:
                days_oos[i] = 5

    units_curr = _allocate([units_prev[i] * factor[i] for i in range(n)], curr_orders)
    # never let a product sell more than last month in a declining month
    free = [i for i in live if i not in new_oos and (story != "pricing" or i >= 8)]
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
    """Create the tables and load the mock sellers, replacing whatever was there.

    reset_calls=True also wipes call history, actions and reviews (a clean slate)."""
    db.create_schema()
    with db.engine().begin() as cx:
        tables = [db.products, db.cancel_reasons, db.monthly_metrics, db.diagnoses, db.plans, db.sellers]
        if reset_calls:
            tables = [db.call_reviews, db.call_turns, db.actions, db.followups, db.calls] + tables
        for t in tables:
            cx.execute(delete(t))
        for s in SELLERS:
            cx.execute(insert(db.sellers).values(**s, is_custom=False, created_at=NOW()))
            for period in ("prev", "curr"):
                cx.execute(insert(db.monthly_metrics).values(seller_id=s["id"], period=period,
                                                             **METRICS[s["id"]][period]))
                for side, reason, count in cancel_reasons(s["id"], period):
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
        print(f"Seeded {len(SELLERS)} sellers into", where)
