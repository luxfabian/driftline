"""Shared plumbing for services: connection per call, change-log helper, validators."""

from __future__ import annotations

import math
import sqlite3
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from pmtool.clock import Clock
from pmtool.db.connection import connect, transaction
from pmtool.domain.enums import ChangeKind, EntityType
from pmtool.domain.models import ChangeLogEntry
from pmtool.errors import ValidationError
from pmtool.repo import changelog_repo
from pmtool.repo._codec import encode_log_value


class ServiceBase:
    """Each public method opens its own connection and runs one transaction (§7.1, P3)."""

    def __init__(self, db_path: Path | str, clock: Clock) -> None:
        self.db_path = db_path
        self.clock = clock

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self.db_path)
        try:
            with transaction(conn):
                yield conn
        finally:
            conn.close()


def new_batch_id() -> str:
    return uuid.uuid4().hex


def diff_and_log(
    conn: sqlite3.Connection,
    entity_type: EntityType,
    entity_id: int,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    logged_fields: Sequence[str],
    change_kind: ChangeKind,
    reason: str | None,
    batch_id: str,
    now: datetime,
) -> list[ChangeLogEntry]:
    """Write one change_log row per logged field whose value changed (R-03).

    For ``create``, pass an empty ``before``: every logged field in ``after``
    is written with old_value NULL (R-01, R-02). Returns the written entries.
    """
    entries: list[ChangeLogEntry] = []
    for name in logged_fields:
        if name not in after:
            continue
        old = before.get(name) if change_kind is not ChangeKind.CREATE else None
        new = after[name]
        old_text, new_text = encode_log_value(old), encode_log_value(new)
        if change_kind is not ChangeKind.CREATE and old_text == new_text:
            continue
        entries.append(
            ChangeLogEntry(
                entity_type=entity_type,
                entity_id=entity_id,
                change_kind=change_kind,
                field=name,
                old_value=old_text,
                new_value=new_text,
                reason=reason,
                batch_id=batch_id,
                changed_at=now,
            )
        )
    changelog_repo.insert_many(conn, entries)
    return entries


def log_event(
    conn: sqlite3.Connection,
    entity_type: EntityType,
    entity_id: int,
    change_kind: ChangeKind,
    now: datetime,
    reason: str | None = None,
) -> None:
    """Single row without a field, used for archive / restore (R-10)."""
    changelog_repo.insert_many(
        conn,
        [
            ChangeLogEntry(
                entity_type=entity_type,
                entity_id=entity_id,
                change_kind=change_kind,
                field=None,
                old_value=None,
                new_value=None,
                reason=reason,
                batch_id=new_batch_id(),
                changed_at=now,
            )
        ],
    )


# --- validators ---------------------------------------------------------------


def clean_text(value: str | None) -> str | None:
    """Strip; empty becomes None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def require_text(value: str | None, code: str, what: str) -> str:
    cleaned = clean_text(value)
    if cleaned is None:
        raise ValidationError(code, f"{what} must not be empty.")
    return cleaned


def require_effort(value: float, what: str) -> float:  # [VAL-02]
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("VAL-02", f"{what} must be a number.") from exc
    if not math.isfinite(number) or number < 0:
        raise ValidationError("VAL-02", f"{what} must be 0 or more hours.")
    return number
