"""Nightly scan: run the diagnosis for every seller and store it.

The team dashboard reads these rows to list sellers who need attention before
they call. At scale this is one cheap batch job; no LLM is involved.

Run:  python -m brain.jobs
"""
from __future__ import annotations

from sqlalchemy import select

from . import db, repo


def scan_all() -> list[dict]:
    """Diagnose every seller, store each result, and return a one-line summary per seller."""
    with db.engine().connect() as cx:
        ids = [r[0] for r in cx.execute(select(db.sellers.c.id))]
    out = []
    for seller_id in ids:
        try:
            d = repo.run_diagnosis(seller_id)
            out.append(dict(seller_id=seller_id, risk=d["risk_level"], cause=d["primary_cause"],
                            gap=d["gap_inr"]))
        except LookupError:        # a seller with no metrics yet: nothing to diagnose
            continue
    return out


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    for row in scan_all():
        print(row)
