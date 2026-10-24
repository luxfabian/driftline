"""Shared test helpers (plain functions so the tests run with unittest and pytest).

Architecture §11 names tests/conftest.py fixtures; plain modules are used on
purpose instead, so ``python -m unittest discover`` keeps working without pytest.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from pmtool.db.connection import connect
from pmtool.db.migrations import apply_migrations

BERLIN = ZoneInfo("Europe/Berlin")
T0 = datetime(2026, 10, 10, 9, 0, 0, tzinfo=BERLIN)
TS = T0.isoformat()


def memory_db() -> sqlite3.Connection:
    conn = connect(":memory:")
    apply_migrations(conn)
    return conn


def insert_milestone(conn: sqlite3.Connection, **overrides) -> int:
    values = {
        "name": "M1",
        "baseline_date": "2026-11-30",
        "forecast_date": "2026-11-30",
        "status": "open",
        "achieved_date": None,
        "created_at": TS,
        "updated_at": TS,
    }
    values.update(overrides)
    return _insert(conn, "milestone", values)


def insert_task(conn: sqlite3.Connection, **overrides) -> int:
    values = {
        "title": "Task",
        "baseline_start": "2026-10-12",
        "baseline_end": "2026-10-16",
        "forecast_start": "2026-10-12",
        "forecast_end": "2026-10-16",
        "estimated_effort_h": 8.0,
        "remaining_effort_h": 8.0,
        "last_review_at": TS,
        "created_at": TS,
        "updated_at": TS,
    }
    values.update(overrides)
    return _insert(conn, "task", values)


def _insert(conn: sqlite3.Connection, table: str, values: dict) -> int:
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
    return int(cur.lastrowid)
