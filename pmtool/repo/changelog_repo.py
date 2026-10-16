"""SQL for ``change_log`` (architecture §6). Polymorphic, no foreign key."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from pmtool.domain.enums import ChangeKind, EntityType
from pmtool.domain.models import ChangeLogEntry
from pmtool.repo._codec import format_timestamp, parse_timestamp


def insert_many(conn: sqlite3.Connection, entries: Iterable[ChangeLogEntry]) -> None:
    conn.executemany(
        "INSERT INTO change_log (entity_type, entity_id, change_kind, field, old_value, "
        "new_value, reason, batch_id, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                e.entity_type.value,
                e.entity_id,
                e.change_kind.value,
                e.field,
                e.old_value,
                e.new_value,
                e.reason,
                e.batch_id,
                format_timestamp(e.changed_at),
            )
            for e in entries
        ],
    )


def list_for_entity(
    conn: sqlite3.Connection, entity_type: str, entity_id: int
) -> list[ChangeLogEntry]:
    """Oldest first."""
    rows = conn.execute(
        "SELECT * FROM change_log WHERE entity_type = ? AND entity_id = ? ORDER BY changed_at, id",
        (str(entity_type), entity_id),
    )
    return [_to_entry(r) for r in rows]


def list_field(conn: sqlite3.Connection, entity_type: str, field: str) -> list[ChangeLogEntry]:
    """All entries for one field of one entity type, ordered by entity, then time."""
    rows = conn.execute(
        "SELECT * FROM change_log WHERE entity_type = ? AND field = ? "
        "ORDER BY entity_id, changed_at, id",
        (str(entity_type), field),
    )
    return [_to_entry(r) for r in rows]


def delete_for_entity(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> None:
    conn.execute(
        "DELETE FROM change_log WHERE entity_type = ? AND entity_id = ?",
        (str(entity_type), entity_id),
    )


def _to_entry(row: sqlite3.Row) -> ChangeLogEntry:
    return ChangeLogEntry(
        id=row["id"],
        entity_type=EntityType(row["entity_type"]),
        entity_id=row["entity_id"],
        change_kind=ChangeKind(row["change_kind"]),
        field=row["field"],
        old_value=row["old_value"],
        new_value=row["new_value"],
        reason=row["reason"],
        batch_id=row["batch_id"],
        changed_at=parse_timestamp(row["changed_at"]),
    )
