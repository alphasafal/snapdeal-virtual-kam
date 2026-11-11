"""A whole call, without audio: look-ups, confirmed actions, summary, then memory on the next call."""
from datetime import datetime, timezone

from brain import repo
from brain.diagnosis import newly_out_of_stock
from brain.tools import KamTools, spoken


def test_seed_matches_brief_exactly(fresh_db):
    ps = repo.get_products("S1")
    assert sum(p.units_prev for p in ps) == 400 and sum(p.units_prev * p.price for p in ps) == 200000
    assert sum(p.units_curr for p in ps) == 270 and sum(p.units_curr * p.price for p in ps) == 135000
    assert sum(1 for p in ps if not p.in_stock) == 18 and sum(1 for p in ps if p.oos_prev) == 5
    for sid in ("S2", "S3"):
        prev, curr = repo.get_months(sid)
        ps = repo.get_products(sid)
        assert sum(p.units_curr * p.price for p in ps) == curr.sales
        assert sum(p.units_prev * p.price for p in ps) == prev.sales


def test_three_sellers_three_different_causes(fresh_db):
    causes = {s: repo.run_diagnosis(s, save=False)["primary_cause"] for s in ("S1", "S2", "S3")}
    assert causes == {"S1": "stockouts", "S2": "pricing", "S3": "service_quality"}


def test_full_call_flow_and_memory(fresh_db):
    call = repo.create_call("S1")
    t = KamTools("S1", call)
    brief = t.account_brief()
    assert "₹2,00,000" in brief and "₹1,35,000" in brief and "Cause 1: Products ran out of stock" in brief
    assert t.memory_brief() is None

    assert t.stockout_products(3)["count"] == 13
    cb = t.cancellation_breakdown()
    assert cb["this_month"] == {"seller_side": 24, "buyer_side": 14}

    # nothing is saved until the seller says yes
    assert t.create_restock_plan(6)["status"] == "needs_confirmation"
    assert repo.get_actions(call_id=call) == []

    t.record_seller_input("stockout_reason", "supplier delay of two weeks")
    done = t.create_restock_plan(6, seller_confirmed=True)
    assert done["status"] == "done" and len(done["products"]) == 6
    assert t.create_restock_plan(6, seller_confirmed=True)["status"] == "already_done"   # no duplicates
    assert t.pause_unavailable_listings(seller_confirmed=True)["paused"] == 12            # 18 out - 6 restocking
    assert t.set_stock_buffer(2, seller_confirmed=True)["status"] == "done"
    assert t.schedule_followup(7)["status"] == "done"

    s = t.wrap_up()["summary"]
    top6 = sum(p.lost_sales for p in newly_out_of_stock(repo.get_products("S1"))[:6])
    assert s["expected_recovery_inr"] == top6 + 13 * 500      # restock + 13 extra stock-out cancellations
    assert len(s["actions"]) == 3 and s["followup_date"]
    repo.update_call(call, status="ended", ended_at=datetime.now(timezone.utc))

    # next call remembers
    call2 = repo.create_call("S1")
    memory = KamTools("S1", call2).memory_brief()
    assert "Restock 6 top products" in memory and "supplier delay" in memory


def test_pricing_seller_actions(fresh_db):
    call = repo.create_call("S2")
    t = KamTools("S2", call)
    assert t.create_restock_plan(3, True)["status"] in ("done", "not_applicable")
    gaps = t.pricing_gaps()
    assert gaps["count"] >= 5
    assert t.match_rival_prices(5)["status"] == "needs_confirmation"
    assert t.match_rival_prices(5, 15, True)["status"] == "done"
    act = [a for a in repo.get_actions(call_id=call) if a["type"] == "price_match"][0]
    assert all(p["new_price"] < p["old_price"] and p["new_price"] >= p["old_price"] * 0.85
               for p in act["detail"]["products"])


def test_service_seller_actions_and_escalation(fresh_db):
    call = repo.create_call("S3")
    t = KamTools("S3", call)
    out = t.enable_dispatch_alerts(True)
    assert out["status"] == "done" and "31,500" in out["expected_recovery_per_month"]   # 21 extra x 1500
    t.escalate_to_human("technical_problem", "Courier partner not picking up")
    assert repo.get_call(call)["escalated"] is True
    assert t.raise_ticket("visibility review", "Re-check rating after dispatch fix")["status"] == "done"


def test_spoken_amounts():
    assert spoken(45450) == "about 45 thousand rupees"
    assert spoken(135000) == "about 1.35 lakh rupees"
    assert spoken(8100) == "about 8,100 rupees"
    assert spoken(200000) == "about 2 lakh rupees"


def _end(call_id):
    repo.update_call(call_id, status="ended", ended_at=datetime.now(timezone.utc))


def test_seller_can_change_the_restock_plan_without_duplicates(fresh_db):
    call = repo.create_call("S1")
    t = KamTools("S1", call)
    assert t.create_restock_plan(4, True)["status"] == "done"
    assert t.create_restock_plan(6, True)["status"] == "updated"
    acts = repo.get_actions(call_id=call)
    assert len(acts) == 1 and len(acts[0]["detail"]["products"]) == 6 and acts[0]["title"] == "Restock 6 top products"


def test_restocking_after_pausing_reactivates_those_listings(fresh_db):
    call = repo.create_call("S1")
    t = KamTools("S1", call)
    first = t.pause_unavailable_listings(seller_confirmed=True)
    assert first["paused"] == 5 and "restock plan" in first["note"]    # no plan yet: only long-dead listings
    done = t.create_restock_plan(5, True)
    assert t.pause_unavailable_listings(seller_confirmed=True)["paused"] == 13   # 5 + the 8 not restocked
    by_name = {p.name: p for p in repo.get_products("S1")}
    assert all(by_name[n].status == "active" for n in done["products"])
    assert len([a for a in repo.get_actions(call_id=call) if a["type"] == "pause_listings"]) == 1


def test_followup_call_does_not_reorder_what_is_already_on_order(fresh_db):
    call = repo.create_call("S1")
    t = KamTools("S1", call)
    first = t.create_restock_plan(13, True)["products"]
    assert len(first) == 13
    _end(call)
    t2 = KamTools("S1", repo.create_call("S1"))
    again = t2.create_restock_plan(5, True)
    assert again["status"] == "not_applicable" and "already on the earlier restock plan" in again["reason"]


def test_price_match_keeps_the_diagnosis_stable_and_is_not_repeated(fresh_db):
    call = repo.create_call("S2")
    t = KamTools("S2", call)
    before = {p.id: p.price for p in repo.get_products("S2")}
    assert t.match_rival_prices(10, 15, True)["status"] == "done"
    assert {p.id: p.price for p in repo.get_products("S2")} == before   # the past month is not rewritten
    _end(call)
    t2 = KamTools("S2", repo.create_call("S2"))
    assert t2.diagnosis["primary_cause"] == "pricing"
    assert t2.match_rival_prices(5, 15, True)["status"] == "not_applicable"


def test_memory_skips_calls_where_nothing_happened(fresh_db):
    real = repo.create_call("S1")
    t = KamTools("S1", real)
    t.create_restock_plan(3, True)
    _end(real)
    dropped = repo.create_call("S1")           # e.g. the connection failed right away
    KamTools("S1", dropped)
    repo.update_call(dropped, status="ended", ended_at=datetime.now(timezone.utc))
    memory = KamTools("S1", repo.create_call("S1")).memory_brief()
    assert memory and "Restock 3 top products" in memory


def test_reseeding_only_when_empty_keeps_call_history(fresh_db):
    from brain import seed
    call = repo.create_call("S1")
    assert seed.is_seeded()
    assert repo.get_call(call) is not None     # start.sh uses --if-empty, so restarts keep history


def test_followup_can_be_moved_and_rejects_today_or_past(fresh_db):
    from datetime import timedelta
    call = repo.create_call("S3")
    t = KamTools("S3", call)
    today = repo.today_ist()
    assert t.schedule_followup(3)["status"] == "done"
    moved = t.schedule_followup(5)
    assert moved["status"] == "rescheduled" and moved["date"] == (today + timedelta(days=5)).isoformat()
    on = t.schedule_followup(on_date=(today + timedelta(days=4)).isoformat())
    assert on["status"] == "rescheduled"
    assert t.schedule_followup(on_date=today.isoformat())["status"] == "invalid_date"
    acts = [a for a in repo.get_actions(call_id=call) if a["type"] == "followup"]
    assert len(acts) == 1 and acts[0]["due_date"] == (today + timedelta(days=4)).isoformat()


def test_escalation_is_refused_for_thanks_and_date_changes(fresh_db):
    call = repo.create_call("S3")
    t = KamTools("S3", call)
    assert t.escalate_to_human("other", "Seller expressed strong gratitude; no further action needed.")["status"] == "not_needed"
    assert t.escalate_to_human("seller_asked_for_a_person", "Seller requested a follow-up call on 10 November")["status"] == "not_needed"
    assert repo.get_call(call)["escalated"] is False
    assert t.escalate_to_human("payments", "Seller says last week's payout has not arrived")["status"] == "done"
    assert repo.get_call(call)["escalated"] is True


def test_playbook_fits_each_seller(fresh_db):
    plan = {s: " | ".join(KamTools(s, repo.create_call(s)).playbook()) for s in ("S1", "S2", "S3")}
    assert "create_restock_plan" in plan["S1"] and "set_stock_buffer" in plan["S1"] and "match_rival_prices" not in plan["S1"]
    assert "match_rival_prices" in plan["S2"] and "create_restock_plan" not in plan["S2"]
    assert "enable_dispatch_alerts" in plan["S3"] and "match_rival_prices" not in plan["S3"]
    assert "PLAYBOOK" in KamTools("S3", repo.create_call("S3")).account_brief()


def test_playbook_leads_with_the_biggest_problem(fresh_db):
    first = {s: KamTools(s, repo.create_call(s)).playbook()[0].split(" - ")[0] for s in ("S1", "S2", "S3")}
    assert first == {"S1": "create_restock_plan", "S2": "match_rival_prices", "S3": "enable_dispatch_alerts"}


def test_voice_mode_falls_back_to_sarvam_safely(monkeypatch):
    import asyncio
    import agent

    def patch(models=None, version="v1beta", fail=False):
        async def fake_list(key):
            if fail:
                raise OSError("offline")
            return models or []

        async def fake_probe(key):
            return version
        monkeypatch.setattr(agent, "list_gemini_live_models", fake_list)
        monkeypatch.setattr(agent, "probe_gemini_live", fake_probe)

    resolve = lambda mode: asyncio.run(agent.resolve_voice(mode))  # noqa: E731
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert resolve("gemini") == ("sarvam", None, None)                        # no key
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    patch(fail=True)
    assert resolve("gemini") == ("sarvam", None, None)                        # key or network problem
    patch(models=["gemini-3.8-live"], version=None)
    assert resolve("gemini") == ("sarvam", None, None)                        # endpoint refuses (the 404 case)
    patch(models=["some-new-live", "gemini-3.1-flash-live-preview"])
    assert resolve("gemini") == ("gemini", "gemini-3.1-flash-live-preview", "v1beta")
    assert resolve("sarvam") == ("sarvam", None, None)
    assert agent.choose_gemini_model(["only-one"]) == "only-one" and agent.choose_gemini_model([]) is None


def test_seller_entered_with_totals_only_still_gets_a_plan(fresh_db):
    """The "try your own numbers" seller has no product rows; the agent must still be able to act."""
    from sqlalchemy import insert
    from brain import db
    with db.engine().begin() as cx:
        cx.execute(insert(db.sellers).values(id="C1", name="Own Numbers Store", owner_name="Anita Rao", city="Pune",
                                             category="General", catalogue_size=60, is_custom=True))
        for period, m in (("prev", dict(sales=200000, orders=400, cancel_rate=8, asp=500, oos_products=5)),
                          ("curr", dict(sales=135000, orders=270, cancel_rate=14, asp=500, oos_products=18))):
            cx.execute(insert(db.monthly_metrics).values(seller_id="C1", period=period, **m))
    call = repo.create_call("C1")
    t = KamTools("C1", call)
    assert t.diagnosis["primary_cause"] == "stockouts"
    assert t.stockout_products()["count"] == 13 and t.stockout_products()["product_names_available"] is False
    assert t.cancellation_breakdown()["breakdown_available"] is False
    plan = " | ".join(t.playbook())
    assert "create_restock_plan" in plan and "set_stock_buffer" in plan
    assert t.create_restock_plan(5)["status"] == "needs_confirmation"
    done = t.create_restock_plan(5, seller_confirmed=True)
    assert done["status"] == "done" and "estimate" in done["expected_recovery_per_month"]
    assert t.set_stock_buffer(2, seller_confirmed=True)["status"] == "done"
    assert t.wrap_up()["summary"]["expected_recovery_inr"] == round(13 * 200000 / 55)


def test_cancelling_an_action_reverses_it(fresh_db):
    call = repo.create_call("S1")
    t = KamTools("S1", call)
    t.create_restock_plan(4, True)
    t.pause_unavailable_listings(seller_confirmed=True)
    t.schedule_followup(7)
    paused = [p.id for p in repo.get_products("S1") if p.status == "paused"]
    assert len(paused) == 14
    assert t.cancel_action("pause")["status"] == "cancelled"
    assert not [p for p in repo.get_products("S1") if p.status == "paused"]        # listings switched back on
    assert t.cancel_action("all")["cancelled"] == ["Restock 4 top products", "Follow-up call on " +
                                                   (repo.today_ist() + __import__("datetime").timedelta(days=7)).strftime("%d %b")]
    assert repo.get_actions(call_id=call) == [] and t.cancel_action("all")["status"] == "nothing_to_cancel"
    assert t.create_restock_plan(3, True)["status"] == "done"                      # can be agreed afresh
    s = t.build_summary()
    assert len(s["actions"]) == 1 and len(s["cancelled"]) == 3


def test_stale_live_calls_are_closed(fresh_db):
    from datetime import datetime, timedelta, timezone
    stuck = repo.create_call("S1")
    repo.update_call(stuck, status="live", started_at=datetime.now(timezone.utc) - timedelta(hours=2))
    fresh = repo.create_call("S1")
    repo.update_call(fresh, status="live", started_at=datetime.now(timezone.utc))
    assert repo.close_stale_calls() == 1
    assert repo.get_call(stuck)["status"] == "ended" and repo.get_call(fresh)["status"] == "live"
