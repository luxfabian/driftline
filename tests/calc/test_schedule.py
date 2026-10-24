"""calc.schedule [SCH-03..SCH-06, FUN-07, R-13]."""

from __future__ import annotations

import unittest

from driftline.calc.schedule import (
    dependency_cycles,
    dependency_warnings,
    milestone_task_warnings,
    milestone_variance,
    mta_series,
    task_variance,
    top_delayed,
)
from driftline.domain.enums import MilestoneStatus, TaskStatus
from tests.factories import TODAY, D, forecast_entry, make_milestone, make_task
from tests.helpers import T0


class VarianceTest(unittest.TestCase):
    def test_SCH_03_task_variance_sign(self):
        t = make_task(forecast_start=D("2026-10-14"), forecast_end=D("2026-10-13"))
        v = task_variance(t)  # baseline 10-12 .. 10-16
        self.assertEqual((v.start_d, v.end_d), (2, -3))

    def test_SCH_03_milestone_variance(self):
        m = make_milestone(day=D("2026-11-30"), forecast_date=D("2026-12-07"))
        self.assertEqual(milestone_variance(m), 7)


class DependencyTest(unittest.TestCase):
    def test_FUN_07_warning_when_start_before_predecessor_end(self):
        p = make_task(end=D("2026-10-16"))
        late = make_task(
            start=D("2026-10-15"), end=D("2026-10-20"), predecessor_ids=frozenset({p.id})
        )
        same_day = make_task(
            start=D("2026-10-16"), end=D("2026-10-20"), predecessor_ids=frozenset({p.id})
        )
        self.assertEqual(dependency_warnings([p, late, same_day]), {late.id: [p.id]})

    def test_FUN_07_ignores_archived_missing_and_done(self):
        p = make_task(end=D("2026-10-30"), archived_at=T0)
        missing_id = 9999
        a = make_task(predecessor_ids=frozenset({p.id, missing_id}))
        q = make_task(end=D("2026-10-30"))
        done = make_task(
            status=TaskStatus.DONE, remaining_effort_h=0, predecessor_ids=frozenset({q.id})
        )
        self.assertEqual(dependency_warnings([p, a, q, done]), {})

    def test_R_13_cycles_found(self):
        a, b, c, d = (make_task() for _ in range(4))
        a = make_task(id=a.id, predecessor_ids=frozenset({c.id}))
        b = make_task(id=b.id, predecessor_ids=frozenset({a.id}))
        c = make_task(id=c.id, predecessor_ids=frozenset({b.id}))
        d = make_task(id=d.id, predecessor_ids=frozenset({a.id}))
        self.assertEqual(dependency_cycles([a, b, c, d]), [sorted([a.id, b.id, c.id])])

    def test_no_cycles_and_long_chain(self):
        chain = [make_task(id=1_000_000)]
        for i in range(1, 3000):
            chain.append(
                make_task(id=1_000_000 + i, predecessor_ids=frozenset({1_000_000 + i - 1}))
            )
        self.assertEqual(dependency_cycles(chain), [])
        looped = [*chain[1:], make_task(id=1_000_000, predecessor_ids=frozenset({1_002_999}))]
        self.assertEqual(len(dependency_cycles(looped)[0]), 3000)


class MilestoneWarningTest(unittest.TestCase):
    def test_SCH_05_warn_when_linked_open_task_ends_later(self):
        m = make_milestone(day=D("2026-10-20"))
        ok = make_milestone(day=D("2026-10-30"))
        tasks = [
            make_task(milestone_id=m.id, end=D("2026-10-22")),
            make_task(milestone_id=m.id, end=D("2026-10-25"), status=TaskStatus.DONE,
                      remaining_effort_h=0),
            make_task(milestone_id=ok.id, end=D("2026-10-30")),
        ]  # fmt: skip
        self.assertEqual(milestone_task_warnings([m, ok], tasks), {m.id: D("2026-10-22")})

    def test_SCH_05_achieved_milestone_not_warned(self):
        m = make_milestone(day=D("2026-10-20"), status=MilestoneStatus.ACHIEVED,
                           achieved_date=D("2026-10-20"))  # fmt: skip
        tasks = [make_task(milestone_id=m.id, end=D("2026-10-22"))]
        self.assertEqual(milestone_task_warnings([m], tasks), {})


class MtaTest(unittest.TestCase):
    def test_SCH_04_creation_only_is_carried_to_today(self):
        entries = [forecast_entry(1, D("2026-10-01"), "2026-11-30")]
        self.assertEqual(
            mta_series(entries, TODAY),
            [(D("2026-10-01"), D("2026-11-30")), (TODAY, D("2026-11-30"))],
        )

    def test_SCH_04_staircase_and_same_day_keeps_last(self):
        entries = [
            forecast_entry(1, D("2026-10-01"), "2026-11-30"),
            forecast_entry(1, D("2026-10-05"), "2026-12-04", hour=9),
            forecast_entry(1, D("2026-10-05"), "2026-12-07", hour=15),
            forecast_entry(1, D("2026-10-08"), "2026-12-07"),  # unchanged value
        ]
        self.assertEqual(
            mta_series(entries, TODAY),
            [
                (D("2026-10-01"), D("2026-11-30")),
                (D("2026-10-05"), D("2026-11-30")),  # carried forward until the change
                (D("2026-10-05"), D("2026-12-07")),
                (D("2026-10-08"), D("2026-12-07")),
                (TODAY, D("2026-12-07")),
            ],
        )

    def test_SCH_04_achieved_milestone_ends_at_until(self):
        entries = [
            forecast_entry(1, D("2026-10-01"), "2026-10-09"),
            forecast_entry(1, D("2026-10-09"), "2026-10-09"),  # achieved on the day
        ]
        series = mta_series(entries, TODAY, until=D("2026-10-09"))
        self.assertEqual(series[-1], (D("2026-10-09"), D("2026-10-09")))  # on the diagonal

    def test_mta_empty(self):
        self.assertEqual(mta_series([], TODAY), [])


class TopDelayedTest(unittest.TestCase):
    def test_SCH_06_sorted_open_late_items_only(self):
        t3 = make_task(title="three", forecast_end=D("2026-10-19"))  # +3
        t10 = make_task(title="ten", forecast_end=D("2026-10-26"))  # +10
        early = make_task(forecast_end=D("2026-10-14"))
        done = make_task(forecast_end=D("2026-10-30"), status=TaskStatus.DONE, remaining_effort_h=0)
        m5 = make_milestone(day=D("2026-11-30"), forecast_date=D("2026-12-05"))
        achieved = make_milestone(
            day=D("2026-10-01"),
            forecast_date=D("2026-10-30"),
            status=MilestoneStatus.ACHIEVED,
            achieved_date=D("2026-10-30"),
        )
        items = top_delayed([t3, t10, early, done], [m5, achieved], n=10)
        self.assertEqual([(i.kind, i.variance_d) for i in items],
                         [("task", 10), ("milestone", 5), ("task", 3)])  # fmt: skip
        self.assertEqual(len(top_delayed([t3, t10], [m5], n=2)), 2)
        self.assertEqual(top_delayed([t3], [], n=0), [])


if __name__ == "__main__":
    unittest.main()
