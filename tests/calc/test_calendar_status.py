"""calc.calendar [WL-01, WL-02] and calc.status [FUN-12, WL-08, VAL-04, FUN-04]."""

from __future__ import annotations

import unittest
from datetime import timedelta

from pmtool.calc import calendar as cal
from pmtool.calc.calendar import CalendarContext
from pmtool.calc.status import (
    current_risk_reason,
    is_effort_overrun,
    is_open,
    is_overdue,
    is_stale,
)
from pmtool.domain.enums import TaskStatus
from pmtool.domain.models import Absence, Settings
from tests.factories import TODAY, D, make_task
from tests.helpers import T0

SETTINGS = Settings()  # 40 h, Mon-Fri, 65 % -> 5.2 h per working day
CTX = CalendarContext(
    SETTINGS,
    holidays=frozenset({D("2026-10-14")}),  # Wednesday
    absences=(Absence(1, D("2026-10-19"), D("2026-10-20"), "Off"),),  # Mon-Tue
)


class CalendarTest(unittest.TestCase):
    def test_WL_01_working_day_rules(self):
        self.assertTrue(CTX.is_working_day(D("2026-10-12")))  # Monday
        self.assertFalse(CTX.is_working_day(D("2026-10-17")))  # Saturday
        self.assertFalse(CTX.is_working_day(D("2026-10-14")))  # holiday
        self.assertFalse(CTX.is_working_day(D("2026-10-19")))  # absence start
        self.assertFalse(CTX.is_working_day(D("2026-10-20")))  # absence end (inclusive)
        self.assertTrue(CTX.is_working_day(D("2026-10-21")))

    def test_WL_01_custom_weekdays(self):
        ctx = CalendarContext(Settings(working_weekdays=(1, 2, 3, 4)))
        self.assertFalse(ctx.is_working_day(D("2026-10-16")))  # Friday off

    def test_WL_02_capacity_formula(self):
        self.assertAlmostEqual(CTX.capacity_h(D("2026-10-12")), 40 / 5 * 0.65)
        self.assertEqual(CTX.capacity_h(D("2026-10-14")), 0.0)
        ctx = CalendarContext(Settings(weekly_hours=32, working_weekdays=(1, 2, 3, 4),
                                       plannable_fraction=0.5))  # fmt: skip
        self.assertAlmostEqual(ctx.capacity_h(D("2026-10-12")), 4.0)

    def test_working_days_inclusive(self):
        self.assertEqual(
            CTX.working_days(D("2026-10-12"), D("2026-10-21")),
            [D("2026-10-12"), D("2026-10-13"), D("2026-10-15"), D("2026-10-16"),
             D("2026-10-21")],
        )  # fmt: skip
        self.assertEqual(CTX.working_days(D("2026-10-16"), D("2026-10-12")), [])

    def test_next_working_day(self):
        self.assertEqual(CTX.next_working_day(D("2026-10-12")), D("2026-10-12"))
        self.assertEqual(CTX.next_working_day(D("2026-10-17")), D("2026-10-21"))
        long_absence = CalendarContext(
            SETTINGS, absences=(Absence(1, TODAY, TODAY + timedelta(400)),)
        )
        self.assertIsNone(long_absence.next_working_day(TODAY))

    def test_functional_api_matches_context(self):
        args = (SETTINGS, CTX.holidays, CTX.absences)
        for offset in range(14):
            d = TODAY + timedelta(offset)
            self.assertEqual(cal.is_working_day(d, *args), CTX.is_working_day(d))
            self.assertEqual(cal.capacity_h(d, *args), CTX.capacity_h(d))
        self.assertEqual(cal.working_days(TODAY, D("2026-10-21"), *args),
                         CTX.working_days(TODAY, D("2026-10-21")))  # fmt: skip
        self.assertEqual(cal.next_working_day(D("2026-10-17"), *args), D("2026-10-21"))


class StatusTest(unittest.TestCase):
    def test_is_open(self):
        self.assertTrue(is_open(make_task(status=TaskStatus.BLOCKED)))
        self.assertFalse(is_open(make_task(status=TaskStatus.DONE, remaining_effort_h=0)))
        self.assertFalse(is_open(make_task(archived_at=T0)))

    def test_FUN_12_overdue_strictly_before_today(self):
        self.assertTrue(is_overdue(make_task(end=D("2026-10-09")), TODAY))
        self.assertFalse(is_overdue(make_task(end=TODAY), TODAY))
        self.assertFalse(is_overdue(make_task(end=D("2026-10-09"), status=TaskStatus.DONE), TODAY))

    def test_WL_08_stale_after_more_than_n_days(self):
        t = make_task()
        self.assertFalse(is_stale(t, T0 + timedelta(days=14), 14))
        self.assertTrue(is_stale(t, T0 + timedelta(days=14, seconds=1), 14))
        self.assertFalse(is_stale(make_task(status=TaskStatus.DONE), T0 + timedelta(days=99), 14))

    def test_VAL_04_effort_overrun(self):
        self.assertTrue(is_effort_overrun(make_task(hours=10, remaining_effort_h=12)))
        self.assertFalse(is_effort_overrun(make_task(hours=10, remaining_effort_h=10)))

    def test_FUN_04_risk_reason_only_while_at_risk(self):
        t = make_task(at_risk=True)
        self.assertEqual(current_risk_reason(t, {t.id: "late"}), "late")
        self.assertIsNone(current_risk_reason(make_task(id=t.id), {t.id: "late"}))


if __name__ == "__main__":
    unittest.main()
