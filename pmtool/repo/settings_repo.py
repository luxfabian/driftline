"""SQL for ``app_settings`` (single row, id = 1)."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from pmtool.domain.models import Settings

COLUMNS = tuple(f.name for f in fields(Settings))


def get(conn: sqlite3.Connection) -> Settings:
    row = conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
    if row is None:
        return Settings()
    values = {c: row[c] for c in COLUMNS}
    values["working_weekdays"] = parse_weekdays(row["working_weekdays"])
    return Settings(**values)


def update(conn: sqlite3.Connection, values: Mapping[str, Any]) -> None:
    if not values:
        return
    unknown = set(values) - set(COLUMNS)
    if unknown:
        raise KeyError(f"Unknown settings columns: {sorted(unknown)}")
    db_values = dict(values)
    if "working_weekdays" in db_values:
        db_values["working_weekdays"] = format_weekdays(db_values["working_weekdays"])
    assignments = ", ".join(f"{c} = ?" for c in db_values)
    conn.execute(f"UPDATE app_settings SET {assignments} WHERE id = 1", list(db_values.values()))


def parse_weekdays(text: str) -> tuple[int, ...]:
    return tuple(sorted(int(x) for x in text.split(",") if x.strip()))


def format_weekdays(days: tuple[int, ...]) -> str:
    return ",".join(str(d) for d in sorted(days))
