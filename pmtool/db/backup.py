"""Backup on start [NFR-04] (architecture §10 step 3)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUP_PREFIX = "pmtool_"
BACKUP_SUFFIX = ".db"
DEFAULT_KEEP = 10


def backup_on_start(
    db_path: Path | str,
    keep: int,
    *,
    backup_dir: Path | str | None = None,
    now: datetime | None = None,
) -> Path | None:
    """Copy the database to ``backups/pmtool_YYYYMMDD_HHMMSS.db`` and prune old copies.

    Uses the SQLite backup API, so the copy is consistent. Returns the new
    backup path, or None if the database file does not exist yet.
    ``backup_dir`` defaults to ``<db folder>/backups``. ``now`` is the time used
    in the file name; the caller passes it from its Clock (P7).
    """
    if keep < 1:
        raise ValueError("keep must be >= 1")
    db_path = Path(db_path)
    if not db_path.exists():
        return None

    target_dir = Path(backup_dir) if backup_dir is not None else db_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)

    if now is None:
        raise ValueError("now is required (pass clock.now())")
    target = _unique_name(target_dir, now)

    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    logger.info("Database backed up to %s", target)

    prune_backups(target_dir, keep)
    return target


def list_backups(backup_dir: Path | str) -> list[Path]:
    """Backup files, oldest first (the timestamp in the name sorts correctly)."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    return sorted(p for p in backup_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}") if p.is_file())


def prune_backups(backup_dir: Path | str, keep: int) -> list[Path]:
    """Delete the oldest backups beyond ``keep``. Returns the deleted paths."""
    backups = list_backups(backup_dir)
    excess = backups[: max(0, len(backups) - keep)]
    for path in excess:
        path.unlink()
        logger.info("Deleted old backup %s", path)
    return excess


def read_keep_count(db_path: Path | str, default: int = DEFAULT_KEEP) -> int:
    """``app_settings.backup_keep_count`` of an existing database, else ``default``.

    Read before migrations run, so any missing table or row falls back to the
    default instead of failing.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return default
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT backup_keep_count FROM app_settings WHERE id = 1").fetchone()
    except sqlite3.Error:
        return default
    finally:
        conn.close()
    if row is None or row[0] is None or int(row[0]) < 1:
        return default
    return int(row[0])


def _unique_name(target_dir: Path, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%d_%H%M%S")
    candidate = target_dir / f"{BACKUP_PREFIX}{stamp}{BACKUP_SUFFIX}"
    counter = 1
    while candidate.exists():  # two starts within the same second
        candidate = target_dir / f"{BACKUP_PREFIX}{stamp}_{counter}{BACKUP_SUFFIX}"
        counter += 1
    return candidate
