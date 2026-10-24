"""UI actions against real services: outcomes, confirmation flow, error mapping."""

from __future__ import annotations

import json
import unittest
from datetime import timedelta

from pmtool.domain.commands import MilestoneUpdate
from pmtool.domain.enums import TaskStatus
from pmtool.ui.actions import execute
from tests.services.base import ServiceTestCase


class CreateTaskActionTest(ServiceTestCase):
    def form(self, **overrides):
        values = {
            "kind": "create_task",
            "title": "Write report",
            "description": "",
            "forecast_start": "2026-10-12",
            "forecast_end": "2026-10-16",
            "estimated_effort_h": 6,
            "priority": "2",  # dbc.Select reports strings
            "labels": ["Work", "admin"],
            "milestone_id": None,
            "predecessor_ids": [],
        }
        values.update(overrides)
        return values

    def test_creates_task_with_labels(self):
        outcome = execute(self.svc, self.form())
        self.assertTrue(outcome.ok, outcome.message)
        detail = self.svc.tasks.detail(outcome.result)
        self.assertEqual(detail.task.priority, 2)
        self.assertEqual(sorted(lb.name for lb in detail.labels), ["Work", "admin"])
        self.assertIn(str(outcome.result), outcome.message)

    def test_missing_title_is_an_error_outcome(self):
        outcome = execute(self.svc, self.form(title="  "))
        self.assertEqual(outcome.status, "error")
        self.assertIn("Title", outcome.message)

    def test_missing_dates_and_effort(self):
        self.assertIn("date", execute(self.svc, self.form(forecast_end="")).message)
        self.assertIn("effort", execute(self.svc, self.form(estimated_effort_h=None)).message)

    def test_end_before_start(self):
        outcome = execute(self.svc, self.form(forecast_end="2026-10-01"))
        self.assertEqual(outcome.status, "error")

    def test_unknown_kind(self):
        self.assertEqual(execute(self.svc, {"kind": "explode"}).status, "error")


class SaveTaskActionTest(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.task_id = self.make_task(label_names=("work",))

    def form(self, **overrides):
        t = self.task(self.task_id)
        values = {
            "kind": "save_task",
            "task_id": self.task_id,
            "title": t.title,
            "description": t.description or "",
            "forecast_start": t.forecast_start.isoformat(),
            "forecast_end": t.forecast_end.isoformat(),
            "estimated_effort_h": t.estimated_effort_h,
            "remaining_effort_h": t.remaining_effort_h,
            "status": t.status.value,
            "status_reason": "",
            "priority": str(int(t.priority)),
            "labels": ["work"],
            "milestone_id": t.milestone_id,
            "reason": "",
        }
        values.update(overrides)
        return values

    def test_unchanged_form_writes_no_history(self):
        before = len(self.log("task", self.task_id))
        self.assertTrue(execute(self.svc, self.form()).ok)
        self.assertEqual(len(self.log("task", self.task_id)), before)

    def test_edit_with_reason_and_labels(self):
        outcome = execute(
            self.svc, self.form(forecast_end="2026-10-20", reason="Late input", labels=["home"])
        )
        self.assertTrue(outcome.ok, outcome.message)
        edits = self.log("task", self.task_id, "edit")
        self.assertEqual(
            [(e["field"], e["reason"]) for e in edits], [("forecast_end", "Late input")]
        )
        names = [lb.name for lb in self.svc.tasks.detail(self.task_id).labels]
        self.assertEqual(names, ["home"])

    def test_clearing_description(self):
        execute(self.svc, self.form(description="Something"))
        execute(self.svc, self.form(description=""))
        self.assertIsNone(self.task(self.task_id).description)

    def test_R_05_confirmation_round_trip(self):
        execute(self.svc, self.form(status="done"))
        outcome = execute(self.svc, self.form(remaining_effort_h=3))
        self.assertEqual(outcome.status, "confirm")
        self.assertEqual(self.task(self.task_id).status, TaskStatus.DONE)  # nothing written
        # The pending action survives the JSON store and is repeated confirmed.
        pending = json.loads(json.dumps(outcome.action))
        self.assertTrue(execute(self.svc, pending, confirmed=True).ok)
        t = self.task(self.task_id)
        self.assertEqual((t.status, t.remaining_effort_h), (TaskStatus.IN_PROGRESS, 3.0))

    def test_blocked_needs_reason(self):
        outcome = execute(self.svc, self.form(status="blocked"))
        self.assertEqual(outcome.status, "error")
        self.assertTrue(execute(self.svc, self.form(status="blocked", status_reason="Waiting")).ok)
        self.assertEqual(self.comments(self.task_id)[-1]["kind"], "blocked")

    def test_milestone_link_and_unlink(self):
        ms = self.make_milestone()
        execute(self.svc, self.form(milestone_id=ms))
        self.assertEqual(self.task(self.task_id).milestone_id, ms)
        execute(self.svc, self.form(milestone_id=None))
        self.assertIsNone(self.task(self.task_id).milestone_id)

    def test_archived_task_cannot_be_saved(self):
        self.svc.tasks.archive(self.task_id)
        self.assertEqual(execute(self.svc, self.form(title="New")).status, "error")


class SmallActionsTest(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.make_task(title="A")
        self.b = self.make_task(title="B")

    def test_comment(self):
        self.assertTrue(execute(self.svc, {"kind": "add_comment", "task_id": self.a,
                                           "text": "Hello"}).ok)  # fmt: skip
        empty = execute(self.svc, {"kind": "add_comment", "task_id": self.a, "text": " "})
        self.assertEqual(empty.status, "error")

    def test_risk_toggle(self):
        no_reason = execute(self.svc, {"kind": "set_risk", "task_id": self.a, "at_risk": True})
        self.assertEqual(no_reason.status, "error")
        execute(self.svc, {"kind": "set_risk", "task_id": self.a, "at_risk": True,
                           "reason": "Supplier late"})  # fmt: skip
        self.assertTrue(self.task(self.a).at_risk)
        execute(self.svc, {"kind": "set_risk", "task_id": self.a, "at_risk": False})
        self.assertFalse(self.task(self.a).at_risk)

    def test_predecessors(self):
        ok = execute(self.svc, {"kind": "set_predecessors", "task_id": self.b,
                                "predecessor_ids": [self.a]})  # fmt: skip
        self.assertTrue(ok.ok)
        self.assertEqual(self.task(self.b).predecessor_ids, {self.a})
        own = execute(self.svc, {"kind": "set_predecessors", "task_id": self.b,
                                 "predecessor_ids": [self.b]})  # fmt: skip
        self.assertEqual(own.status, "error")

    def test_bulk_review_archive_restore(self):
        self.clock.advance(days=3)
        outcome = execute(self.svc, {"kind": "mark_reviewed", "task_ids": [self.a, self.b]})
        self.assertEqual(outcome.message, "2 tasks marked as reviewed.")
        self.assertEqual(self.task(self.a).last_review_at, self.clock.now())
        execute(self.svc, {"kind": "archive_tasks", "task_ids": [self.a]})
        self.assertTrue(self.task(self.a).is_archived)
        execute(self.svc, {"kind": "restore_tasks", "task_ids": [self.a]})
        self.assertFalse(self.task(self.a).is_archived)

    def test_bulk_needs_selection(self):
        self.assertEqual(execute(self.svc, {"kind": "archive_tasks", "task_ids": []}).status,
                         "error")  # fmt: skip

    def test_rebaseline_needs_reason(self):
        no_reason = execute(self.svc, {"kind": "rebaseline_tasks", "task_ids": [self.a]})
        self.assertEqual(no_reason.status, "error")
        ok = execute(self.svc, {"kind": "rebaseline_tasks", "task_ids": [self.a, self.b],
                                "reason": "New plan"})  # fmt: skip
        self.assertTrue(ok.ok)


class MilestoneActionsTest(ServiceTestCase):
    def test_create_edit_achieve_reopen(self):
        created = execute(self.svc, {"kind": "create_milestone", "name": "Review",
                                     "description": "", "forecast_date": "2026-11-30"})  # fmt: skip
        self.assertTrue(created.ok, created.message)
        ms_id = created.result
        edit = {
            "kind": "update_milestone",
            "milestone_id": ms_id,
            "name": "Review",
            "description": "",
            "forecast_date": "2026-12-04",
            "reason": "Partner late",
        }
        self.assertTrue(execute(self.svc, edit).ok)
        edits = self.log("milestone", ms_id, "edit")
        self.assertEqual([(e["new_value"], e["reason"]) for e in edits],
                         [("2026-12-04", "Partner late")])  # fmt: skip
        achieved = execute(self.svc, {"kind": "achieve_milestone", "milestone_id": ms_id,
                                      "achieved_date": "2026-12-01"})  # fmt: skip
        self.assertTrue(achieved.ok)
        ms = self.svc.milestones.get(ms_id)
        self.assertEqual(
            (ms.status.value, ms.forecast_date.isoformat()), ("achieved", "2026-12-01")
        )
        self.assertEqual(execute(self.svc, {**edit, "forecast_date": "2026-12-24"}).status,
                         "error")  # R-09: reopen first  # fmt: skip
        self.assertTrue(execute(self.svc, {"kind": "reopen_milestone", "milestone_id": ms_id}).ok)

    def test_create_needs_name_and_date(self):
        no_name = execute(self.svc, {"kind": "create_milestone", "name": " ",
                                     "forecast_date": "2026-11-30"})  # fmt: skip
        self.assertEqual(no_name.status, "error")
        no_date = execute(self.svc, {"kind": "create_milestone", "name": "M", "forecast_date": ""})
        self.assertEqual(no_date.status, "error")

    def test_rebaseline_archive_restore(self):
        a, b = self.make_milestone(), self.make_milestone(name="Other")
        later = self.svc.milestones.get(a).forecast_date + timedelta(days=5)
        self.svc.milestones.update(MilestoneUpdate(a, forecast_date=later))
        no_reason = execute(self.svc, {"kind": "rebaseline_milestones", "milestone_ids": [a, b]})
        self.assertEqual(no_reason.status, "error")
        ok = execute(self.svc, {"kind": "rebaseline_milestones", "milestone_ids": [a, b],
                                "reason": "New plan"})  # fmt: skip
        self.assertTrue(ok.ok)
        self.assertEqual(len(self.log("milestone", a, "rebaseline")), 1)
        execute(self.svc, {"kind": "archive_milestones", "milestone_ids": [a, b]})
        self.assertTrue(self.svc.milestones.get(b).is_archived)
        execute(self.svc, {"kind": "restore_milestones", "milestone_ids": [b]})
        self.assertFalse(self.svc.milestones.get(b).is_archived)


class SettingsActionsTest(ServiceTestCase):
    def test_update_settings(self):
        ok = execute(
            self.svc,
            {
                "kind": "update_settings",
                "values": {"weekly_hours": 32, "working_weekdays": [1, 2, 3, 4]},
            },
        )
        self.assertTrue(ok.ok, ok.message)
        self.assertEqual(self.svc.settings.get().working_weekdays, (1, 2, 3, 4))
        bad = execute(
            self.svc,
            {"kind": "update_settings", "values": {"load_green_max": 1.2, "load_amber_max": 1.0}},
        )
        self.assertEqual(bad.status, "error")

    def test_absences_and_holidays(self):
        added = execute(
            self.svc,
            {
                "kind": "add_absence",
                "start_date": "2026-12-21",
                "end_date": "2026-12-31",
                "note": "Vacation",
            },
        )
        self.assertTrue(added.ok)
        reversed_dates = execute(
            self.svc, {"kind": "add_absence", "start_date": "2026-12-21", "end_date": "2026-12-01"}
        )
        self.assertEqual(reversed_dates.status, "error")
        execute(self.svc, {"kind": "remove_absence", "absence_id": added.result})
        self.assertEqual(self.svc.settings.list_absences(), [])
        self.assertTrue(
            execute(self.svc, {"kind": "add_holiday", "date": "2026-12-25", "name": "Christmas"}).ok
        )
        self.assertEqual(
            execute(self.svc, {"kind": "add_holiday", "date": "2026-12-25"}).status, "error"
        )  # duplicate
        self.assertTrue(execute(self.svc, {"kind": "remove_holiday", "date": "2026-12-25"}).ok)

    def test_R_11_delete_asks_and_needs_archive(self):
        task_id = self.make_task()
        active = execute(self.svc, {"kind": "delete_task", "task_id": task_id})
        self.assertEqual(active.status, "error")  # archive first
        self.svc.tasks.archive(task_id)
        ask = execute(self.svc, {"kind": "delete_task", "task_id": task_id})
        self.assertEqual(ask.status, "confirm")
        self.assertTrue(execute(self.svc, ask.action, confirmed=True).ok)
        self.assertEqual(self.query("SELECT count(*) AS n FROM task")[0]["n"], 0)
        ms = self.make_milestone()
        self.svc.milestones.archive(ms)
        ask = execute(self.svc, {"kind": "delete_milestone", "milestone_id": ms})
        self.assertEqual(ask.status, "confirm")
        self.assertTrue(execute(self.svc, ask.action, confirmed=True).ok)


if __name__ == "__main__":
    unittest.main()
