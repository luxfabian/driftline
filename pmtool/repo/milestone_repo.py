"""SQL for the ``milestone`` table (architecture §6). No rules, no transactions."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any

from pmtool.domain.enums import MilestoneStatus
from pmtool.domain.models import Milestone
from pmtool.repo._codec import parse_date, parse_timestamp, placeholders, to_db

COLUMNS = (
    "name",
    "description",
    "baseline_date",
    "forecast_date",
    "status",
    "achieved_date",
    "created_at",
    "updated_at",
    "archived_at",
)


def insert(conn: sqlite3.Connection, values: Mapping[str, Any]) -> int:
    _check_columns(values)
    cols = list(values)
    cur = conn.execute(
        f"INSERT INTO milestone ({', '.join(cols)}) VALUES ({placeholders(len(cols))})",
        [to_db(values[c]) for c in cols],
    )
    return int(cur.lastrowid)


def update_fields(conn: sqlite3.Connection, milestone_id: int, values: Mapping[str, Any]) -> None:
    if not values:
        return
    _check_columns(values)
    assignments = ", ".join(f"{c} = ?" for c in values)
    conn.execute(
        f"UPDATE milestone SET {assignments} WHERE id = ?",
        [*(to_db(v) for v in values.values()), milestone_id],
    )


def get(conn: sqlite3.Connection, milestone_id: int) -> Milestone | None:
    row = conn.execute("SELECT * FROM milestone WHERE id = ?", (milestone_id,)).fetchone()
    return None if row is None else _to_milestone(row)


def list_all(conn: sqlite3.Connection, include_archived: bool) -> list[Milestone]:
    sql = "SELECT * FROM milestone"
    if not include_archived:
        sql += " WHERE archived_at IS NULL"
    return [_to_milestone(r) for r in conn.execute(sql + " ORDER BY id")]


def existing_ids(conn: sqlite3.Connection, milestone_ids: Iterable[int]) -> set[int]:
    ids = sorted(set(milestone_ids))
    if not ids:
        return set()
    rows = conn.execute(f"SELECT id FROM milestone WHERE id IN ({placeholders(len(ids))})", ids)
    return {r[0] for r in rows}


def delete(conn: sqlite3.Connection, milestone_id: int) -> None:
    conn.execute("DELETE FROM milestone WHERE id = ?", (milestone_id,))


def _check_columns(values: Mapping[str, Any]) -> None:
    unknown = set(values) - set(COLUMNS)
    if unknown:
        raise KeyError(f"Unknown milestone columns: {sorted(unknown)}")


def _to_milestone(row: sqlite3.Row) -> Milestone:
    return Milestone(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        baseline_date=parse_date(row["baseline_date"]),
        forecast_date=parse_date(row["forecast_date"]),
        status=MilestoneStatus(row["status"]),
        achieved_date=parse_date(row["achieved_date"]),
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
        archived_at=parse_timestamp(row["archived_at"]),
    )
