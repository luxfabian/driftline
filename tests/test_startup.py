"""Startup sequence (architecture §10, steps 2-5)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from driftline.__main__ import startup
from driftline.clock import FixedClock
from driftline.config import load_config
from driftline.db.backup import list_backups
from driftline.db.connection import connect
from driftline.db.migrations import latest_version
from tests.helpers import T0


class StartupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config = load_config({"DRIFTLINE_DATA_DIR": str(Path(self._tmp.name) / "data")})
        self.clock = FixedClock(T0)

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_start_creates_db_without_backup(self):
        db = startup(self.config, self.clock)
        self.assertTrue(db.exists())
        self.assertEqual(list_backups(self.config.backup_dir), [])
        conn = connect(db)
        self.assertEqual(
            conn.execute("SELECT version FROM schema_version").fetchone()[0], latest_version()
        )
        self.assertEqual(conn.execute("SELECT count(*) FROM app_settings").fetchone()[0], 1)
        conn.close()

    def test_restart_backs_up_and_respects_keep_setting(self):
        startup(self.config, self.clock)
        conn = connect(self.config.db_path)
        conn.execute("UPDATE app_settings SET backup_keep_count = 2")
        conn.close()
        for _ in range(4):
            self.clock.advance(minutes=1)
            startup(self.config, self.clock)
        self.assertEqual(len(list_backups(self.config.backup_dir)), 2)

    def test_data_survives_restart(self):  # [DAT-07]
        startup(self.config, self.clock)
        conn = connect(self.config.db_path)
        conn.execute("UPDATE app_settings SET weekly_hours = 32")
        conn.close()
        self.clock.advance(seconds=5)
        startup(self.config, self.clock)
        conn = connect(self.config.db_path)
        self.assertEqual(conn.execute("SELECT weekly_hours FROM app_settings").fetchone()[0], 32)
        conn.close()


if __name__ == "__main__":
    unittest.main()
