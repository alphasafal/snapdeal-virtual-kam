"""The database tables, and the connection to the database.

Postgres in production (set DATABASE_URL), a local SQLite file when DATABASE_URL is empty
(tests and the terminal "console" mode).

The tables, and what each one holds:

  sellers          one row per seller: name, owner, city, category
  monthly_metrics  two rows per seller: last month ("prev") and this month ("curr")
  products         the seller's catalogue with units sold in each month and stock status
  cancel_reasons   how many orders were cancelled, by whom and why, in each month
  calls            one row per voice call: who, when, status, summary, cost, reply delay
  call_turns       the transcript: one row per thing said (or done) on a call
  actions          what the seller agreed to on a call (restock plan, price match, ...)
  followups        follow-up calls that have been booked
  call_reviews     a team member's sign-off or flag on a finished call
  diagnoses        the latest diagnosis for each seller (see diagnosis.py)
  plans            the what-if planner's options for each seller (see planner.py)

Every table is plain rows. No state lives in the agent process, so any number of agent
workers can serve calls in parallel. To read or write these tables, use repo.py.
"""
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, Integer, MetaData,
                        String, Table, Text, create_engine)

metadata = MetaData()

sellers = Table(
    "sellers", metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("owner_name", String, nullable=False),
    Column("city", String),
    Column("category", String),
    Column("catalogue_size", Integer),
    Column("is_custom", Boolean, default=False),
    Column("created_at", DateTime(timezone=True)),
)

# Two rows per seller: period = 'prev' (last month) and 'curr' (this month).
monthly_metrics = Table(
    "monthly_metrics", metadata,
    Column("seller_id", String, primary_key=True),
    Column("period", String, primary_key=True),
    Column("sales", Float, nullable=False),
    Column("orders", Integer, nullable=False),
    Column("cancel_rate", Float, nullable=False),      # percent, e.g. 14.0
    Column("asp", Float, nullable=False),
    Column("oos_products", Integer, nullable=False),
    Column("visits", Integer),                         # optional extras (assumptions)
    Column("rating", Float),
    Column("price_gap_pct", Float),                    # our price vs cheapest rival, top products
    Column("late_dispatch_rate", Float),
)

products = Table(
    "products", metadata,
    Column("id", String, primary_key=True),
    Column("seller_id", String, index=True, nullable=False),
    Column("name", String, nullable=False),
    Column("price", Float, nullable=False),
    Column("units_prev", Integer, nullable=False),
    Column("units_curr", Integer, nullable=False),
    Column("in_stock", Boolean, nullable=False),
    Column("oos_prev", Boolean, nullable=False, default=False),
    Column("days_oos_curr", Integer, nullable=False, default=0),
    Column("competitor_price", Float),
    Column("status", String, nullable=False, default="active"),   # active | paused
)

cancel_reasons = Table(
    "cancel_reasons", metadata,
    Column("seller_id", String, primary_key=True),
    Column("period", String, primary_key=True),
    Column("side", String, primary_key=True),          # seller | buyer
    Column("reason", String, primary_key=True),
    Column("count", Integer, nullable=False),
)

calls = Table(
    "calls", metadata,
    Column("id", String, primary_key=True),            # also the LiveKit room name
    Column("seller_id", String, index=True, nullable=False),
    Column("direction", String, nullable=False, default="inbound"),  # inbound | proactive
    Column("voice_mode", String),
    Column("language", String, default="en"),          # en | hinglish
    Column("status", String, nullable=False, default="created"),     # created | live | ended
    Column("started_at", DateTime(timezone=True)),
    Column("ended_at", DateTime(timezone=True)),
    Column("duration_s", Integer),
    Column("root_cause", String),
    Column("summary", JSON),
    Column("notes", JSON),                             # what the seller told us
    Column("est_cost_inr", Float),
    Column("avg_latency_ms", Integer),
    Column("escalated", Boolean, default=False),
)

call_turns = Table(
    "call_turns", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("call_id", String, index=True, nullable=False),
    Column("role", String, nullable=False),            # seller | agent
    Column("text", Text, nullable=False),
    Column("at", DateTime(timezone=True)),
)

actions = Table(
    "actions", metadata,
    Column("id", String, primary_key=True),
    Column("call_id", String, index=True, nullable=False),
    Column("seller_id", String, index=True, nullable=False),
    Column("type", String, nullable=False),
    Column("title", String, nullable=False),
    Column("detail", JSON),
    Column("expected_recovery_inr", Float),
    Column("status", String, nullable=False, default="confirmed"),   # confirmed | partly_done | done
    Column("progress", String),
    Column("due_date", String),
    Column("created_at", DateTime(timezone=True)),
)

followups = Table(
    "followups", metadata,
    Column("id", String, primary_key=True),
    Column("seller_id", String, index=True, nullable=False),
    Column("call_id", String),
    Column("due_date", String, nullable=False),
    Column("purpose", String),
    Column("status", String, nullable=False, default="scheduled"),
)

# A person on the Snapdeal team can open any finished call and sign it off or flag it.
call_reviews = Table(
    "call_reviews", metadata,
    Column("call_id", String, primary_key=True),
    Column("verdict", String, nullable=False),         # ok | needs_followup
    Column("reviewer", String),
    Column("note", Text),
    Column("reviewed_at", DateTime(timezone=True)),
)

# Latest diagnosis per seller, written by the nightly scan and at call start.
diagnoses = Table(
    "diagnoses", metadata,
    Column("seller_id", String, primary_key=True),
    Column("computed_at", DateTime(timezone=True)),
    Column("risk_level", String),
    Column("primary_cause", String),
    Column("gap_inr", Float),
    Column("headline", String),
    Column("result", JSON),
)

# What-if planner options per seller, written by the nightly scan (see planner.py).
plans = Table(
    "plans", metadata,
    Column("seller_id", String, primary_key=True),
    Column("computed_at", DateTime(timezone=True)),
    Column("gap_inr", Float),                          # the sales drop being planned against
    Column("recoverable_inr", Float),                  # the most all options could win back together
    Column("options", JSON),                           # list of {key, title, detail, recover_inr, when}
)


def database_url() -> str:
    """The database address in the form SQLAlchemy expects."""
    url = os.environ.get("DATABASE_URL", "").strip() or "sqlite:///kam_local.db"   # empty means local file
    # Hosting providers hand out "postgres://..." or "postgresql://..."; name the driver explicitly.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@lru_cache(maxsize=1)
def engine():
    """The shared database connection pool, created on first use and reused after that.
    `pool_pre_ping` checks a connection is still alive before using it."""
    return create_engine(database_url(), pool_pre_ping=True, future=True)


def create_schema() -> None:
    """Create any tables that do not exist yet. Safe to call repeatedly."""
    metadata.create_all(engine())


def reset_engine() -> None:
    """Forget the cached connection pool. Used by tests after changing DATABASE_URL."""
    engine.cache_clear()
