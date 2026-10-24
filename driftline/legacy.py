"""One-time move of data from the tool's former name, pmtool (October 2026).

The old default folder ``~/.pmtool`` held ``pmtool.db``, ``pmtool.log`` and
``backups/pmtool_*.db``. On the first start of Driftline, if the default
folder ``~/.driftline`` does not exist yet, the old folder is renamed and its
files get the new names. Nothing is copied or deleted. A custom data folder
(``DRIFTLINE_DATA_DIR``) is never touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from driftline.config import DEFAULT_DATA_DIR, Config

LEGACY_DATA_DIR = Path.home() / ".pmtool"
LEGACY_NAME, NEW_NAME = "pmtool", "driftline"


@dataclass(frozen=True)
class MigrationResult:
    moved: bool
    message: str | None = None  # logged by the caller once logging is set up


def migrate_legacy_data(
    config: Config,
    legacy_dir: Path = LEGACY_DATA_DIR,
    default_dir: Path = DEFAULT_DATA_DIR,
) -> MigrationResult:
    """Rename ``~/.pmtool`` to the default data folder, once. Call before logging setup."""
    target = config.data_dir
    if target != default_dir or not legacy_dir.is_dir():
        return MigrationResult(False)
    if target.exists():
        return MigrationResult(
            False,
            f"Found data from the old name in {legacy_dir}, but {target} already exists; "
            f"left both as they are. Move files by hand if you need the old data.",
        )
    legacy_dir.rename(target)
    for old, new in _file_renames(target):
        old.rename(new)
    return MigrationResult(True, f"Moved your data from {legacy_dir} to {target} (pmtool is "
                                 "now called Driftline).")  # fmt: skip


def _file_renames(folder: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for suffix in (".db", ".db-wal", ".db-shm", ".log"):
        old = folder / f"{LEGACY_NAME}{suffix}"
        if old.exists():
            pairs.append((old, folder / f"{NEW_NAME}{suffix}"))
    backups = folder / "backups"
    if backups.is_dir():
        for old in sorted(backups.glob(f"{LEGACY_NAME}_*.db")):
            pairs.append((old, backups / (NEW_NAME + old.name[len(LEGACY_NAME) :])))
    return pairs
