"""Figure builders (architecture §11): return a Figure, filter text in subtitle, trace counts."""

from __future__ import annotations

import unittest
from datetime import date

import pandas as pd
import plotly.graph_objects as go

from pmtool.domain.enums import TaskStatus
from pmtool.ui import charts
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
            ["Baseline", "Planned", "Blocked", "⚠ At risk", "Overdue (red outline)",
             "Milestone baseline", "Milestone forecast"],
        )  # fmt: skip
        blocked_trace = fig.data[2]
        self.assertEqual(blocked_trace.marker.pattern.shape, "/")  # not color alone
        self.assertEqual(blocked_trace.marker.line.color, (charts.STATUS_CRITICAL,))

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
        self.assertEqual(names(fig), ["Capacity", "Shortfall", "Demand"])
        self.assertEqual(fig.data[1].fill, "tonexty")
        self.assertEqual(list(fig.data[1].y), [10, 10, 20])  # max(demand, capacity)
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
        self.assertEqual(fig.layout.barmode, "stack")
        self.assertEqual(list(fig.layout.xaxis.categoryarray), ["Wk of 12 Oct", "Wk of 19 Oct"])

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
        self.assertEqual(list(few.values()), list(charts.CATEGORICAL[:3]))
        many = charts.categorical_colors(range(10))
        self.assertEqual(len(set(many.values()) - {charts.OTHER_COLOR}), 7)
        self.assertEqual(many[9], charts.OTHER_COLOR)

    def test_status_colors_cover_every_status(self):
        self.assertEqual(set(charts.TASK_STATUS_COLORS), set(TaskStatus))


if __name__ == "__main__":
    unittest.main()
