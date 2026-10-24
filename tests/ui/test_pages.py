"""Pure page functions of the phase 5 views (no browser)."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta

from driftline.domain.enums import MilestoneStatus, Priority, TaskStatus
from driftline.domain.filters import Filter
from driftline.domain.models import Label, Settings, Snapshot
from driftline.ui import charts
from driftline.ui.pages.dashboard import dashboard_data, day_section, day_title, due_text
from driftline.ui.pages.milestones import dialog_action, milestone_rows, mta_figure
from driftline.ui.pages.timeline import (
    clicked_task_id,
    period_label,
    shift,
    timeline_figure,
    window,
)
from driftline.ui.pages.workload import colored_labels, workload_data, workload_filter
from tests.factories import TODAY, D, forecast_entry, make_milestone, make_task
from tests.helpers import T0


def snapshot(tasks=(), milestones=(), labels=(), forecast_log=None, settings=None):
    return Snapshot(
        tasks=tuple(tasks),
        milestones=tuple(milestones),
        labels=tuple(labels),
        settings=settings or Settings(),
        absences=(),
        holidays=frozenset(),
        milestone_forecast_log=forecast_log or {},
    )


class DashboardDataTest(unittest.TestCase):
    def test_counts_follow_filter(self):
        late = make_task(start=D("2026-10-01"), end=D("2026-10-09"), priority=Priority.HIGH)
        risky = make_task(at_risk=True)
        blocked = make_task(status=TaskStatus.BLOCKED)
        snap = snapshot([late, risky, blocked])
        now = T0 + timedelta(days=20)  # everything is stale by then
        data = dashboard_data(snap, Filter(), TODAY, now)
        self.assertEqual((data.overdue, data.at_risk, data.blocked, data.stale), (1, 1, 1, 3))
        only_high = dashboard_data(snap, Filter(priorities=frozenset({2})), TODAY, now)
        self.assertEqual((only_high.overdue, only_high.at_risk, only_high.stale), (1, 0, 1))

    def test_load_ratio_uses_default_horizon(self):
        snap = snapshot([make_task(hours=26.0)], settings=Settings(default_horizon_weeks=1))
        data = dashboard_data(snap, Filter(), TODAY, T0)
        self.assertEqual(data.horizon_weeks, 1)
        self.assertAlmostEqual(data.ratio, 1.0)  # 26 h demand / 5 x 5.2 h capacity
        self.assertEqual(data.level, "amber")

    def test_dependency_warning_checks_predecessors_outside_filter(self):
        pred = make_task(end=D("2026-10-20"), priority=Priority.LOW)
        succ = make_task(start=D("2026-10-14"), predecessor_ids=frozenset({pred.id}),
                         priority=Priority.HIGH)  # fmt: skip
        data = dashboard_data(snapshot([pred, succ]), Filter(priorities=frozenset({2})),
                              TODAY, T0)  # fmt: skip
        self.assertEqual([(t.id, [p.id for p in ps]) for t, ps in data.dependency_warnings],
                         [(succ.id, [pred.id])])  # fmt: skip

    def test_milestone_warning_and_cycles(self):
        ms = make_milestone(day=D("2026-10-14"))
        a = make_task(milestone_id=ms.id, end=D("2026-10-20"))
        b = make_task(predecessor_ids=frozenset({a.id}))
        a = replace(a, predecessor_ids=frozenset({b.id}))
        data = dashboard_data(snapshot([a, b], [ms]), Filter(), TODAY, T0)
        self.assertEqual([(m.id, end) for m, end in data.milestone_warnings],
                         [(ms.id, D("2026-10-20"))])  # fmt: skip
        self.assertEqual([sorted(t.id for t in c) for c in data.cycles], [sorted([a.id, b.id])])


class YourDayTest(unittest.TestCase):
    def test_due_text(self):
        self.assertEqual(due_text(TODAY, True, D("2026-10-09"), TODAY), "overdue 3 d")
        self.assertEqual(due_text(TODAY, False, TODAY, TODAY), "due today")
        self.assertEqual(due_text(D("2026-10-14"), False, D("2026-10-14"), TODAY), "due Wed")
        self.assertEqual(due_text(D("2026-11-30"), False, D("2026-11-30"), TODAY), "due 30 Nov")

    def test_section_marks_capacity_cut_and_blocked(self):
        from driftline.calc.calendar import CalendarContext
        from driftline.calc.workload import day_plan

        big = make_task(priority=Priority.CRITICAL, start=TODAY, end=TODAY, hours=6.0, at_risk=True)
        small = make_task(priority=Priority.LOW, start=TODAY, end=TODAY, hours=1.0)
        blocked = make_task(status=TaskStatus.BLOCKED, start=TODAY, end=TODAY, hours=1.0)
        tasks = [big, small, blocked]
        plan = day_plan(tasks, TODAY, CalendarContext(Settings()))
        text = str(day_section(plan, {t.id: t for t in tasks}, {}, TODAY))
        self.assertIn("plannable time ends here", text)
        self.assertIn("more than fits", text)
        self.assertIn("Blocked, not workable", text)
        self.assertIn("⚠", text)  # FUN-04 marker on the at-risk task
        self.assertEqual(day_title(plan, TODAY), "Your day · Monday, 12 October")


class WorkloadFilterTest(unittest.TestCase):
    def test_status_dates_and_archive_do_not_apply(self):
        f = Filter(
            labels=frozenset({1}),
            priorities=frozenset({2}),
            statuses=frozenset(),
            date_from=D("2026-10-01"),
            include_archived=True,
            at_risk_only=True,
        )
        scoped = workload_filter(f)
        self.assertEqual(
            (scoped.labels, scoped.priorities, scoped.at_risk_only),
            (frozenset({1}), frozenset({2}), True),
        )
        self.assertEqual(scoped.statuses, Filter().statuses)
        self.assertIsNone(scoped.date_from)
        self.assertFalse(scoped.include_archived)


class WorkloadDataTest(unittest.TestCase):
    def test_filter_applies_and_label_colors_are_stable(self):
        labels = (Label(1, "work", "work"), Label(2, "home", "home"))
        work = make_task(label_ids=frozenset({1}), hours=10.0)
        home = make_task(label_ids=frozenset({2}), hours=4.0)
        snap = snapshot([work, home], labels=labels)
        everything = workload_data(snap, Filter(), TODAY, 2, "label")
        only_work = workload_data(snap, Filter(labels=frozenset({1})), TODAY, 2, "label")
        self.assertAlmostEqual(everything.weekly["hours"].sum(), 14.0)
        self.assertAlmostEqual(only_work.weekly["hours"].sum(), 10.0)
        self.assertEqual(everything.colors["work"], only_work.colors["work"])  # no repaint
        self.assertAlmostEqual(only_work.curves["demand_h"].iloc[-1], 10.0)

    def test_many_labels_fold_into_other(self):
        labels = tuple(Label(i, f"l{i:02d}", f"l{i:02d}") for i in range(1, 11))
        tasks = [make_task(label_ids=frozenset({i})) for i in range(1, 11)]
        data = workload_data(snapshot(tasks, labels=labels), Filter(), TODAY, 2, "label")
        groups = set(data.weekly["group"])
        self.assertIn(charts.OTHER, groups)
        self.assertLessEqual(len(groups), 8)

    def test_biggest_labels_keep_their_color(self):
        labels = tuple(Label(i, f"l{i:02d}", f"l{i:02d}") for i in range(1, 11))
        tasks = [make_task(label_ids=frozenset({i}), hours=float(i)) for i in range(1, 11)]
        snap = snapshot(tasks, labels=labels)
        kept = colored_labels(snap)
        self.assertEqual(kept, [f"l{i:02d}" for i in range(5, 11)])  # 6 biggest, alphabetical
        filtered = workload_data(snap, Filter(labels=frozenset({10})), TODAY, 2, "label")
        everything = workload_data(snap, Filter(), TODAY, 2, "label")
        self.assertEqual(filtered.colors["l10"], everything.colors["l10"])  # no repaint

    def test_priority_colors(self):
        data = workload_data(snapshot([make_task()]), Filter(), TODAY, 2, "priority")
        self.assertEqual(data.colors, charts.PRIORITY_COLORS)
        self.assertEqual(set(data.weekly["group"]), {"Medium"})


class MilestonesPageTest(unittest.TestCase):
    def test_rows_with_warning_and_open_task_count(self):
        ms = make_milestone(day=D("2026-10-14"))
        snap = snapshot(
            [make_task(milestone_id=ms.id, end=D("2026-10-20")),
             make_task(milestone_id=ms.id, status=TaskStatus.DONE, remaining_effort_h=0.0)],
            [ms],
        )  # fmt: skip
        (row,) = milestone_rows(snap, Filter())
        self.assertEqual(row["open_tasks"], 1)
        self.assertIn("2026-10-20 (+6 d)", row["warning"])

    def test_rows_respect_milestone_filter_and_archive(self):
        a, b = make_milestone(), make_milestone(archived_at=T0)
        snap = snapshot([], [a, b])
        self.assertEqual([r["id"] for r in milestone_rows(snap, Filter())], [a.id])
        both = milestone_rows(snap, Filter(include_archived=True))
        self.assertEqual({r["id"] for r in both}, {a.id, b.id})
        only_b = Filter(milestone_ids=frozenset({b.id}), include_archived=True)
        self.assertEqual([r["id"] for r in milestone_rows(snap, only_b)], [b.id])

    def test_mta_figure_ends_achieved_milestone_on_its_date(self):
        done = make_milestone(name="Done", status=MilestoneStatus.ACHIEVED,
                              achieved_date=D("2026-10-05"), day=D("2026-10-05"))  # fmt: skip
        log = {done.id: (forecast_entry(done.id, D("2026-10-01"), "2026-10-05"),)}
        fig = mta_figure(snapshot([], [done], forecast_log=log), Filter(), TODAY, None)
        line = fig.data[1]
        self.assertEqual(line.name, "Done")
        self.assertEqual(str(line.x[-1])[:10], "2026-10-05")

    def test_dialog_actions(self):
        create = dialog_action({"mode": "create", "ids": []}, "M", "", "2026-11-01", "")
        self.assertEqual(create["kind"], "create_milestone")
        edit = dialog_action({"mode": "edit", "ids": [4]}, "M", "d", "2026-11-01", "why")
        self.assertEqual((edit["kind"], edit["milestone_id"], edit["reason"]),
                         ("update_milestone", 4, "why"))  # fmt: skip
        achieve = dialog_action({"mode": "achieve", "ids": [4]}, "", "", "2026-10-30", "")
        self.assertEqual(achieve["achieved_date"], "2026-10-30")
        rebase = dialog_action({"mode": "rebaseline", "ids": [1, 2]}, "", "", "", "New plan")
        self.assertEqual(rebase["milestone_ids"], [1, 2])
        self.assertEqual(dialog_action({"mode": "edit", "ids": []}, "", "", "", "")["kind"],
                         "none")  # fmt: skip


class TimeWindowTest(unittest.TestCase):
    def test_windows(self):
        wed = D("2026-10-14")
        self.assertEqual(window(wed, "week"), (D("2026-10-12"), D("2026-10-18")))
        self.assertEqual(window(wed, "month"), (D("2026-10-01"), D("2026-10-31")))
        self.assertEqual(window(D("2026-02-10"), "month"), (D("2026-02-01"), D("2026-02-28")))
        self.assertEqual(window(wed, "year"), (D("2026-01-01"), D("2026-12-31")))
        self.assertIsNone(window(wed, "all"))

    def test_shift_across_boundaries(self):
        self.assertEqual(shift(D("2026-12-30"), "week", 1), D("2027-01-06"))
        self.assertEqual(shift(D("2026-12-31"), "month", 1), D("2027-01-01"))
        self.assertEqual(shift(D("2026-01-31"), "month", -1), D("2025-12-01"))
        self.assertEqual(shift(D("2026-03-31"), "month", -1), D("2026-02-01"))  # no Feb 31
        self.assertEqual(shift(D("2026-10-14"), "year", -1), D("2025-01-01"))
        self.assertEqual(shift(D("2026-10-14"), "all", 5), D("2026-10-14"))

    def test_labels(self):
        self.assertEqual(period_label(D("2026-10-14"), "week"), "Week 42 · 12 Oct – 18 Oct 2026")
        self.assertEqual(period_label(D("2026-10-14"), "month"), "October 2026")
        self.assertEqual(period_label(D("2026-10-14"), "year"), "2026")
        self.assertEqual(period_label(D("2026-10-14"), "all"), "All dates")


class TimelinePageTest(unittest.TestCase):
    def test_figure_uses_filter_and_milestone_switch(self):
        ms = make_milestone()
        high = make_task(priority=Priority.HIGH, milestone_id=ms.id)
        low = make_task(priority=Priority.LOW)
        snap = snapshot([high, low], [ms])
        fig = timeline_figure(snap, Filter(priorities=frozenset({2})), TODAY, True)
        rows = {y for trace in fig.data if trace.y for y in trace.y if y}
        self.assertIn(f"#{high.id} Task", rows)
        self.assertNotIn(f"#{low.id} Task", rows)
        self.assertTrue(any(y.startswith("◆") for y in rows))
        no_ms = timeline_figure(snap, Filter(), TODAY, False)
        self.assertFalse(any(t.name and "Milestone" in t.name for t in no_ms.data))

    def test_dependency_links_follow_switch_and_lateness(self):
        pred = make_task(end=D("2026-10-20"))
        succ = make_task(start=D("2026-10-14"), predecessor_ids=frozenset({pred.id}))
        snap = snapshot([pred, succ])
        with_links = timeline_figure(snap, Filter(), TODAY, False, show_dependencies=True)
        names = {t.name for t in with_links.data}
        self.assertIn("Late dependency", names)  # succ starts before pred ends
        without = timeline_figure(snap, Filter(), TODAY, False, show_dependencies=False)
        self.assertFalse({"Dependency", "Late dependency"} & {t.name for t in without.data})

    def test_window_shows_only_tasks_in_period_and_fixes_axis(self):
        inside = make_task(start=D("2026-10-12"), end=D("2026-10-16"))
        outside = make_task(start=D("2026-12-01"), end=D("2026-12-04"))
        slipped = replace(
            make_task(start=D("2026-12-07"), end=D("2026-12-09")),
            baseline_start=D("2026-10-13"),
            baseline_end=D("2026-10-14"),
        )
        span = window(D("2026-10-14"), "month")
        fig = timeline_figure(
            snapshot([inside, outside, slipped]), Filter(), TODAY, False, span=span
        )
        rows = {y for trace in fig.data if trace.y for y in trace.y if y}
        self.assertIn(f"#{inside.id} Task", rows)
        self.assertIn(f"#{slipped.id} Task", rows)  # its baseline is in October
        self.assertNotIn(f"#{outside.id} Task", rows)
        self.assertEqual(list(fig.layout.xaxis.range), ["2026-10-01", "2026-11-01"])

    def test_clicked_task_id(self):
        self.assertEqual(clicked_task_id({"points": [{"customdata": [7, "x"]}]}), 7)
        self.assertIsNone(clicked_task_id({"points": [{"customdata": [-3, "M"]}]}))
        self.assertIsNone(clicked_task_id({"points": [{"x": 1}]}))
        self.assertIsNone(clicked_task_id(None))


if __name__ == "__main__":
    unittest.main()
