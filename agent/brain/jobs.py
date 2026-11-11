"""Nightly scan: run the diagnosis for every seller and store it, with the planner's options.

The team dashboard reads these rows to rank sellers by the rupees that could be won back,
so Asha can call the right ones first. At scale this is one cheap batch job; no LLM is involved.

Run:  python -m brain.jobs
"""
from __future__ import annotations

from sqlalchemy import delete, insert, select

from . import db, repo
from .planner import plan_options


def scan_all() -> list[dict]:
    """Diagnose every seller, store each result, and return a one-line summary per seller."""
    with db.engine().connect() as cx:
        ids = [r[0] for r in cx.execute(select(db.sellers.c.id))]
    out = []
    for seller_id in ids:
        try:
            d = repo.run_diagnosis(seller_id)
            plan = plan_options(seller_id, d)
            with db.engine().begin() as cx:
                cx.execute(delete(db.plans).where(db.plans.c.seller_id == seller_id))
                cx.execute(insert(db.plans).values(
                    seller_id=seller_id, computed_at=repo.now(), gap_inr=plan["gap_inr"],
                    recoverable_inr=plan["recoverable_inr"], options=plan["options"]))
            out.append(dict(seller_id=seller_id, risk=d["risk_level"], cause=d["primary_cause"],
                            gap=d["gap_inr"], recoverable=plan["recoverable_inr"]))
        except LookupError:        # a seller with no metrics yet: nothing to diagnose
            continue
    return out


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    for row in scan_all():
        print(row)
