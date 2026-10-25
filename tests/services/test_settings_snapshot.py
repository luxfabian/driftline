"""SettingsService and SnapshotService."""

from __future__ import annotations

import unittest

from driftline.domain.commands import MilestoneUpdate
from driftline.domain.models import Settings
from driftline.errors import NotFound, ValidationError
from tests.services.base import D, ServiceTestCase


class SettingsTest(ServiceTestCase):
    def test_defaults(self):
        self.assertEqual(self.svc.settings.get(), Settings())

    def test_update_and_persist(self):
        new = self.svc.settings.update(
            weekly_hours=32, working_weekdays="5,1,2,3", plannable_fraction=0.7,
            default_horizon_weeks=6, stale_after_days=7,
        )  # fmt: skip
        self.assertEqual(new.working_weekdays, (1, 2, 3, 5))
        self.assertEqual(self.svc.settings.get(), new)

    def test_theme_is_stored(self):
        self.assertEqual(self.svc.settings.get().theme, "no309")
        self.svc.settings.update(theme="no278")
        self.assertEqual(self.svc.settings.get().theme, "no278")

    def test_invalid_values_rejected_and_nothing_written(self):
        bad = [
            {"weekly_hours": 0},
            {"plannable_fraction": 1.2},
            {"plannable_fraction": 0},
            {"working_weekdays": []},
            {"working_weekdays": [1, 1]},
            {"working_weekdays": [0, 8]},
            {"default_horizon_weeks": 13},
            {"default_horizon_weeks": 2.5},
            {"stale_after_days": 0},
            {"backup_keep_count": -1},
            {"load_green_max": 1.2, "load_amber_max": 1.0},
            {"load_green_max": 0},
            {"colour": "blue"},
            {"theme": "neon"},
        ]
        for values in bad:
            with self.assertRaises(ValidationError, msg=values):
                self.svc.settings.update(**values)
        self.assertEqual(self.svc.settings.get(), Settings())

    def test_absences(self):
        aid = self.svc.settings.add_absence(D("2026-12-21"), D("2027-01-01"), " Vacation ")
        self.assertEqual(self.svc.settings.list_absences()[0].note, "Vacation")
        with self.assertRaises(ValidationError):
            self.svc.settings.add_absence(D("2026-12-21"), D("2026-12-20"))
        self.svc.settings.remove_absence(aid)
        self.assertEqual(self.svc.settings.list_absences(), [])
        with self.assertRaises(NotFound):
            self.svc.settings.remove_absence(aid)

    def test_holidays(self):
        self.svc.settings.add_holiday(D("2026-12-25"), "Christmas")
        with self.assertRaises(ValidationError):
            self.svc.settings.add_holiday(D("2026-12-25"))
        self.assertEqual([h.date for h in self.svc.settings.list_holidays()], [D("2026-12-25")])
        self.svc.settings.remove_holiday(D("2026-12-25"))
        with self.assertRaises(NotFound):
            self.svc.settings.remove_holiday(D("2026-12-25"))


class SnapshotTest(ServiceTestCase):
    def test_snapshot_contents(self):
        mid = self.make_milestone()
        a = self.make_task(label_names=("Work",), milestone_id=mid)
        b = self.make_task(predecessor_ids=(a,))
        archived = self.make_task()
        self.svc.tasks.archive(archived)
        self.svc.tasks.set_at_risk(a, True, "Late input")
        self.svc.tasks.set_at_risk(b, True, "Old reason")
        self.svc.tasks.set_at_risk(b, False)
        self.svc.settings.add_holiday(D("2026-12-25"))
        self.svc.settings.add_absence(D("2026-12-28"), D("2026-12-31"))
        self.clock.advance(days=3)
        self.svc.milestones.update(MilestoneUpdate(mid, forecast_date=D("2026-12-07")))

        snap = self.svc.snapshot.load()
        self.assertEqual([t.id for t in snap.tasks], [a, b])
        self.assertEqual(snap.tasks[1].predecessor_ids, frozenset({a}))
        self.assertEqual([lbl.name for lbl in snap.labels], ["Work"])
        self.assertEqual(snap.holidays, frozenset({D("2026-12-25")}))
        self.assertEqual(len(snap.absences), 1)
        self.assertEqual(dict(snap.risk_reasons), {a: "Late input"})
        log = snap.milestone_forecast_log[mid]
        self.assertEqual([e.new_value for e in log], ["2026-11-30", "2026-12-07"])
        with self.assertRaises(TypeError):
            snap.risk_reasons[b] = "x"  # read-only

        full = self.svc.snapshot.load(include_archived=True)
        self.assertEqual([t.id for t in full.tasks], [a, b, archived])

    def test_archived_milestone_log_excluded(self):
        mid = self.make_milestone()
        self.svc.milestones.archive(mid)
        self.assertEqual(dict(self.svc.snapshot.load().milestone_forecast_log), {})
        self.assertIn(mid, self.svc.snapshot.load(True).milestone_forecast_log)


if __name__ == "__main__":
    unittest.main()
