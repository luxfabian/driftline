"""Settings page helpers (pure)."""

from __future__ import annotations

import unittest
from datetime import datetime

from pmtool.domain.models import Settings
from pmtool.services.import_service import ImportResult, RowError
from pmtool.ui.pages.settings import (
    capacity_note,
    export_name,
    form_values,
    import_summary,
    row_action_to_action,
    settings_values,
)


class SettingsPageTest(unittest.TestCase):
    def test_form_round_trip(self):
        s = Settings(
            weekly_hours=32,
            working_weekdays=(1, 2, 4),
            plannable_fraction=0.6,
            load_green_max=0.8,
            load_amber_max=1.1,
        )
        values = settings_values(*form_values(s))
        self.assertEqual(values["working_weekdays"], [1, 2, 4])
        self.assertAlmostEqual(values["plannable_fraction"], 0.6)
        self.assertAlmostEqual(values["load_amber_max"], 1.1)
        self.assertEqual(values["weekly_hours"], 32)

    def test_empty_fields_are_left_out(self):
        values = settings_values(None, [1], "", None, None, None, None, None, None)
        self.assertEqual(values, {"working_weekdays": [1]})

    def test_capacity_note(self):
        self.assertIn("5.20 h", capacity_note(40, [1, 2, 3, 4, 5], 65))
        self.assertEqual(capacity_note(None, [1], 65), "")

    def test_export_name(self):
        self.assertEqual(
            export_name(datetime(2026, 10, 24, 9, 5), "xlsx"), "pmtool_export_20261024_0905.xlsx"
        )

    def test_row_actions(self):
        self.assertEqual(
            row_action_to_action("delete_task", 4), {"kind": "delete_task", "task_id": 4}
        )
        self.assertEqual(row_action_to_action("remove_holiday", "2026-12-25")["date"], "2026-12-25")
        self.assertEqual(row_action_to_action("restore_milestone", 2)["milestone_ids"], [2])
        self.assertIsNone(row_action_to_action("explode", 1))

    def test_import_summary_lists_errors(self):
        text = str(import_summary(ImportResult(errors=(RowError(3, "title is empty"),))))
        self.assertIn("Line 3: title is empty", text)
        self.assertIn("Imported 2", str(import_summary(ImportResult(task_ids=(1, 2)))))


if __name__ == "__main__":
    unittest.main()
