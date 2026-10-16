"""SQL for ``comment`` (architecture §6). Append-only: no update, no delete."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from pmtool.domain.enums import CommentKind
from pmtool.domain.models import Comment
from pmtool.repo._codec import format_timestamp, parse_timestamp


def insert(
    conn: sqlite3.Connection, task_id: int, kind: CommentKind, text: str, created_at: datetime
) -> int:
    cur = conn.execute(
        "INSERT INTO comment (task_id, kind, text, created_at) VALUES (?, ?, ?, ?)",
        (task_id, kind.value, text, format_timestamp(created_at)),
    )
    return int(cur.lastrowid)


def list_for_task(conn: sqlite3.Connection, task_id: int) -> list[Comment]:
    """Newest first [FUN-03]. ``id`` breaks ties within the same second."""
    rows = conn.execute(
        "SELECT * FROM comment WHERE task_id = ? ORDER BY created_at DESC, id DESC", (task_id,)
    )
    return [
        Comment(
            id=r["id"],
            task_id=r["task_id"],
            kind=CommentKind(r["kind"]),
            text=r["text"],
            created_at=parse_timestamp(r["created_at"]),
        )
        for r in rows
    ]


def latest_risk_reasons(conn: sqlite3.Connection) -> dict[int, str]:
    """task_id -> text of its most recent ``risk_set`` comment."""
    rows = conn.execute(
        "SELECT c.task_id, c.text FROM comment c "
        "JOIN (SELECT task_id, MAX(id) AS max_id FROM comment "
        "      WHERE kind = 'risk_set' GROUP BY task_id) last ON last.max_id = c.id"
    )
    return {r[0]: r[1] for r in rows}
