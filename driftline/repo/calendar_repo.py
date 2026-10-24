"""SQL for ``absence`` and ``public_holiday`` [WL-01]."""

from __future__ import annotations

import sqlite3
from datetime import date

from driftline.domain.models import Absence, Holiday
from driftline.repo._codec import parse_date


def list_absences(conn: sqlite3.Connection) -> list[Absence]:
    rows = conn.execute("SELECT * FROM absence ORDER BY start_date, id")
    return [
        Absence(
            id=r["id"],
            start_date=parse_date(r["start_date"]),
            end_date=parse_date(r["end_date"]),
            note=r["note"],
        )
        for r in rows
    ]


def insert_absence(conn: sqlite3.Connection, start: date, end: date, note: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO absence (start_date, end_date, note) VALUES (?, ?, ?)",
        (start.isoformat(), end.isoformat(), note),
    )
    return int(cur.lastrowid)


def delete_absence(conn: sqlite3.Connection, absence_id: int) -> bool:
    """Returns True if a row was deleted."""
    return conn.execute("DELETE FROM absence WHERE id = ?", (absence_id,)).rowcount > 0


def list_holidays(conn: sqlite3.Connection) -> list[Holiday]:
    rows = conn.execute("SELECT date, name FROM public_holiday ORDER BY date")
    return [Holiday(date=parse_date(r["date"]), name=r["name"]) for r in rows]


def holiday_exists(conn: sqlite3.Connection, day: date) -> bool:
    row = conn.execute("SELECT 1 FROM public_holiday WHERE date = ?", (day.isoformat(),))
    return row.fetchone() is not None


def insert_holiday(conn: sqlite3.Connection, day: date, name: str | None) -> None:
    conn.execute("INSERT INTO public_holiday (date, name) VALUES (?, ?)", (day.isoformat(), name))


def delete_holiday(conn: sqlite3.Connection, day: date) -> bool:
    cur = conn.execute("DELETE FROM public_holiday WHERE date = ?", (day.isoformat(),))
    return cur.rowcount > 0
