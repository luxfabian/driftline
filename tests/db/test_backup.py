"""Phase 1 acceptance: backup test passes [NFR-04]."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from pmtool.db.backup import backup_on_start, list_backups, read_keep_count
from pmtool.db.connection import connect
from pmtool.db.migrations import apply_migrations
from tests.helpers import T0, insert_task


class BackupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.db = self.dir / "pmtool.db"
        self.backups = self.dir / "backups"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_db(self, tasks: int = 1) -> None:
        conn = connect(self.db)
        apply_migrations(conn)
        for _ in range(tasks):
            insert_task(conn)
        conn.close()

    def test_no_database_no_backup(self):
        self.assertIsNone(backup_on_start(self.db, 10, now=T0))
        self.assertFalse(self.backups.exists())

    def test_backup_has_expected_name_and_content(self):
        self._make_db(tasks=3)
        path = backup_on_start(self.db, 10, now=T0)
        self.assertEqual(path, self.backups / "pmtool_20261010_090000.db")
        copy = sqlite3.connect(path)
        self.assertEqual(copy.execute("SELECT count(*) FROM task").fetchone()[0], 3)
        copy.close()

    def test_keeps_only_last_n(self):
        self._make_db()
        for i in range(5):
            backup_on_start(self.db, 3, now=T0 + timedelta(minutes=i))
        names = [p.name for p in list_backups(self.backups)]
        self.assertEqual(
            names,
            ["pmtool_20261010_090200.db", "pmtool_20261010_090300.db", "pmtool_20261010_090400.db"],
        )

    def test_same_second_does_not_overwrite(self):
        self._make_db()
        first = backup_on_start(self.db, 10, now=T0)
        second = backup_on_start(self.db, 10, now=T0)
        self.assertNotEqual(first, second)
        self.assertEqual(len(list_backups(self.backups)), 2)

    def test_custom_backup_dir(self):
        self._make_db()
        target = self.dir / "elsewhere"
        path = backup_on_start(self.db, 10, backup_dir=target, now=T0)
        self.assertEqual(path.parent, target)

    def test_now_is_required(self):
        self._make_db()
        with self.assertRaises(ValueError):
            backup_on_start(self.db, 10)

    def test_invalid_keep(self):
        with self.assertRaises(ValueError):
            backup_on_start(self.db, 0, now=T0)

    def test_read_keep_count(self):
        self.assertEqual(read_keep_count(self.db), 10)  # no file
        sqlite3.connect(self.db).close()  # empty file, no tables
        self.assertEqual(read_keep_count(self.db), 10)
        self.db.unlink()
        self._make_db(tasks=0)
        conn = connect(self.db)
        conn.execute("UPDATE app_settings SET backup_keep_count = 4")
        conn.close()
        self.assertEqual(read_keep_count(self.db), 4)


if __name__ == "__main__":
    unittest.main()
