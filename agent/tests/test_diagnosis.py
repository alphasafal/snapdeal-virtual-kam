"""Ten seller scenarios for the diagnosis engine. Each asserts the main cause it should find."""
import pytest
from brain.diagnosis import Month, Product, diagnose, inr

BRIEF_PREV = Month(sales=200000, orders=400, cancel_rate=8, asp=500, oos_products=5)
BRIEF_CURR = Month(sales=135000, orders=270, cancel_rate=14, asp=500, oos_products=18)


def keys(d):
    return [c["key"] for c in d["causes"]]


def test_01_brief_table_headline_numbers():
    d = diagnose(BRIEF_PREV, BRIEF_CURR, catalogue_size=60)
    assert d["gap_inr"] == 65000 and d["orders_gap"] == 130
    assert d["snapshot"]["sales_change_pct"] == -32.5 == d["snapshot"]["orders_change_pct"]
    assert d["price_effect_inr"] == 0 and d["volume_effect_inr"] == -65000
    assert "volume problem" in d["headline"] and d["risk_level"] == "high"


def test_02_brief_table_aggregate_only_blames_stockouts_first():
    d = diagnose(BRIEF_PREV, BRIEF_CURR, catalogue_size=60)
    assert d["primary_cause"] == "stockouts"
    stock = d["causes"][0]
    assert stock["confidence"] == "estimated"
    assert stock["impact_inr"] == round(13 * 200000 / 55)      # 13 new stockouts x average product
    assert sum(c["impact_inr"] for c in d["causes"]) == 65000  # causes add up to the whole drop


def test_03_brief_table_cancellation_leak():
    c = diagnose(BRIEF_PREV, BRIEF_CURR)["cancellations"]
    assert c["cancelled_orders_curr"] == 38
    assert c["cancelled_value_inr"] == 18900       # 270 x 14% x 500
    assert c["extra_vs_last_month_inr"] == 8100    # 270 x 6 points x 500


def test_04_missing_catalogue_size_is_declared_as_assumption():
    d = diagnose(BRIEF_PREV, BRIEF_CURR)
    assert any("assumed 60" in a for a in d["assumptions"])


def test_05_own_price_cut_is_a_pricing_cause():
    d = diagnose(Month(100000, 200, 5, 500, 2), Month(80000, 200, 5, 400, 2))
    assert d["primary_cause"] == "pricing" and d["causes"][0]["impact_inr"] == 20000


def test_06_rival_undercut_measured_from_products():
    products = [Product("a", "Kurti", 1000, 50, 20, True, competitor_price=850),
                Product("b", "Saree", 1000, 50, 50, True, competitor_price=1000)]
    d = diagnose(Month(100000, 100, 5, 1000, 0, price_gap_pct=1),
                 Month(70000, 70, 5, 1000, 0, price_gap_pct=12), products)
    assert d["primary_cause"] == "pricing" and d["causes"][0]["impact_inr"] == 30000


def test_07_service_quality_when_cancellations_and_rating_slide():
    d = diagnose(Month(450000, 300, 6, 1500, 3, rating=4.3, late_dispatch_rate=5),
                 Month(315000, 210, 19, 1500, 3, rating=3.6, late_dispatch_rate=27))
    assert d["primary_cause"] == "service_quality"
    assert any("Late dispatch" in e for e in d["causes"][0]["evidence"])


def test_08_unexplained_drop_is_labelled_traffic_not_invented():
    d = diagnose(Month(100000, 200, 5, 500, 2), Month(80000, 160, 5, 500, 2))
    assert keys(d) == ["traffic"] and d["causes"][0]["confidence"] == "inferred"


def test_09_growing_seller_is_not_diagnosed_as_declining():
    d = diagnose(Month(100000, 200, 5, 500, 2), Month(120000, 240, 9, 500, 6))
    assert d["status"] == "not_declining" and d["causes"] == [] and len(d["watch"]) == 2


def test_10_stockout_loss_never_exceeds_the_drop():
    products = [Product("a", "Tawa", 500, 100, 0, False, days_oos_curr=30)]
    d = diagnose(Month(100000, 200, 5, 500, 0), Month(90000, 180, 5, 500, 1), products)
    assert d["causes"][0]["impact_inr"] == 10000


@pytest.mark.parametrize("n,text", [(135000, "₹1,35,000"), (200000, "₹2,00,000"), (500, "₹500"),
                                    (12345678, "₹1,23,45,678"), (8100, "₹8,100")])
def test_indian_number_format(n, text):
    assert inr(n) == text


def test_price_cut_with_rising_orders_never_explains_more_than_the_drop():
    d = diagnose(Month(100000, 200, 5, 500, 2), Month(90000, 300, 5, 300, 2))
    assert d["primary_cause"] == "pricing" and d["causes"][0]["impact_inr"] == 10000
    assert d["causes"][0]["share_pct"] == 100
