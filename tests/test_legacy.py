"""One-time move of data from the former name pmtool (driftline/legacy.py)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from driftline.config import load_config
from driftline.legacy import migrate_legacy_data


class LegacyMigrationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        home = Path(self._tmp.name)
        self.legacy = home / ".pmtool"
        self.default = home / ".driftline"
        (self.legacy / "backups").mkdir(parents=True)
        (self.legacy / "pmtool.db").write_text("db")
        (self.legacy / "pmtool.log").write_text("log")
        (self.legacy / "backups" / "pmtool_20261024_090000.db").write_text("b1")
        (self.legacy / "notes.txt").write_text("keep me")

    def tearDown(self):
        self._tmp.cleanup()

    def migrate(self, data_dir: Path):
        config = load_config({"DRIFTLINE_DATA_DIR": str(data_dir)})
        return migrate_legacy_data(config, legacy_dir=self.legacy, default_dir=self.default)

    def test_moves_folder_and_renames_files(self):
        result = self.migrate(self.default)
        self.assertTrue(result.moved)
        self.assertIn("Driftline", result.message)
        self.assertFalse(self.legacy.exists())
        self.assertEqual((self.default / "driftline.db").read_text(), "db")
        self.assertEqual((self.default / "driftline.log").read_text(), "log")
        self.assertTrue((self.default / "backups" / "driftline_20261024_090000.db").exists())
        self.assertEqual((self.default / "notes.txt").read_text(), "keep me")

    def test_runs_only_once(self):
        self.migrate(self.default)
        again = self.migrate(self.default)
        self.assertFalse(again.moved)
        self.assertIsNone(again.message)

    def test_never_overwrites_an_existing_folder(self):
        self.default.mkdir()
        result = self.migrate(self.default)
        self.assertFalse(result.moved)
        self.assertIn("left both", result.message)
        self.assertTrue((self.legacy / "pmtool.db").exists())

    def test_custom_data_folder_is_left_alone(self):
        result = self.migrate(Path(self._tmp.name) / "elsewhere")
        self.assertFalse(result.moved)
        self.assertTrue(self.legacy.exists())


if __name__ == "__main__":
    unittest.main()
