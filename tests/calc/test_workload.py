"""calc.workload [WL-03..WL-07] incl. the edge cases of data_model_spec §5."""

from __future__ import annotations

import unittest
from datetime import timedelta

from pmtool.calc.calendar import CalendarContext
from pmtool.calc.workload import (
    NO_LABEL,
    cumulative_curves,
    daily_allocation,
    day_plan,
    due_date,
    horizon_end,
    load_level,
    load_ratio,
    weekly_capacity,
    weekly_load,
)
from pmtool.domain.enums import Priority, TaskStatus
from pmtool.domain.models import Absence, Settings
from tests.factories import TODAY, D, make_task
from tests.helpers import T0

CTX = CalendarContext(Settings())  # 5.2 h per weekday
DAY_CAP = 5.2
SATURDAY = D("2026-10-17")
FAR_END = D("2027-12-31")


def row(df, day):
    return df[df["date"] == day].iloc[0]


class DueDateAndCurvesTest(unittest.TestCase):
    def test_WL_04_overdue_due_today(self):
        self.assertEqual(due_date(make_task(end=D("2026-10-01")), TODAY), TODAY)
        self.assertEqual(due_date(make_task(end=D("2026-10-20")), TODAY), D("2026-10-20"))

    def test_WL_03_cumulative_demand_capacity_shortfall(self):
        tasks = [
            make_task(end=D("2026-10-01"), hours=8),  # overdue -> today
            make_task(end=D("2026-10-14"), hours=12),
            make_task(end=D("2026-11-30"), hours=50),  # after horizon
        ]
        curves = cumulative_curves(tasks, TODAY, D("2026-10-18"), CTX)
        self.assertEqual(list(curves.columns), ["date", "demand_h", "capacity_h", "shortfall_h"])
        self.assertEqual(len(curves), 7)
        self.assertAlmostEqual(row(curves, TODAY)["demand_h"], 8)
        self.assertAlmostEqual(row(curves, TODAY)["capacity_h"], DAY_CAP)
        self.assertAlmostEqual(row(curves, TODAY)["shortfall_h"], 8 - DAY_CAP)
        wed = row(curves, D("2026-10-14"))
        self.assertAlmostEqual(wed["demand_h"], 20)
        self.assertAlmostEqual(wed["shortfall_h"], 20 - 3 * DAY_CAP)
        sun = row(curves, D("2026-10-18"))
        self.assertAlmostEqual(sun["capacity_h"], 5 * DAY_CAP)  # weekend adds nothing
        self.assertAlmostEqual(sun["shortfall_h"], 0)

    def test_WL_05_blocked_counts_done_and_archived_do_not(self):
        tasks = [
            make_task(hours=5, status=TaskStatus.BLOCKED),
            make_task(hours=7, status=TaskStatus.DONE, remaining_effort_h=0),
            make_task(hours=9, archived_at=T0),
            make_task(hours=4, remaining_effort_h=0),
        ]
        curves = cumulative_curves(tasks, TODAY, D("2026-10-16"), CTX)
        self.assertAlmostEqual(curves["demand_h"].iloc[-1], 5)

    def test_edge_today_not_a_working_day(self):
        curves = cumulative_curves([make_task(end=D("2026-10-01"), hours=3)], SATURDAY,
                                   SATURDAY, CTX)  # fmt: skip
        self.assertEqual(curves["capacity_h"].iloc[0], 0)
        self.assertAlmostEqual(curves["demand_h"].iloc[0], 3)

    def test_edge_future_start_counts_in_demand_by_due_date(self):
        t = make_task(start=D("2026-10-26"), end=D("2026-10-28"), hours=6)
        curves = cumulative_curves([t], TODAY, D("2026-10-30"), CTX)
        self.assertAlmostEqual(row(curves, D("2026-10-27"))["demand_h"], 0)
        self.assertAlmostEqual(row(curves, D("2026-10-28"))["demand_h"], 6)


class AllocationTest(unittest.TestCase):
    def _alloc(self, tasks, end=FAR_END, ctx=CTX, today=TODAY):
        return daily_allocation(tasks, today, end, ctx)

    def test_WL_06_allocation_sums_equal_remaining(self):
        tasks = [
            make_task(start=D("2026-10-01"), end=D("2026-10-20"), hours=17.5),
            make_task(
                start=D("2026-10-19"), end=D("2026-11-06"), hours=40, status=TaskStatus.BLOCKED
            ),
            make_task(end=D("2026-10-02"), hours=3),  # overdue
            make_task(start=SATURDAY, end=D("2026-10-18"), hours=2),  # weekend only
        ]
        alloc = self._alloc(tasks)
        sums = alloc.groupby("task_id")["hours"].sum()
        for t in tasks:
            self.assertAlmostEqual(sums[t.id], t.remaining_effort_h)

    def test_WL_06_spread_evenly_over_working_days_from_today(self):
        t = make_task(start=D("2026-10-01"), end=D("2026-10-16"), hours=10)
        alloc = self._alloc([t])
        self.assertEqual(sorted(alloc["date"]), [TODAY + timedelta(i) for i in range(5)])
        self.assertTrue((alloc["hours"] == 2.0).all())

    def test_edge_future_start_allocation_starts_at_start(self):
        t = make_task(start=D("2026-10-21"), end=D("2026-10-22"), hours=6)
        alloc = self._alloc([t])
        self.assertEqual(sorted(alloc["date"]), [D("2026-10-21"), D("2026-10-22")])

    def test_WL_06_no_working_day_goes_to_next_working_day(self):
        weekend = make_task(start=SATURDAY, end=D("2026-10-18"), hours=4)
        overdue = make_task(end=D("2026-10-02"), hours=3)
        alloc = self._alloc([weekend, overdue])
        self.assertEqual(list(alloc[alloc.task_id == weekend.id]["date"]), [D("2026-10-19")])
        self.assertEqual(list(alloc[alloc.task_id == overdue.id]["date"]), [TODAY])
        on_saturday = self._alloc([overdue], today=SATURDAY)
        self.assertEqual(list(on_saturday["date"]), [D("2026-10-19")])

    def test_holidays_and_absences_skipped(self):
        ctx = CalendarContext(
            Settings(),
            holidays=frozenset({D("2026-10-13")}),
            absences=(Absence(1, D("2026-10-14"), D("2026-10-15")),),
        )
        alloc = self._alloc([make_task(hours=4)], ctx=ctx)
        self.assertEqual(sorted(alloc["date"]), [TODAY, D("2026-10-16")])

    def test_no_working_day_within_a_year_keeps_effort(self):
        ctx = CalendarContext(Settings(), absences=(Absence(1, TODAY, TODAY + timedelta(500)),))
        alloc = self._alloc([make_task(hours=4)], ctx=ctx)
        self.assertAlmostEqual(alloc["hours"].sum(), 4)

    def test_horizon_cut(self):
        t = make_task(end=D("2026-10-23"), hours=20)  # 10 working days, 2 h each
        alloc = self._alloc([t], end=D("2026-10-16"))
        self.assertAlmostEqual(alloc["hours"].sum(), 10)

    def test_empty(self):
        self.assertTrue(self._alloc([]).empty)


class WeeklyLoadTest(unittest.TestCase):
    def test_WL_06_group_by_priority_with_capacity(self):
        tasks = [
            make_task(hours=10, priority=Priority.LOW),
            make_task(hours=5, priority=Priority.CRITICAL),
            make_task(start=D("2026-10-19"), end=D("2026-10-23"), hours=8, priority=Priority.LOW),
        ]
        alloc = daily_allocation(tasks, TODAY, D("2026-10-25"), CTX)
        weekly = weekly_load(alloc, tasks, "priority", CTX)
        self.assertEqual(list(weekly.columns), ["week_start", "group", "hours", "capacity_h"])
        self.assertEqual(
            [(w, g, round(h, 6)) for w, g, h, _ in weekly.itertuples(index=False)],
            [(TODAY, "Critical", 5.0), (TODAY, "Low", 10.0), (D("2026-10-19"), "Low", 8.0)],
        )
        self.assertAlmostEqual(weekly["capacity_h"].iloc[0], 5 * DAY_CAP)

    def test_WL_06_multi_label_task_counts_in_each_group(self):
        tasks = [
            make_task(hours=10, label_ids=frozenset({1, 2})),
            make_task(hours=4),
        ]
        alloc = daily_allocation(tasks, TODAY, D("2026-10-18"), CTX)
        weekly = weekly_load(alloc, tasks, "label", CTX, labels={1: "work", 2: "Admin"})
        self.assertEqual(
            [(g, round(h, 6)) for g, h in weekly[["group", "hours"]].itertuples(index=False)],
            [("Admin", 10.0), ("work", 10.0), (NO_LABEL, 4.0)],
        )

    def test_weekly_capacity_full_weeks(self):
        ctx = CalendarContext(Settings(), holidays=frozenset({D("2026-10-21")}))
        cap = weekly_capacity(D("2026-10-14"), D("2026-10-21"), ctx)
        self.assertEqual(list(cap["week_start"]), [TODAY, D("2026-10-19")])
        self.assertAlmostEqual(cap["capacity_h"].iloc[0], 5 * DAY_CAP)
        self.assertAlmostEqual(cap["capacity_h"].iloc[1], 4 * DAY_CAP)

    def test_invalid_group(self):
        alloc = daily_allocation([make_task()], TODAY, D("2026-10-18"), CTX)
        with self.assertRaises(ValueError):
            weekly_load(alloc, [make_task()], "colour", CTX)  # type: ignore[arg-type]

    def test_empty_allocation(self):
        alloc = daily_allocation([], TODAY, D("2026-10-18"), CTX)
        self.assertTrue(weekly_load(alloc, [], "priority", CTX).empty)


class LoadRatioTest(unittest.TestCase):
    def test_WL_07_ratio(self):
        self.assertEqual(horizon_end(TODAY, 4), D("2026-11-08"))
        tasks = [make_task(end=D("2026-11-06"), hours=52), make_task(end=D("2026-11-09"), hours=99)]
        self.assertAlmostEqual(load_ratio(tasks, TODAY, 4, CTX), 52 / (20 * DAY_CAP))

    def test_edge_zero_capacity_is_na(self):
        ctx = CalendarContext(Settings(), absences=(Absence(1, TODAY, TODAY + timedelta(30)),))
        self.assertIsNone(load_ratio([make_task()], TODAY, 2, ctx))
        self.assertEqual(load_level(None, Settings()), "na")

    def test_WL_07_traffic_light_boundaries(self):
        s = Settings()
        self.assertEqual(load_level(0.8499, s), "green")
        self.assertEqual(load_level(0.85, s), "amber")
        self.assertEqual(load_level(1.0, s), "amber")
        self.assertEqual(load_level(1.0001, s), "red")
        custom = Settings(load_green_max=0.5, load_amber_max=0.7)
        self.assertEqual(load_level(0.6, custom), "amber")


class DayPlanTest(unittest.TestCase):
    """Dashboard "Your day": what the WL-06 spreading puts on the next working day."""

    def test_hours_match_daily_allocation(self):
        t = make_task(start=TODAY, end=D("2026-10-16"), hours=10.0)  # Mon-Fri: 2 h a day
        plan = day_plan([t], TODAY, CTX)
        self.assertEqual(plan.day, TODAY)
        self.assertEqual(plan.capacity_h, DAY_CAP)
        self.assertEqual([(i.task_id, i.hours) for i in plan.items], [(t.id, 2.0)])

    def test_weekend_plans_next_monday_and_overdue_lands_there(self):
        late = make_task(start=D("2026-10-05"), end=D("2026-10-09"), hours=3.0)
        plan = day_plan([late], SATURDAY, CTX)
        self.assertEqual(plan.day, D("2026-10-19"))
        (item,) = plan.items
        self.assertTrue(item.overdue)
        self.assertEqual((item.hours, item.due), (3.0, SATURDAY))  # WL-04: due "today"

    def test_focus_order_priority_then_due_then_at_risk(self):
        low = make_task(priority=Priority.LOW, start=TODAY, end=TODAY, hours=1.0)
        high_later = make_task(priority=Priority.HIGH, start=TODAY, end=D("2026-10-14"))
        high_soon = make_task(priority=Priority.HIGH, start=TODAY, end=TODAY, hours=1.0)
        high_soon_risk = make_task(
            priority=Priority.HIGH, start=TODAY, end=TODAY, hours=1.0, at_risk=True
        )
        blocked = make_task(
            priority=Priority.CRITICAL, status=TaskStatus.BLOCKED, start=TODAY, end=TODAY, hours=1.0
        )
        plan = day_plan([low, high_later, high_soon, high_soon_risk, blocked], TODAY, CTX)
        self.assertEqual(
            [i.task_id for i in plan.items],
            [high_soon_risk.id, high_soon.id, high_later.id, low.id, blocked.id],
        )
        self.assertTrue(plan.items[-1].blocked)
        self.assertFalse(plan.items[-1].within_capacity)  # blocked work is not "workable"

    def test_capacity_cut(self):
        a = make_task(priority=Priority.CRITICAL, start=TODAY, end=TODAY, hours=4.0)
        b = make_task(priority=Priority.HIGH, start=TODAY, end=TODAY, hours=3.0)
        c = make_task(priority=Priority.LOW, start=TODAY, end=TODAY, hours=1.0)
        plan = day_plan([a, b, c], TODAY, CTX)
        # a (0-4 h) and b (4-7 h) start within 5.2 h; c starts at 7 h, beyond capacity
        self.assertEqual([i.within_capacity for i in plan.items], [True, True, False])
        self.assertAlmostEqual(plan.planned_h, 8.0)
        self.assertAlmostEqual(plan.workable_h, 8.0)

    def test_future_and_done_tasks_are_not_on_the_day(self):
        future = make_task(start=D("2026-10-20"), end=D("2026-10-23"))
        done = make_task(status=TaskStatus.DONE, remaining_effort_h=0.0)
        self.assertEqual(day_plan([future, done], TODAY, CTX).items, ())

    def test_no_working_day_within_a_year(self):
        always_away = CalendarContext(Settings(), absences=(Absence(1, TODAY, FAR_END),))
        plan = day_plan([make_task()], TODAY, always_away)
        self.assertIsNone(plan.day)
        self.assertEqual(plan.items, ())


if __name__ == "__main__":
    unittest.main()
