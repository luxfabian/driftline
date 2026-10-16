"""SQL for ``task_dependency`` (architecture §6). Metadata only [DAT-06]."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable


def set_predecessors(
    conn: sqlite3.Connection, task_id: int, predecessor_ids: Iterable[int]
) -> None:
    conn.execute("DELETE FROM task_dependency WHERE successor_id = ?", (task_id,))
    conn.executemany(
        "INSERT INTO task_dependency (predecessor_id, successor_id) VALUES (?, ?)",
        [(p, task_id) for p in sorted(set(predecessor_ids))],
    )


def list_all(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """All edges as (predecessor_id, successor_id)."""
    rows = conn.execute(
        "SELECT predecessor_id, successor_id FROM task_dependency "
        "ORDER BY predecessor_id, successor_id"
    )
    return [(r[0], r[1]) for r in rows]


def successor_ids(conn: sqlite3.Connection, task_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT successor_id FROM task_dependency WHERE predecessor_id = ? ORDER BY successor_id",
        (task_id,),
    )
    return [r[0] for r in rows]
