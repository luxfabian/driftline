"""MilestoneService and BaselineService rules (R-02, R-03, R-08, R-09, R-10, R-11)."""

from __future__ import annotations

import unittest

from pmtool.domain.commands import MilestoneUpdate, TaskUpdate
from pmtool.domain.enums import MilestoneStatus, TaskStatus
from pmtool.errors import ConfirmationRequired, NotFound, ValidationError
from tests.services.base import D, ServiceTestCase


class MilestoneRules(ServiceTestCase):
    def test_R_02_baseline_equals_forecast_and_create_logged(self):
        mid = self.make_milestone()
        ms = self.svc.milestones.get(mid)
        self.assertEqual(ms.baseline_date, ms.forecast_date)
        self.assertEqual(ms.status, MilestoneStatus.OPEN)
        rows = self.log("milestone", mid)
        self.assertEqual([r["field"] for r in rows], ["baseline_date", "forecast_date", "status"])
        self.assertTrue(all(r["change_kind"] == "create" and r["old_value"] is None for r in rows))

    def test_R_03_forecast_change_logged_with_reason(self):
        mid = self.make_milestone()
        self.clock.advance(days=7)
        self.svc.milestones.update(
            MilestoneUpdate(mid, forecast_date=D("2026-12-11"), reason="Late parts")
        )
        rows = self.log("milestone", mid, "edit")
        self.assertEqual(
            [(r["field"], r["old_value"], r["new_value"], r["reason"]) for r in rows],
            [("forecast_date", "2026-11-30", "2026-12-11", "Late parts")],
        )
        self.assertEqual(self.svc.milestones.get(mid).updated_at, self.clock.now())

    def test_name_required(self):
        with self.assertRaises(ValidationError):
            self.make_milestone(name=" ")

    def test_R_09_achieve_sets_forecast_to_achieved_date(self):
        mid = self.make_milestone()
        self.clock.advance(days=40)
        self.svc.milestones.set_achieved(mid)
        ms = self.svc.milestones.get(mid)
        self.assertEqual(ms.status, MilestoneStatus.ACHIEVED)
        self.assertEqual(ms.achieved_date, self.clock.today())
        self.assertEqual(ms.forecast_date, self.clock.today())
        fields = {r["field"] for r in self.log("milestone", mid, "edit")}
        self.assertEqual(fields, {"status", "forecast_date"})

    def test_R_09_achieve_with_explicit_date_and_forecast_locked(self):
        mid = self.make_milestone()
        self.svc.milestones.set_achieved(mid, D("2026-11-27"))
        self.assertEqual(self.svc.milestones.get(mid).forecast_date, D("2026-11-27"))
        with self.assertRaises(ValidationError) as ctx:
            self.svc.milestones.update(MilestoneUpdate(mid, forecast_date=D("2026-12-01")))
        self.assertEqual(ctx.exception.code, "R-09")

    def test_R_09_reopen_clears_achieved_date_keeps_forecast(self):
        mid = self.make_milestone()
        self.svc.milestones.set_achieved(mid, D("2026-11-27"))
        self.svc.milestones.reopen(mid)
        ms = self.svc.milestones.get(mid)
        self.assertEqual((ms.status, ms.achieved_date, ms.forecast_date),
                         (MilestoneStatus.OPEN, None, D("2026-11-27")))  # fmt: skip

    def test_R_10_archiving_milestone_keeps_tasks_active_and_linked(self):
        mid = self.make_milestone()
        tid = self.make_task(milestone_id=mid)
        self.svc.milestones.archive(mid)
        t = self.task(tid)
        self.assertIsNone(t.archived_at)
        self.assertEqual(t.milestone_id, mid)
        self.assertEqual(self.svc.snapshot.load().milestones, ())
        self.svc.milestones.restore(mid)
        kinds = [r["change_kind"] for r in self.log("milestone", mid) if r["field"] is None]
        self.assertEqual(kinds, ["archive", "restore"])

    def test_R_11_milestone_delete_unlinks_tasks(self):
        mid = self.make_milestone()
        tid = self.make_task(milestone_id=mid)
        with self.assertRaises(ValidationError):
            self.svc.milestones.delete_permanently(mid, confirmed=True)
        self.svc.milestones.archive(mid)
        with self.assertRaises(ConfirmationRequired):
            self.svc.milestones.delete_permanently(mid)
        self.svc.milestones.delete_permanently(mid, confirmed=True)
        self.assertIsNone(self.task(tid).milestone_id)
        self.assertEqual(self.log("milestone", mid), [])


class BaselineRules(ServiceTestCase):
    def test_R_08_rebaseline_tasks_copies_forecast_and_logs(self):
        tid = self.make_task()
        self.svc.tasks.update(
            TaskUpdate(tid, forecast_start=D("2026-10-13"), forecast_end=D("2026-10-23"))
        )
        self.clock.advance(days=1)
        batch = self.svc.baselines.rebaseline_tasks([tid], "Scope extended")
        t = self.task(tid)
        self.assertEqual((t.baseline_start, t.baseline_end), (D("2026-10-13"), D("2026-10-23")))
        rows = self.log("task", tid, "rebaseline")
        self.assertEqual(
            [(r["field"], r["old_value"], r["new_value"], r["reason"]) for r in rows],
            [
                ("baseline_start", "2026-10-12", "2026-10-13", "Scope extended"),
                ("baseline_end", "2026-10-16", "2026-10-23", "Scope extended"),
            ],
        )
        self.assertEqual({r["batch_id"] for r in rows}, {batch})

    def test_R_08_reason_required(self):
        tid = self.make_task()
        for reason in ("", "  ", None):
            with self.assertRaises(ValidationError) as ctx:
                self.svc.baselines.rebaseline_tasks([tid], reason)
            self.assertEqual(ctx.exception.code, "R-08")

    def test_R_08_empty_selection_rejected(self):
        with self.assertRaises(ValidationError):
            self.svc.baselines.rebaseline_tasks([], "x")

    def test_R_08_rebaseline_all_one_batch_open_items_only(self):
        a = self.make_task()
        b = self.make_task()
        done = self.make_task()
        mid = self.make_milestone()
        for tid in (a, b, done):
            self.svc.tasks.update(TaskUpdate(tid, forecast_end=D("2026-10-30")))
        self.svc.tasks.update(TaskUpdate(done, status=TaskStatus.DONE))
        self.svc.milestones.update(MilestoneUpdate(mid, forecast_date=D("2026-12-15")))
        batch = self.svc.baselines.rebaseline_all("Quarterly re-plan")
        rows = self.query("SELECT entity_type, entity_id, batch_id FROM change_log "
                          "WHERE change_kind = 'rebaseline'")  # fmt: skip
        self.assertEqual({r["batch_id"] for r in rows}, {batch})
        self.assertEqual({(r["entity_type"], r["entity_id"]) for r in rows},
                         {("task", a), ("task", b), ("milestone", mid)})  # fmt: skip
        self.assertEqual(self.task(done).baseline_end, D("2026-10-16"))
        self.assertEqual(self.svc.milestones.get(mid).baseline_date, D("2026-12-15"))

    def test_R_08_earlier_baselines_remain_readable(self):
        tid = self.make_task()
        for end in ("2026-10-20", "2026-10-27"):
            self.svc.tasks.update(TaskUpdate(tid, forecast_end=D(end)))
            self.svc.baselines.rebaseline_tasks([tid], f"to {end}")
        history = [
            (r["old_value"], r["new_value"])
            for r in self.log("task", tid, "rebaseline")
            if r["field"] == "baseline_end"
        ]
        self.assertEqual(history, [("2026-10-16", "2026-10-20"), ("2026-10-20", "2026-10-27")])

    def test_R_08_rebaseline_is_atomic(self):
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, forecast_end=D("2026-10-23")))
        with self.assertRaises(NotFound):
            self.svc.baselines.rebaseline_tasks([tid, 999], "x")
        self.assertEqual(self.task(tid).baseline_end, D("2026-10-16"))
        self.assertEqual(self.log("task", tid, "rebaseline"), [])


if __name__ == "__main__":
    unittest.main()
