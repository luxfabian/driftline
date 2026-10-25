"""Figure builders (architecture §11): return a Figure, filter text in subtitle, trace counts."""

from __future__ import annotations

import unittest
from datetime import date

import pandas as pd
import plotly.graph_objects as go

from driftline.domain.enums import TaskStatus
from driftline.ui import charts, theme
from tests.factories import TODAY, D, make_milestone, make_task

FILTER_TEXT = "Labels: work (any)"


def subtitle(fig: go.Figure) -> str:
    return fig.layout.title.subtitle.text


def names(fig: go.Figure) -> list[str]:
    return [t.name for t in fig.data]


class GanttTest(unittest.TestCase):
    def test_traces_and_subtitle(self):
        planned = make_task()
        blocked = make_task(status=TaskStatus.BLOCKED)
        ms = make_milestone()
        fig = charts.build_gantt([planned, blocked], [ms], TODAY, FILTER_TEXT,
                                 risk_ids={planned.id}, overdue_ids={blocked.id})  # fmt: skip
        self.assertIsInstance(fig, go.Figure)
        self.assertIn(FILTER_TEXT, subtitle(fig))
        self.assertEqual(
            names(fig),
            ["Baseline", "Planned", "Blocked", "⚠ At risk", "Overdue (outline)",
             "Milestone baseline", "Milestone forecast"],
        )  # fmt: skip
        blocked_trace = fig.data[2]
        self.assertEqual(blocked_trace.marker.pattern.shape, "/")  # not color alone
        self.assertEqual(blocked_trace.marker.line.color, (charts.STATUS_CRITICAL,))

    def test_dependency_connectors(self):  # FUN-06/07, toggled on the timeline page
        a = make_task(start=D("2026-10-12"), end=D("2026-10-16"))
        b = make_task(start=D("2026-10-19"), end=D("2026-10-23"))
        c = make_task(start=D("2026-10-14"), end=D("2026-10-20"))
        hidden = make_task()
        links = [(a.id, b.id, False), (a.id, c.id, True), (hidden.id, b.id, False)]
        fig = charts.build_gantt([a, b, c], [], TODAY, FILTER_TEXT, risk_ids=(), dependencies=links)
        lines = {t.name: t for t in fig.data if getattr(t, "mode", None) == "lines"}
        self.assertEqual(set(lines), {"Dependency", "Late dependency"})
        ok = lines["Dependency"]
        # elbow: down from a's bar end (day after its end), then across to b's start
        self.assertEqual(list(ok.x), ["2026-10-17", "2026-10-17", "2026-10-19", None])
        self.assertEqual(ok.y[0], f"#{a.id} Task")
        self.assertEqual(ok.y[2], f"#{b.id} Task")
        self.assertEqual(lines["Late dependency"].line.color, charts.STATUS_CRITICAL)
        # the link from the hidden task is not drawn
        self.assertEqual(sum(x is None for x in ok.x), 1)

    def test_no_connectors_without_dependencies(self):
        fig = charts.build_gantt([make_task()], [], TODAY, FILTER_TEXT, risk_ids=())
        self.assertFalse(any(getattr(t, "mode", None) == "lines" for t in fig.data))

    def test_window_ticks_follow_period_length(self):
        t = make_task()
        week = charts.build_gantt(
            [t], [], TODAY, FILTER_TEXT, risk_ids=(), window=(D("2026-10-12"), D("2026-10-18"))
        )
        self.assertEqual(list(week.layout.xaxis.range), ["2026-10-12", "2026-10-19"])
        self.assertEqual(week.layout.xaxis.dtick, charts.DAY_MS)
        year = charts.build_gantt(
            [t], [], TODAY, FILTER_TEXT, risk_ids=(), window=(D("2026-01-01"), D("2026-12-31"))
        )
        self.assertEqual(year.layout.xaxis.dtick, "M1")

    def test_bar_spans_inclusive_end_day(self):
        t = make_task(start=D("2026-10-12"), end=D("2026-10-12"))
        fig = charts.build_gantt([t], [], TODAY, FILTER_TEXT, risk_ids=())
        forecast = fig.data[1]
        self.assertEqual(forecast.x[0], charts.DAY_MS)
        self.assertEqual(forecast.customdata[0][0], t.id)  # click-to-open uses this

    def test_empty(self):
        fig = charts.build_gantt([], [], TODAY, FILTER_TEXT, risk_ids=())
        self.assertEqual(len(fig.data), 0)
        self.assertIn(FILTER_TEXT, subtitle(fig))


class MtaTest(unittest.TestCase):
    def test_one_line_per_milestone_plus_diagonal(self):
        series = {
            "Paper": [(D("2026-10-01"), D("2026-11-01")), (D("2026-10-12"), D("2026-11-01"))],
            "Review": [(D("2026-10-05"), D("2026-12-01"))],
            "Empty": [],
        }
        fig = charts.build_mta(series, TODAY, FILTER_TEXT, colors={"Paper": "#123456"})
        self.assertEqual(names(fig), ["Reporting date = forecast", "Paper", "Review"])
        self.assertEqual(fig.data[1].line.color, "#123456")
        self.assertIn(FILTER_TEXT, subtitle(fig))
        # Diagonal: x == y, and both axes share one range so it is 45°.
        self.assertEqual(list(fig.data[0].x), list(fig.data[0].y))
        self.assertEqual(fig.layout.xaxis.range, fig.layout.yaxis.range)

    def test_no_history(self):
        fig = charts.build_mta({}, TODAY, FILTER_TEXT)
        self.assertEqual(len(fig.data), 0)


class WorkloadChartsTest(unittest.TestCase):
    def curves(self, demand, capacity):
        days = [date(2026, 10, 12 + i) for i in range(len(demand))]
        return pd.DataFrame(
            {"date": days, "demand_h": demand, "capacity_h": capacity,
             "shortfall_h": [max(0, d - c) for d, c in zip(demand, capacity, strict=True)]}
        )  # fmt: skip

    def test_cumulative_shades_shortfall(self):
        fig = charts.build_cumulative(self.curves([10, 10, 20], [5, 10, 15]), FILTER_TEXT)
        self.assertEqual(
            names(fig), ["Demand within capacity", "Demand above capacity", "Capacity"]
        )
        self.assertEqual(fig.layout.barmode, "stack")
        self.assertEqual(list(fig.data[0].y), [5, 10, 15])  # min(demand, capacity)
        self.assertEqual(list(fig.data[1].y), [5, 0, 5])  # shortfall on top
        self.assertEqual(fig.data[1].marker.color, theme.active().blocked)
        self.assertIn(FILTER_TEXT, subtitle(fig))
        self.assertTrue(any("5.0 h" in a.text for a in fig.layout.annotations))

    def test_cumulative_without_shortfall_has_no_annotation(self):
        fig = charts.build_cumulative(self.curves([1, 2], [5, 10]), FILTER_TEXT)
        self.assertEqual(len(fig.layout.annotations), 0)

    def weekly(self):
        mon = date(2026, 10, 12)
        return pd.DataFrame(
            {"week_start": [mon, mon, date(2026, 10, 19)], "group": ["work", "home", "work"],
             "hours": [5.0, 3.0, 4.0], "capacity_h": [26.0, 26.0, 26.0]}
        )  # fmt: skip

    def capacity(self):
        return pd.DataFrame({"week_start": [date(2026, 10, 12), date(2026, 10, 19)],
                             "capacity_h": [26.0, 26.0]})  # fmt: skip

    def test_weekly_by_label_notes_multi_label_counting(self):
        fig = charts.build_weekly_load(self.weekly(), self.capacity(), "Label", FILTER_TEXT)
        self.assertEqual(names(fig), ["work", "home", "Capacity"])
        self.assertIn(FILTER_TEXT, subtitle(fig))
        self.assertIn(charts.MULTI_LABEL_NOTE, subtitle(fig))
        self.assertEqual({t.stackgroup for t in fig.data[:2]}, {"load"})  # stacked lines
        self.assertIsNone(fig.data[2].stackgroup)  # capacity is not stacked
        self.assertEqual(list(fig.layout.xaxis.categoryarray), ["Wk of 12 Oct", "Wk of 19 Oct"])
        home = fig.data[1]
        self.assertEqual(list(home.y), [3.0, 0.0])  # weeks without hours are 0, not gaps

    def test_weekly_by_priority_has_no_label_note(self):
        fig = charts.build_weekly_load(self.weekly(), self.capacity(), "Priority", FILTER_TEXT)
        self.assertNotIn(charts.MULTI_LABEL_NOTE, subtitle(fig))

    def test_fold_groups(self):
        folded = charts.fold_groups(self.weekly(), keep={"work"})
        self.assertEqual(sorted(set(folded["group"])), ["Other", "work"])
        self.assertAlmostEqual(folded["hours"].sum(), 12.0)


class ColorsTest(unittest.TestCase):
    def test_categorical_fixed_order_and_other(self):
        few = charts.categorical_colors([3, 1, 2])
        self.assertEqual(list(few.values()), list(charts.categorical()[:3]))
        all_slots = charts.categorical_colors(range(len(charts.categorical())))
        self.assertEqual(list(all_slots.values()), list(charts.categorical()))
        many = charts.categorical_colors(range(10))
        self.assertEqual(
            len(set(many.values()) - {charts.OTHER_COLOR}), len(charts.categorical()) - 1
        )
        self.assertEqual(many[9], charts.OTHER_COLOR)

    def test_status_colors_cover_every_status(self):
        self.assertEqual(set(charts.task_status_colors()), set(TaskStatus))


if __name__ == "__main__":
    unittest.main()
