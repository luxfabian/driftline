"""TaskService: one named test per rule (architecture §11)."""

from __future__ import annotations

import unittest

from pmtool.domain.commands import UNLINK, TaskUpdate
from pmtool.domain.enums import Priority, TaskStatus
from pmtool.errors import ConfirmationRequired, NotFound, ValidationError
from tests.helpers import TS
from tests.services.base import D, ServiceTestCase


class R01CreateTask(ServiceTestCase):
    def test_R_01_baseline_equals_forecast_and_remaining_equals_estimate(self):
        t = self.task(self.make_task())
        self.assertEqual((t.baseline_start, t.baseline_end), (t.forecast_start, t.forecast_end))
        self.assertEqual(t.remaining_effort_h, t.estimated_effort_h)
        self.assertEqual(t.status, TaskStatus.PLANNED)
        self.assertEqual(t.priority, Priority.MEDIUM)
        self.assertEqual(t.last_review_at, t.created_at)
        self.assertEqual(t.created_at, self.clock.now())

    def test_R_01_create_rows_for_every_logged_field(self):
        tid = self.make_task()
        rows = self.log("task", tid)
        self.assertEqual(
            [r["field"] for r in rows],
            ["baseline_start", "baseline_end", "forecast_start", "forecast_end",
             "remaining_effort_h", "status"],
        )  # fmt: skip
        self.assertTrue(all(r["change_kind"] == "create" for r in rows))
        self.assertTrue(all(r["old_value"] is None for r in rows))
        self.assertEqual(len({r["batch_id"] for r in rows}), 1)
        by_field = {r["field"]: r["new_value"] for r in rows}
        self.assertEqual(by_field["forecast_end"], "2026-10-16")
        self.assertEqual(by_field["remaining_effort_h"], "10.0")
        self.assertEqual(by_field["status"], "planned")
        self.assertEqual(rows[0]["changed_at"], TS)

    def test_create_with_labels_predecessors_and_milestone(self):
        ms = self.make_milestone()
        a = self.make_task()
        b = self.make_task(label_names=("Work", "work ", "Admin"), predecessor_ids=(a,),
                           milestone_id=ms, priority=Priority.HIGH)  # fmt: skip
        detail = self.svc.tasks.detail(b)
        self.assertEqual(sorted(lbl.name for lbl in detail.labels), ["Admin", "Work"])
        self.assertEqual([t.id for t in detail.predecessors], [a])
        self.assertEqual(detail.task.milestone_id, ms)
        self.assertEqual(detail.task.priority, Priority.HIGH)

    def test_create_rejects_empty_title_and_unknown_milestone(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make_task(title="  ")
        self.assertEqual(ctx.exception.code, "DAT-01")
        with self.assertRaises(NotFound):
            self.make_task(milestone_id=99)
        self.assertEqual(self.query("SELECT count(*) AS n FROM task")[0]["n"], 0)


class R03EditLogging(ServiceTestCase):
    def test_R_03_only_changed_logged_fields_are_logged(self):
        tid = self.make_task()
        self.clock.advance(days=1)
        self.svc.tasks.update(
            TaskUpdate(tid, title="New title", forecast_end=D("2026-10-20"),
                       forecast_start=D("2026-10-12"), reason="Waiting for input")
        )  # fmt: skip
        rows = self.log("task", tid, "edit")
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["field"], rows[0]["old_value"], rows[0]["new_value"], rows[0]["reason"]),
            ("forecast_end", "2026-10-16", "2026-10-20", "Waiting for input"),
        )
        self.assertEqual(self.task(tid).title, "New title")

    def test_R_03_no_change_writes_nothing(self):
        tid = self.make_task()
        before = self.task(tid)
        self.clock.advance(days=1)
        self.svc.tasks.update(TaskUpdate(tid, title="Write report", status=TaskStatus.PLANNED))
        self.assertEqual(self.log("task", tid, "edit"), [])
        self.assertEqual(self.task(tid), before)

    def test_R_03_unlogged_fields_change_without_log_rows(self):
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, priority=Priority.CRITICAL, estimated_effort_h=12))
        self.assertEqual(self.log("task", tid, "edit"), [])
        t = self.task(tid)
        self.assertEqual((t.priority, t.estimated_effort_h, t.remaining_effort_h),
                         (Priority.CRITICAL, 12.0, 10.0))  # fmt: skip

    def test_milestone_link_and_unlink(self):
        ms = self.make_milestone()
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, milestone_id=ms))
        self.assertEqual(self.task(tid).milestone_id, ms)
        self.svc.tasks.update(TaskUpdate(tid, milestone_id=UNLINK))
        self.assertIsNone(self.task(tid).milestone_id)


class R04R05DoneAndRemaining(ServiceTestCase):
    def test_R_04_done_sets_remaining_to_zero_and_logs_it(self):
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.DONE, remaining_effort_h=4))
        t = self.task(tid)
        self.assertEqual((t.status, t.remaining_effort_h), (TaskStatus.DONE, 0.0))
        fields = {r["field"]: r["new_value"] for r in self.log("task", tid, "edit")}
        self.assertEqual(fields, {"status": "done", "remaining_effort_h": "0.0"})

    def test_R_05_reopening_needs_confirmation_and_writes_nothing(self):
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.DONE))
        n_rows = len(self.log("task", tid))
        with self.assertRaises(ConfirmationRequired) as ctx:
            self.svc.tasks.update(TaskUpdate(tid, remaining_effort_h=3))
        self.assertEqual(ctx.exception.code, "R-05")
        self.assertEqual(self.task(tid).status, TaskStatus.DONE)
        self.assertEqual(len(self.log("task", tid)), n_rows)

    def test_R_05_confirmed_reopens_as_in_progress(self):
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.DONE))
        # A full form resends the unchanged status "done": still counts as reopening.
        self.svc.tasks.update(
            TaskUpdate(tid, status=TaskStatus.DONE, remaining_effort_h=3), confirmed=True
        )
        t = self.task(tid)
        self.assertEqual((t.status, t.remaining_effort_h), (TaskStatus.IN_PROGRESS, 3.0))

    def test_R_05_explicit_new_status_needs_no_confirmation(self):
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.DONE))
        self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.PLANNED, remaining_effort_h=2))
        self.assertEqual(self.task(tid).status, TaskStatus.PLANNED)


class R06RiskAndBlocked(ServiceTestCase):
    def test_R_06_at_risk_requires_reason_and_stores_comment(self):
        tid = self.make_task()
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.set_at_risk(tid, True, "  ")
        self.assertEqual(ctx.exception.code, "VAL-06")
        self.svc.tasks.set_at_risk(tid, True, "Supplier late")
        detail = self.svc.tasks.detail(tid)
        self.assertTrue(detail.task.at_risk)
        self.assertEqual(detail.risk_reason, "Supplier late")
        self.assertEqual([(c["kind"], c["text"]) for c in self.comments(tid)],
                         [("risk_set", "Supplier late")])  # fmt: skip

    def test_R_06_new_reason_replaces_current_reason(self):
        tid = self.make_task()
        self.svc.tasks.set_at_risk(tid, True, "First")
        self.svc.tasks.set_at_risk(tid, True, "Second")
        self.assertEqual(self.svc.tasks.detail(tid).risk_reason, "Second")

    def test_R_06_clearing_inserts_risk_cleared(self):
        tid = self.make_task()
        self.svc.tasks.set_at_risk(tid, True, "Supplier late")
        self.svc.tasks.set_at_risk(tid, False)
        detail = self.svc.tasks.detail(tid)
        self.assertFalse(detail.task.at_risk)
        self.assertIsNone(detail.risk_reason)
        self.assertEqual(self.comments(tid)[-1]["kind"], "risk_cleared")
        self.svc.tasks.set_at_risk(tid, False)  # clearing again: no new comment
        self.assertEqual(len(self.comments(tid)), 2)

    def test_R_06_blocked_requires_reason(self):
        tid = self.make_task()
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.BLOCKED))
        self.assertEqual(ctx.exception.code, "VAL-06")
        self.assertEqual(self.task(tid).status, TaskStatus.PLANNED)
        self.svc.tasks.update(
            TaskUpdate(tid, status=TaskStatus.BLOCKED, status_reason="No access to lab")
        )
        self.assertEqual(self.task(tid).status, TaskStatus.BLOCKED)
        self.assertEqual([(c["kind"], c["text"]) for c in self.comments(tid)],
                         [("blocked", "No access to lab")])  # fmt: skip


class R07Review(ServiceTestCase):
    def test_R_07_review_fields_update_last_review(self):
        tid = self.make_task()
        for cmd in (
            TaskUpdate(tid, remaining_effort_h=7),
            TaskUpdate(tid, status=TaskStatus.IN_PROGRESS),
            TaskUpdate(tid, forecast_end=D("2026-10-23")),
            TaskUpdate(tid, forecast_start=D("2026-10-13")),
        ):
            self.clock.advance(days=1)
            self.svc.tasks.update(cmd)
            self.assertEqual(self.task(tid).last_review_at, self.clock.now(), cmd)

    def test_R_07_other_fields_do_not_count_as_review(self):
        tid = self.make_task()
        self.clock.advance(days=1)
        self.svc.tasks.update(TaskUpdate(tid, title="Other", priority=Priority.LOW))
        t = self.task(tid)
        self.assertEqual(t.last_review_at, t.created_at)
        self.assertEqual(t.updated_at, self.clock.now())

    def test_R_07_mark_reviewed(self):
        tid = self.make_task()
        self.clock.advance(days=3)
        self.svc.tasks.mark_reviewed(tid)
        self.assertEqual(self.task(tid).last_review_at, self.clock.now())
        self.assertEqual(self.log("task", tid, "edit"), [])


class R10R11ArchiveDelete(ServiceTestCase):
    def test_R_10_archive_and_restore_keep_links_and_log(self):
        ms = self.make_milestone()
        a = self.make_task()
        b = self.make_task(label_names=("x",), predecessor_ids=(a,), milestone_id=ms)
        self.svc.tasks.archive(b)
        archived = self.task(b)
        self.assertEqual(archived.archived_at, self.clock.now())
        self.assertEqual((archived.label_ids != frozenset(), archived.predecessor_ids),
                         (True, frozenset({a})))  # fmt: skip
        self.assertNotIn(b, [t.id for t in self.svc.snapshot.load().tasks])
        self.svc.tasks.archive(b)  # idempotent
        self.svc.tasks.restore(b)
        self.assertIsNone(self.task(b).archived_at)
        kinds = [r["change_kind"] for r in self.log("task", b) if r["field"] is None]
        self.assertEqual(kinds, ["archive", "restore"])

    def test_R_10_archived_task_cannot_be_edited(self):
        tid = self.make_task()
        self.svc.tasks.archive(tid)
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.update(TaskUpdate(tid, title="x"))
        self.assertEqual(ctx.exception.code, "DAT-08")

    def test_R_11_delete_requires_archive_and_confirmation(self):
        a = self.make_task()
        b = self.make_task(predecessor_ids=(a,), label_names=("x",))
        self.svc.tasks.add_comment(a, "note")
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.delete_permanently(a, confirmed=True)
        self.assertEqual(ctx.exception.code, "R-11")
        self.svc.tasks.archive(a)
        with self.assertRaises(ConfirmationRequired):
            self.svc.tasks.delete_permanently(a)
        self.assertEqual(len(self.query("SELECT * FROM task")), 2)
        self.svc.tasks.delete_permanently(a, confirmed=True)
        self.assertEqual([r["id"] for r in self.query("SELECT id FROM task")], [b])
        self.assertEqual(self.log("task", a), [])
        self.assertEqual(self.comments(a), [])
        self.assertEqual(self.task(b).predecessor_ids, frozenset())
        self.assertTrue(self.log("task", b))  # other histories untouched


class R12Labels(ServiceTestCase):
    def test_R_12_labels_reused_case_insensitively(self):
        a = self.make_task(label_names=("Work",))
        b = self.make_task()
        self.svc.tasks.set_labels(b, ["  WORK", "home", ""])
        labels = self.query("SELECT name, name_key FROM label ORDER BY name_key")
        self.assertEqual(labels, [{"name": "home", "name_key": "home"},
                                  {"name": "Work", "name_key": "work"}])  # fmt: skip
        self.assertEqual(self.task(a).label_ids & self.task(b).label_ids, self.task(a).label_ids)
        self.svc.tasks.set_labels(b, [])
        self.assertEqual(self.task(b).label_ids, frozenset())


class R13Dependencies(ServiceTestCase):
    def test_R_13_predecessors_set_and_successors_shown(self):
        a, b, c = self.make_task(), self.make_task(), self.make_task()
        self.svc.tasks.set_predecessors(c, [a, b])
        self.assertEqual(self.task(c).predecessor_ids, frozenset({a, b}))
        self.assertEqual([t.id for t in self.svc.tasks.detail(a).successors], [c])

    def test_R_13_cycles_are_allowed(self):
        a, b = self.make_task(), self.make_task()
        self.svc.tasks.set_predecessors(b, [a])
        self.svc.tasks.set_predecessors(a, [b])
        self.assertEqual(self.task(a).predecessor_ids, frozenset({b}))

    def test_R_13_dependencies_never_move_dates(self):
        a = self.make_task(forecast_end=D("2026-10-30"))
        b = self.make_task()
        before = self.task(b)
        self.svc.tasks.set_predecessors(b, [a])
        after = self.task(b)
        self.assertEqual((after.forecast_start, after.forecast_end),
                         (before.forecast_start, before.forecast_end))  # fmt: skip


class R14UpdatedAt(ServiceTestCase):
    def test_R_14_every_change_sets_updated_at(self):
        tid = self.make_task()
        actions = [
            lambda: self.svc.tasks.update(TaskUpdate(tid, description="d")),
            lambda: self.svc.tasks.set_labels(tid, ["a"]),
            lambda: self.svc.tasks.set_at_risk(tid, True, "r"),
            lambda: self.svc.tasks.archive(tid),
            lambda: self.svc.tasks.restore(tid),
        ]
        for action in actions:
            self.clock.advance(hours=1)
            action()
            self.assertEqual(self.task(tid).updated_at, self.clock.now())


class ValidationRules(ServiceTestCase):
    def test_VAL_01_end_before_start(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make_task(forecast_start=D("2026-10-16"), forecast_end=D("2026-10-12"))
        self.assertEqual(ctx.exception.code, "VAL-01")
        tid = self.make_task()
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.update(TaskUpdate(tid, forecast_end=D("2026-10-01")))
        self.assertEqual(ctx.exception.code, "VAL-01")
        self.assertEqual(self.task(tid).forecast_end, D("2026-10-16"))

    def test_VAL_01_same_day_is_allowed(self):
        self.make_task(forecast_start=D("2026-10-12"), forecast_end=D("2026-10-12"))

    def test_VAL_02_effort_must_be_non_negative_number(self):
        for bad in (-1, float("nan"), float("inf"), "abc"):
            with self.assertRaises(ValidationError) as ctx:
                self.make_task(estimated_effort_h=bad)
            self.assertEqual(ctx.exception.code, "VAL-02", bad)
        tid = self.make_task()
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.update(TaskUpdate(tid, remaining_effort_h=-2))
        self.assertEqual(ctx.exception.code, "VAL-02")
        self.make_task(estimated_effort_h=0)

    def test_VAL_03_done_and_remaining_consistent(self):
        tid = self.make_task()
        self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.DONE))
        self.assertEqual(self.task(tid).remaining_effort_h, 0.0)
        with self.assertRaises(ConfirmationRequired):
            self.svc.tasks.update(TaskUpdate(tid, remaining_effort_h=1))

    def test_VAL_04_remaining_may_exceed_estimate(self):
        tid = self.make_task(estimated_effort_h=10)
        self.svc.tasks.update(TaskUpdate(tid, remaining_effort_h=15))
        t = self.task(tid)
        self.assertEqual((t.estimated_effort_h, t.remaining_effort_h), (10.0, 15.0))

    def test_VAL_05_predecessors_must_exist_and_not_be_self(self):
        tid = self.make_task()
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.set_predecessors(tid, [tid])
        self.assertEqual(ctx.exception.code, "VAL-05")
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.set_predecessors(tid, [999])
        self.assertEqual(ctx.exception.code, "VAL-05")
        with self.assertRaises(ValidationError) as ctx:
            self.make_task(predecessor_ids=(999,))
        self.assertEqual(ctx.exception.code, "VAL-05")

    def test_VAL_06_reason_required(self):
        tid = self.make_task()
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.set_at_risk(tid, True, None)
        self.assertEqual(ctx.exception.code, "VAL-06")
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.update(TaskUpdate(tid, status=TaskStatus.BLOCKED, status_reason=" "))
        self.assertEqual(ctx.exception.code, "VAL-06")
        self.assertEqual(self.comments(tid), [])


class CommentsAndDetail(ServiceTestCase):
    def test_comments_newest_first_and_not_empty(self):
        tid = self.make_task()
        self.svc.tasks.add_comment(tid, "first")
        self.clock.advance(minutes=5)
        self.svc.tasks.add_comment(tid, "second")
        texts = [c.text for c in self.svc.tasks.detail(tid).comments]
        self.assertEqual(texts, ["second", "first"])
        with self.assertRaises(ValidationError) as ctx:
            self.svc.tasks.add_comment(tid, "   ")
        self.assertEqual(ctx.exception.code, "FUN-03")

    def test_detail_history_oldest_first(self):
        tid = self.make_task()
        self.clock.advance(days=1)
        self.svc.tasks.update(TaskUpdate(tid, remaining_effort_h=4))
        history = self.svc.tasks.detail(tid).history
        self.assertEqual(history[0].change_kind, "create")
        self.assertEqual(history[-1].field, "remaining_effort_h")

    def test_unknown_task(self):
        with self.assertRaises(NotFound):
            self.svc.tasks.detail(42)
        with self.assertRaises(NotFound):
            self.svc.tasks.update(TaskUpdate(42, title="x"))


if __name__ == "__main__":
    unittest.main()
