"""Pure page functions of the phase 5 views (no browser)."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta

from pmtool.domain.enums import MilestoneStatus, Priority, TaskStatus
from pmtool.domain.filters import Filter
from pmtool.domain.models import Label, Settings, Snapshot
from pmtool.ui import charts
from pmtool.ui.pages.dashboard import dashboard_data
from pmtool.ui.pages.milestones import dialog_action, milestone_rows, mta_figure
from pmtool.ui.pages.timeline import clicked_task_id, timeline_figure
from pmtool.ui.pages.workload import workload_data
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

    def test_clicked_task_id(self):
        self.assertEqual(clicked_task_id({"points": [{"customdata": [7, "x"]}]}), 7)
        self.assertIsNone(clicked_task_id({"points": [{"customdata": [-3, "M"]}]}))
        self.assertIsNone(clicked_task_id({"points": [{"x": 1}]}))
        self.assertIsNone(clicked_task_id(None))


if __name__ == "__main__":
    unittest.main()
