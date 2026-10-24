"""domain.filters [FUN-09, FUN-10]."""

from __future__ import annotations

import unittest

from driftline.domain.enums import Priority, TaskStatus
from driftline.domain.filters import Filter, apply_filter, describe
from tests.factories import D, make_task
from tests.helpers import T0

LABELS = {1: "work", 2: "Admin", 3: "home"}
MILESTONES = {10: "Design review"}


def ids(tasks):
    return [t.id for t in tasks]


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.planned = make_task(label_ids=frozenset({1, 2}), priority=Priority.HIGH)
        self.blocked = make_task(label_ids=frozenset({1}), status=TaskStatus.BLOCKED, at_risk=True)
        self.done = make_task(status=TaskStatus.DONE, remaining_effort_h=0, milestone_id=10)
        self.archived = make_task(archived_at=T0)
        self.all = [self.planned, self.blocked, self.done, self.archived]

    def test_FUN_09_default_is_open_active_tasks(self):
        self.assertEqual(ids(apply_filter(self.all, Filter())), [self.planned.id, self.blocked.id])

    def test_FUN_09_labels_any_and_all(self):
        any_ = Filter(labels=frozenset({2, 3}))
        all_ = Filter(labels=frozenset({1, 2}), label_mode="all")
        self.assertEqual(ids(apply_filter(self.all, any_)), [self.planned.id])
        self.assertEqual(ids(apply_filter(self.all, all_)), [self.planned.id])
        self.assertEqual(
            ids(apply_filter(self.all, Filter(labels=frozenset({1})))),
            [self.planned.id, self.blocked.id],
        )

    def test_FUN_09_priority_status_risk_milestone(self):
        self.assertEqual(ids(apply_filter(self.all, Filter(priorities=frozenset({2})))),
                         [self.planned.id])  # fmt: skip
        self.assertEqual(ids(apply_filter(self.all, Filter(at_risk_only=True))), [self.blocked.id])
        done_filter = Filter(statuses=frozenset({TaskStatus.DONE}), milestone_ids=frozenset({10}))
        self.assertEqual(ids(apply_filter(self.all, done_filter)), [self.done.id])
        self.assertEqual(len(apply_filter(self.all, Filter(statuses=frozenset()))), 3)

    def test_FUN_09_date_range_overlap(self):
        t = make_task(start=D("2026-10-12"), end=D("2026-10-16"))
        cases = {
            (D("2026-10-16"), None): True,  # touches end
            (D("2026-10-17"), None): False,
            (None, D("2026-10-12")): True,  # touches start
            (None, D("2026-10-11")): False,
            (D("2026-10-13"), D("2026-10-14")): True,  # inside
            (D("2026-10-01"), D("2026-10-31")): True,  # around
        }
        for (start, end), expected in cases.items():
            result = apply_filter([t], Filter(date_from=start, date_to=end))
            self.assertEqual(bool(result), expected, (start, end))

    def test_include_archived(self):
        f = Filter(include_archived=True)
        self.assertIn(self.archived.id, ids(apply_filter(self.all, f)))

    def test_invalid_label_mode(self):
        with self.assertRaises(ValueError):
            Filter(label_mode="some")  # type: ignore[arg-type]


class DescribeTest(unittest.TestCase):
    def test_FUN_10_default_says_no_filter(self):
        self.assertEqual(describe(Filter(), LABELS, MILESTONES), "No filter")

    def test_FUN_10_full_description(self):
        f = Filter(
            labels=frozenset({1, 2}),
            priorities=frozenset({1, 2, 4}),
            statuses=frozenset({TaskStatus.DONE, TaskStatus.PLANNED}),
            at_risk_only=True,
            milestone_ids=frozenset({10}),
            date_from=D("2026-10-01"),
            include_archived=True,
        )
        self.assertEqual(
            describe(f, LABELS, MILESTONES),
            "Labels: Admin, work (any) · Priority: 1–2, 4 · Status: Planned, Done · "
            "At risk only · Milestones: Design review · Dates: 2026-10-01 – … · incl. archived",
        )

    def test_status_all(self):
        self.assertEqual(describe(Filter(statuses=frozenset(TaskStatus)), {}, {}), "Status: all")
        self.assertEqual(describe(Filter(statuses=frozenset()), {}, {}), "Status: all")

    def test_unknown_ids_still_described(self):
        self.assertEqual(describe(Filter(labels=frozenset({99})), {}, {}), "Labels: #99 (any)")


if __name__ == "__main__":
    unittest.main()
