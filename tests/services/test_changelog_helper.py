"""diff_and_log (architecture §7.2) tested directly, independent of callers."""

from __future__ import annotations

import unittest
from datetime import date

from driftline.domain.enums import ChangeKind, EntityType, TaskStatus
from driftline.domain.models import TASK_LOGGED_FIELDS
from driftline.services._base import diff_and_log
from tests.helpers import T0, memory_db

BEFORE = {
    "baseline_start": date(2026, 10, 12),
    "baseline_end": date(2026, 10, 16),
    "forecast_start": date(2026, 10, 12),
    "forecast_end": date(2026, 10, 16),
    "remaining_effort_h": 10.0,
    "status": TaskStatus.PLANNED,
}


class DiffAndLogTest(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()

    def _log(self, before, after, kind=ChangeKind.EDIT):
        return diff_and_log(self.conn, EntityType.TASK, 1, before, after, TASK_LOGGED_FIELDS,
                            kind, "why", "batch", T0)  # fmt: skip

    def test_R_03_unchanged_values_are_not_logged(self):
        self.assertEqual(self._log(BEFORE, dict(BEFORE)), [])
        self.assertEqual(self._log(BEFORE, {"remaining_effort_h": 10}), [])  # 10 == 10.0
        self.assertEqual(self.conn.execute("SELECT count(*) FROM change_log").fetchone()[0], 0)

    def test_R_03_changed_values_logged_unlogged_fields_ignored(self):
        after = {"status": TaskStatus.DONE, "remaining_effort_h": 0.0, "title": "ignored"}
        entries = self._log(BEFORE, after)
        self.assertEqual(
            [(e.field, e.old_value, e.new_value) for e in entries],
            [("remaining_effort_h", "10.0", "0.0"), ("status", "planned", "done")],
        )
        self.assertTrue(all(e.reason == "why" and e.batch_id == "batch" for e in entries))

    def test_create_logs_all_given_fields_with_null_old_value(self):
        entries = self._log({}, BEFORE, ChangeKind.CREATE)
        self.assertEqual([e.field for e in entries], list(TASK_LOGGED_FIELDS))
        self.assertTrue(all(e.old_value is None for e in entries))


if __name__ == "__main__":
    unittest.main()
