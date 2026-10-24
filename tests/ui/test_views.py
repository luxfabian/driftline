"""Pure view helpers: grid rows, flags, dropdown options."""

from __future__ import annotations

import unittest
from datetime import timedelta

from pmtool.domain.enums import Priority, TaskStatus
from pmtool.domain.filters import Filter
from pmtool.domain.models import Label, Settings, Snapshot
from pmtool.ui.formatting import (
    FLAG_AT_RISK,
    FLAG_DEPENDENCY,
    FLAG_OVERDUE,
    FLAG_OVERRUN,
    FLAG_STALE,
    filter_text,
    label_options,
    lookups,
    milestone_options,
    task_options,
)
from pmtool.ui.pages.tasks import task_rows
from tests.factories import TODAY, D, make_milestone, make_task
from tests.helpers import T0


def snapshot(tasks, milestones=(), labels=()):
    return Snapshot(
        tasks=tuple(tasks),
        milestones=tuple(milestones),
        labels=tuple(labels),
        settings=Settings(),
        absences=(),
        holidays=frozenset(),
    )


class TaskRowsTest(unittest.TestCase):
    def rows(self, tasks, f=None, labels=(), now=T0):
        snap = snapshot(tasks, labels=labels)
        return {r["id"]: r for r in task_rows(snap, f or Filter(), TODAY, now)}

    def test_row_fields(self):
        t = make_task(title="Report", priority=Priority.HIGH, label_ids=frozenset({2, 1}),
                      forecast_end=D("2026-10-19"))  # fmt: skip
        labels = (Label(1, "work", "work"), Label(2, "Admin", "admin"))
        row = self.rows([t], labels=labels)[t.id]
        self.assertEqual(row["rid"], str(t.id))
        self.assertEqual(row["priority"], "2 High")
        self.assertEqual(row["status"], "Planned")
        self.assertEqual(row["labels"], "Admin, work")
        self.assertEqual(row["end"], "2026-10-19")
        self.assertEqual(row["end_variance_d"], 3)  # baseline end 2026-10-16
        self.assertEqual(row["start_variance_d"], 0)  # SCH-03: both variances

    def test_overdue_and_at_risk_marked(self):  # FUN-04, FUN-12
        late = make_task(start=D("2026-10-01"), end=D("2026-10-09"))
        risky = make_task(title="Risky", at_risk=True)
        rows = self.rows([late, risky])
        self.assertTrue(rows[late.id]["overdue"])
        self.assertIn(FLAG_OVERDUE, rows[late.id]["flags"])
        self.assertTrue(rows[risky.id]["title"].startswith("⚠"))
        self.assertIn(FLAG_AT_RISK, rows[risky.id]["flags"])
        self.assertFalse(rows[risky.id]["overdue"])

    def test_stale_overrun_and_dependency_flags(self):
        pred = make_task(end=D("2026-10-20"))
        succ = make_task(start=D("2026-10-14"), end=D("2026-10-30"),
                         predecessor_ids=frozenset({pred.id}), remaining_effort_h=20.0)  # fmt: skip
        rows = self.rows([pred, succ], now=T0 + timedelta(days=15))
        flags = rows[succ.id]["flags"]
        for flag in (FLAG_DEPENDENCY, FLAG_STALE, FLAG_OVERRUN):
            self.assertIn(flag, flags)

    def test_filter_applies_and_done_hidden_by_default(self):
        done = make_task(status=TaskStatus.DONE, remaining_effort_h=0.0)
        low = make_task(priority=Priority.LOW)
        self.assertEqual(set(self.rows([done, low])), {low.id})
        only_high = Filter(priorities=frozenset({1, 2}))
        self.assertEqual(self.rows([done, low], f=only_high), {})

    def test_archived_only_with_filter(self):
        archived = make_task(archived_at=T0)
        self.assertEqual(self.rows([archived]), {})
        row = self.rows([archived], f=Filter(include_archived=True))[archived.id]
        self.assertTrue(row["archived"])

    def test_filter_text(self):
        labels = (Label(1, "work", "work"),)
        snap = snapshot([], labels=labels)
        self.assertEqual(filter_text(snap, Filter()), "No filter")
        self.assertIn("work", filter_text(snap, Filter(labels=frozenset({1}))))


class OptionsTest(unittest.TestCase):
    def test_label_options_offer_new_label_case_insensitively(self):  # DAT-04
        lookup = {"labels": ["work", "Admin"]}
        values = [o["value"] for o in label_options(lookup, [], "WORK")]
        self.assertEqual(values, ["work", "Admin"])  # existing label offered, no duplicate
        options = label_options(lookup, ["home"], "  travel ")
        self.assertEqual([o["value"] for o in options], ["work", "Admin", "home", "travel"])

    def test_lookups_mark_archived_items(self):
        ms_open = make_milestone(name="Open")
        ms_old = make_milestone(name="Old", archived_at=T0)
        t1 = make_task(title="Active")
        t2 = make_task(title="Gone", archived_at=T0)
        lookup = lookups(snapshot([t1, t2], milestones=[ms_open, ms_old]))
        ms = {o["value"]: o for o in milestone_options(lookup)}
        self.assertFalse(ms[ms_open.id]["disabled"])
        self.assertTrue(ms[ms_old.id]["disabled"])
        self.assertIn("(archived)", ms[ms_old.id]["label"])
        tasks = task_options(lookup, exclude=t1.id)
        self.assertEqual([o["value"] for o in tasks], [t2.id])
        self.assertTrue(tasks[0]["disabled"])


if __name__ == "__main__":
    unittest.main()
