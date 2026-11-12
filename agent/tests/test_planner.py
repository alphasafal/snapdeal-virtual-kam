"""The what-if planner and the wider seller portfolio."""
import pytest

from brain import repo, seed
from brain.jobs import scan_all
from brain.planner import plan_options
from brain.tools import KamTools


def plan(seller_id: str) -> dict:
    return plan_options(seller_id, repo.run_diagnosis(seller_id, save=False))


def test_every_seller_has_products_that_add_up_to_the_monthly_totals(fresh_db):
    assert len(seed.SELLERS) == 12
    for seller in seed.SELLERS:
        products = seed.build_products(seller["id"])
        months = seed.METRICS[seller["id"]]
        assert len(products) == seller["catalogue_size"]
        assert sum(p["units_prev"] * p["price"] for p in products) == months["prev"]["sales"]
        assert sum(p["units_curr"] * p["price"] for p in products) == months["curr"]["sales"]
        assert sum(p["units_prev"] for p in products) == months["prev"]["orders"]
        assert sum(p["units_curr"] for p in products) == months["curr"]["orders"]


@pytest.mark.parametrize("seller_id,cause", [
    ("S1", "stockouts"), ("S2", "pricing"), ("S3", "service_quality"), ("S4", "stockouts"),
    ("S5", "pricing"), ("S6", "service_quality"), ("S7", "stockouts"), ("S8", "pricing"),
    ("S9", "service_quality"), ("S11", "stockouts"), ("S12", "pricing"),
])
def test_each_story_gets_the_right_main_cause(fresh_db, seller_id, cause):
    assert repo.run_diagnosis(seller_id, save=False)["primary_cause"] == cause


def test_a_growing_seller_has_no_problem_and_no_plan(fresh_db):
    diagnosis = repo.run_diagnosis("S10", save=False)
    assert diagnosis["gap_inr"] == 0 and diagnosis["causes"] == []
    assert plan("S10") == {"options": [], "recoverable_inr": 0.0, "gap_inr": 0.0}


def test_planner_for_the_brief_seller(fresh_db):
    result = plan("S1")
    by_key = {option["key"]: option for option in result["options"]}
    # Restocking everything that ran out wins back exactly what the diagnosis blames on stockouts.
    assert by_key["restock_top"]["recover_inr"] + by_key["restock_rest"]["recover_inr"] == 45450
    assert by_key["stock_buffer"]["recover_inr"] == 13 * 500          # 19 - 6 cancelled orders at Rs 500
    assert by_key["visibility_review"]["recover_inr"] is None         # no rupee figure is invented
    assert "price_top" not in by_key                                  # pricing is not this seller's problem
    assert result["recoverable_inr"] <= result["gap_inr"] == 65000
    amounts = [option["recover_inr"] or 0 for option in result["options"]]
    assert amounts == sorted(amounts, reverse=True)                   # biggest first


def test_planner_agrees_with_what_asha_says_on_the_call(fresh_db):
    """The planner page and the voice agent must quote the same rupees for the same action."""
    tools = KamTools("S1", repo.create_call("S1"))
    spoken = tools.create_restock_plan(5)["proposal"]                 # "... they lost Rs X this month."
    restock = next(o for o in plan("S1")["options"] if o["key"] == "restock_top")
    assert f"{int(restock['recover_inr']):,}".replace(",", "") in spoken.replace(",", "")

    tools = KamTools("S2", repo.create_call("S2"))
    spoken = tools.match_rival_prices(5)["proposal"]
    price = next(o for o in plan("S2")["options"] if o["key"] == "price_top")
    assert f"{int(price['recover_inr'])}" in spoken.replace(",", "")


def test_restock_cost_uses_the_quantities_asha_orders(fresh_db):
    """The planner's stock to buy is the same units, product by product, as the restock plan
    Asha saves on a call, and the sales it wins back add up to the option's own figure."""
    restock = next(o for o in plan("S1")["options"] if o["key"] == "restock_top")
    call_id = repo.create_call("S1")
    KamTools("S1", call_id).create_restock_plan(5, seller_confirmed=True)
    saved = repo.get_actions(call_id=call_id)[0]["detail"]["products"]
    assert [(i["name"], i["units"]) for i in restock["items"]] == [(p["name"], p["quantity"]) for p in saved]
    assert sum(i["recover_inr"] for i in restock["items"]) == restock["recover_inr"]
    prices = {p.name: p.price for p in repo.get_products("S1")}
    assert all(i["stock_value_inr"] == i["units"] * prices[i["name"]] for i in restock["items"])
    assert restock["cost_share"] == 0.6                               # an assumption, shown as one on the page


def test_price_match_margin_uses_the_prices_asha_sets(fresh_db):
    """The margin the planner says a price match gives up is the cut Asha would save,
    on last month's volume."""
    price = next(o for o in plan("S2")["options"] if o["key"] == "price_top")
    call_id = repo.create_call("S2")
    KamTools("S2", call_id).match_rival_prices(5, 15, seller_confirmed=True)
    saved = repo.get_actions(call_id=call_id)[0]["detail"]["products"]
    sold_last_month = {p.id: p.units_prev for p in repo.get_products("S2")}
    assert price["margin_inr"] == sum((p["old_price"] - p["new_price"]) * sold_last_month[p["id"]] for p in saved)
    assert 0 < price["margin_inr"] < price["recover_inr"]            # cheaper than the sales it wins back


def test_only_restocks_and_price_matches_carry_a_cost(fresh_db):
    for seller in seed.SELLERS:
        for option in plan(seller["id"])["options"]:
            assert ("items" in option) == option["key"].startswith("restock_")
            assert ("margin_inr" in option) == option["key"].startswith("price_")


def test_planner_never_promises_more_than_was_lost(fresh_db):
    for seller in seed.SELLERS:
        result = plan(seller["id"])
        assert 0 <= result["recoverable_inr"] <= result["gap_inr"]


def test_nightly_scan_stores_a_plan_for_every_seller(fresh_db):
    from sqlalchemy import select
    from brain import db
    rows = scan_all()
    assert len(rows) == 12
    with db.engine().connect() as cx:
        stored = {r["seller_id"]: r for r in cx.execute(select(db.plans)).mappings()}
    assert set(stored) == {s["id"] for s in seed.SELLERS}
    assert stored["S1"]["recoverable_inr"] > 40000
    assert stored["S10"]["options"] == []
    restock = next(o for o in stored["S1"]["options"] if o["key"] == "restock_top")
    assert len(restock["items"]) == 5 and restock["items"][0]["units"] > 0   # the page costs the plan from these
