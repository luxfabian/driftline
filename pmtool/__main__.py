"""Entry point: ``python -m pmtool`` (architecture §10)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from pmtool.clock import Clock, SystemClock
from pmtool.config import Config, load_config, setup_logging
from pmtool.db.backup import backup_on_start, read_keep_count
from pmtool.db.connection import connect
from pmtool.db.migrations import apply_migrations, ensure_settings_row
from pmtool.services import build_services
from pmtool.ui.app import create_app

logger = logging.getLogger("pmtool")


def startup(config: Config, clock: Clock) -> Path:
    """Steps 2-5 of §10: data dir, backup, migrations, settings row.

    Returns the database path. Logging (step 1) is set up by the caller.
    """
    config.data_dir.mkdir(parents=True, exist_ok=True)

    keep = read_keep_count(config.db_path)
    backup_on_start(config.db_path, keep, backup_dir=config.backup_dir, now=clock.now())

    conn = connect(config.db_path)
    try:
        version = apply_migrations(conn)
        ensure_settings_row(conn)
    finally:
        conn.close()
    logger.info("Database ready at %s (schema version %s)", config.db_path, version)
    return config.db_path


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    setup_logging(config)
    clock = SystemClock()
    db_path = startup(config, clock)

    services = build_services(db_path, clock)
    app = create_app(services)
    logger.info("Open http://%s:%s in your browser", config.host, config.port)
    app.run(host=config.host, port=config.port, debug=False)  # localhost only [NFR-02]
    return 0


if __name__ == "__main__":
    sys.exit(main())
