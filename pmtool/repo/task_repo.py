"""SQL for the ``task`` table (architecture §6). No rules, no transactions."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from pmtool.domain.enums import Priority, TaskStatus
from pmtool.domain.models import Task
from pmtool.repo._codec import parse_date, parse_timestamp, placeholders, to_db

COLUMNS = (
    "title",
    "description",
    "baseline_start",
    "baseline_end",
    "forecast_start",
    "forecast_end",
    "estimated_effort_h",
    "remaining_effort_h",
    "status",
    "priority",
    "at_risk",
    "milestone_id",
    "last_review_at",
    "created_at",
    "updated_at",
    "archived_at",
)


def insert(conn: sqlite3.Connection, values: Mapping[str, Any]) -> int:
    _check_columns(values)
    cols = list(values)
    cur = conn.execute(
        f"INSERT INTO task ({', '.join(cols)}) VALUES ({placeholders(len(cols))})",
        [to_db(values[c]) for c in cols],
    )
    return int(cur.lastrowid)


def update_fields(conn: sqlite3.Connection, task_id: int, values: Mapping[str, Any]) -> None:
    if not values:
        return
    _check_columns(values)
    assignments = ", ".join(f"{c} = ?" for c in values)
    conn.execute(
        f"UPDATE task SET {assignments} WHERE id = ?",
        [*(to_db(v) for v in values.values()), task_id],
    )


def get(conn: sqlite3.Connection, task_id: int) -> Task | None:
    row = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    labels = _label_map(conn, [task_id])
    preds = _predecessor_map(conn, [task_id])
    return _to_task(row, labels.get(task_id, ()), preds.get(task_id, ()))


def get_many(conn: sqlite3.Connection, task_ids: Iterable[int]) -> list[Task]:
    ids = sorted(set(task_ids))
    if not ids:
        return []
    rows = conn.execute(
        f"SELECT * FROM task WHERE id IN ({placeholders(len(ids))}) ORDER BY id", ids
    ).fetchall()
    return _build(conn, rows)


def list_all(conn: sqlite3.Connection, include_archived: bool) -> list[Task]:
    sql = "SELECT * FROM task"
    if not include_archived:
        sql += " WHERE archived_at IS NULL"
    rows = conn.execute(sql + " ORDER BY id").fetchall()
    return _build(conn, rows)


def existing_ids(conn: sqlite3.Connection, task_ids: Iterable[int]) -> set[int]:
    ids = sorted(set(task_ids))
    if not ids:
        return set()
    rows = conn.execute(f"SELECT id FROM task WHERE id IN ({placeholders(len(ids))})", ids)
    return {r[0] for r in rows}


def delete(conn: sqlite3.Connection, task_id: int) -> None:
    conn.execute("DELETE FROM task WHERE id = ?", (task_id,))


# --- helpers -----------------------------------------------------------------


def _check_columns(values: Mapping[str, Any]) -> None:
    unknown = set(values) - set(COLUMNS)
    if unknown:
        raise KeyError(f"Unknown task columns: {sorted(unknown)}")


def _build(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[Task]:
    ids = [r["id"] for r in rows]
    labels = _label_map(conn, ids)
    preds = _predecessor_map(conn, ids)
    return [_to_task(r, labels.get(r["id"], ()), preds.get(r["id"], ())) for r in rows]


def _label_map(conn: sqlite3.Connection, ids: list[int]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = defaultdict(list)
    if ids:
        rows = conn.execute(
            f"SELECT task_id, label_id FROM task_label WHERE task_id IN ({placeholders(len(ids))})",
            ids,
        )
        for task_id, label_id in rows:
            result[task_id].append(label_id)
    return result


def _predecessor_map(conn: sqlite3.Connection, ids: list[int]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = defaultdict(list)
    if ids:
        rows = conn.execute(
            "SELECT successor_id, predecessor_id FROM task_dependency "
            f"WHERE successor_id IN ({placeholders(len(ids))})",
            ids,
        )
        for successor, predecessor in rows:
            result[successor].append(predecessor)
    return result


def _to_task(row: sqlite3.Row, label_ids: Iterable[int], predecessor_ids: Iterable[int]) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        baseline_start=parse_date(row["baseline_start"]),
        baseline_end=parse_date(row["baseline_end"]),
        forecast_start=parse_date(row["forecast_start"]),
        forecast_end=parse_date(row["forecast_end"]),
        estimated_effort_h=float(row["estimated_effort_h"]),
        remaining_effort_h=float(row["remaining_effort_h"]),
        status=TaskStatus(row["status"]),
        priority=Priority(row["priority"]),
        at_risk=bool(row["at_risk"]),
        milestone_id=row["milestone_id"],
        last_review_at=parse_timestamp(row["last_review_at"]),
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
        archived_at=parse_timestamp(row["archived_at"]),
        label_ids=frozenset(label_ids),
        predecessor_ids=frozenset(predecessor_ids),
    )
