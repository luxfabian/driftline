"""SQL for ``label`` and ``task_label`` (architecture §6)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from pmtool.domain.models import Label


def name_key(name: str) -> str:
    """Case-insensitive identity of a label: ``lower(trim(name))`` [DAT-04]."""
    return name.strip().lower()


def get_or_create(conn: sqlite3.Connection, name: str) -> int:
    key = name_key(name)
    row = conn.execute("SELECT id FROM label WHERE name_key = ?", (key,)).fetchone()
    if row is not None:
        return int(row[0])
    cur = conn.execute("INSERT INTO label (name, name_key) VALUES (?, ?)", (name.strip(), key))
    return int(cur.lastrowid)


def set_task_labels(conn: sqlite3.Connection, task_id: int, label_ids: Iterable[int]) -> None:
    conn.execute("DELETE FROM task_label WHERE task_id = ?", (task_id,))
    conn.executemany(
        "INSERT INTO task_label (task_id, label_id) VALUES (?, ?)",
        [(task_id, label_id) for label_id in sorted(set(label_ids))],
    )


def list_all(conn: sqlite3.Connection) -> list[Label]:
    rows = conn.execute("SELECT id, name, name_key FROM label ORDER BY name_key")
    return [Label(id=r["id"], name=r["name"], name_key=r["name_key"]) for r in rows]


def list_for_task(conn: sqlite3.Connection, task_id: int) -> list[Label]:
    rows = conn.execute(
        "SELECT l.id, l.name, l.name_key FROM label l "
        "JOIN task_label tl ON tl.label_id = l.id WHERE tl.task_id = ? ORDER BY l.name_key",
        (task_id,),
    )
    return [Label(id=r["id"], name=r["name"], name_key=r["name_key"]) for r in rows]
