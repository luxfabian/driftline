"""Codec and repository round trips."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pmtool.domain.enums import ChangeKind, CommentKind, EntityType, Priority, TaskStatus
from pmtool.domain.models import ChangeLogEntry
from pmtool.repo import changelog_repo, comment_repo, label_repo, settings_repo, task_repo
from pmtool.repo._codec import encode_log_value, format_timestamp, to_db
from tests.helpers import T0, insert_task, memory_db


class CodecTest(unittest.TestCase):
    def test_to_db(self):
        self.assertEqual(to_db(True), 1)
        self.assertEqual(to_db(TaskStatus.DONE), "done")
        self.assertEqual(to_db(Priority.HIGH), 2)
        self.assertEqual(to_db(date(2026, 1, 2)), "2026-01-02")
        self.assertEqual(to_db(T0), "2026-10-10T09:00:00+02:00")

    def test_log_encoding_per_spec(self):
        self.assertEqual(encode_log_value(3), "3.0")
        self.assertEqual(encode_log_value(2.5), "2.5")
        self.assertEqual(encode_log_value(False), "0")
        self.assertEqual(encode_log_value(TaskStatus.IN_PROGRESS), "in_progress")
        self.assertEqual(encode_log_value(date(2026, 1, 2)), "2026-01-02")
        self.assertIsNone(encode_log_value(None))

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            format_timestamp(datetime(2026, 1, 1))

    def test_timezone_preserved(self):
        winter = datetime(2026, 12, 1, 8, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        self.assertTrue(format_timestamp(winter).endswith("+01:00"))


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()

    def test_task_round_trip_with_labels_and_predecessors(self):
        a = insert_task(self.conn)
        b = insert_task(self.conn, status="in_progress", priority=1, at_risk=1)
        lid = label_repo.get_or_create(self.conn, "Work")
        self.assertEqual(label_repo.get_or_create(self.conn, " WORK "), lid)
        label_repo.set_task_labels(self.conn, b, [lid, lid])
        from pmtool.repo import dependency_repo

        dependency_repo.set_predecessors(self.conn, b, [a])
        t = task_repo.get(self.conn, b)
        self.assertEqual(t.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(t.priority, Priority.CRITICAL)
        self.assertTrue(t.at_risk)
        self.assertEqual(t.forecast_end, date(2026, 10, 16))
        self.assertEqual(t.created_at, T0)
        self.assertEqual((t.label_ids, t.predecessor_ids), (frozenset({lid}), frozenset({a})))
        self.assertEqual([x.id for x in task_repo.list_all(self.conn, False)], [a, b])
        self.assertEqual(dependency_repo.successor_ids(self.conn, a), [b])
        self.assertIsNone(task_repo.get(self.conn, 999))

    def test_update_rejects_unknown_columns(self):
        tid = insert_task(self.conn)
        with self.assertRaises(KeyError):
            task_repo.update_fields(self.conn, tid, {"id": 5})

    def test_changelog_round_trip(self):
        entry = ChangeLogEntry(
            entity_type=EntityType.TASK, entity_id=1, change_kind=ChangeKind.EDIT,
            field="status", old_value="planned", new_value="done", reason=None,
            batch_id="b1", changed_at=T0,
        )  # fmt: skip
        changelog_repo.insert_many(self.conn, [entry])
        [stored] = changelog_repo.list_for_entity(self.conn, EntityType.TASK, 1)
        self.assertEqual(stored.new_value, "done")
        self.assertEqual(stored.changed_at, T0)
        self.assertIsNotNone(stored.id)

    def test_latest_risk_reason(self):
        tid = insert_task(self.conn)
        comment_repo.insert(self.conn, tid, CommentKind.RISK_SET, "old", T0)
        comment_repo.insert(self.conn, tid, CommentKind.NOTE, "note", T0)
        comment_repo.insert(self.conn, tid, CommentKind.RISK_SET, "new", T0)
        self.assertEqual(comment_repo.latest_risk_reasons(self.conn), {tid: "new"})

    def test_settings_round_trip(self):
        settings_repo.update(self.conn, {"working_weekdays": (5, 1), "weekly_hours": 30.0})
        s = settings_repo.get(self.conn)
        self.assertEqual((s.working_weekdays, s.weekly_hours), ((1, 5), 30.0))


if __name__ == "__main__":
    unittest.main()
