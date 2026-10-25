"""Schema creation and migrations (architecture §10, steps 4-5).

Version 1 is ``schema.sql``. Later schema changes are appended to
``MIGRATIONS`` as ``{version: sql}``; never edit ``schema.sql`` for them.
"""

from __future__ import annotations

import logging
import sqlite3
from importlib import resources

from driftline.db.connection import transaction

logger = logging.getLogger(__name__)

BASE_VERSION = 1

# version -> SQL that upgrades from (version - 1) to version.
MIGRATIONS: dict[int, str] = {
    # 2: colour theme (a ColorTheme value; checked by the settings service, so new
    # themes need no migration).
    2: "ALTER TABLE app_settings ADD COLUMN theme TEXT NOT NULL DEFAULT 'no309';",
}


def latest_version() -> int:
    return max([BASE_VERSION, *MIGRATIONS])


def read_schema_sql() -> str:
    return resources.files("driftline.db").joinpath("schema.sql").read_text(encoding="utf-8")


def current_version(conn: sqlite3.Connection) -> int | None:
    """Schema version of the database, or None for an empty database."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if exists is None:
        return None
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        raise RuntimeError("schema_version table exists but is empty; database is damaged")
    return int(row[0])


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Create the schema on an empty database, else run pending migrations.

    Returns the schema version after the call.
    """
    version = current_version(conn)

    if version is None:
        logger.info("Empty database: creating schema version %s", BASE_VERSION)
        conn.executescript(read_schema_sql())
        conn.execute("PRAGMA foreign_keys = ON")  # executescript may reset session state
        version = BASE_VERSION

    target = latest_version()
    if version > target:
        raise RuntimeError(
            f"Database schema version {version} is newer than this program supports "
            f"({target}). Update driftline."
        )

    for next_version in range(version + 1, target + 1):
        logger.info("Migrating schema %s -> %s", next_version - 1, next_version)
        with transaction(conn):
            for statement in _split_statements(MIGRATIONS[next_version]):
                conn.execute(statement)
            conn.execute("UPDATE schema_version SET version = ?", (next_version,))
        version = next_version

    return version


def ensure_settings_row(conn: sqlite3.Connection) -> None:
    """Make sure the single ``app_settings`` row exists (architecture §10 step 5)."""
    with transaction(conn):
        conn.execute("INSERT OR IGNORE INTO app_settings (id) VALUES (1)")


def _split_statements(sql: str) -> list[str]:
    """Split a migration script into complete statements (keeps it transactional)."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError(f"Incomplete SQL statement in migration: {buffer.strip()[:80]}")
    return statements
