"""Working days and plannable capacity [WL-01, WL-02] (data_model_spec §5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property

from driftline.domain.models import Absence, Settings, Snapshot


@dataclass(frozen=True)
class CalendarContext:
    """Bundles the calendar inputs so signatures stay short (architecture §8)."""

    settings: Settings
    holidays: frozenset[date] = frozenset()
    absences: tuple[Absence, ...] = field(default_factory=tuple)

    @classmethod
    def from_snapshot(cls, snap: Snapshot) -> CalendarContext:
        return cls(snap.settings, snap.holidays, tuple(snap.absences))

    @cached_property
    def _absent_days(self) -> frozenset[date]:
        return _expand_absences(self.absences)

    @cached_property
    def daily_capacity_h(self) -> float:
        return daily_capacity(self.settings)

    def is_working_day(self, d: date) -> bool:
        return (
            d.isoweekday() in self.settings.working_weekdays
            and d not in self.holidays
            and d not in self._absent_days
        )

    def capacity_h(self, d: date) -> float:
        return self.daily_capacity_h if self.is_working_day(d) else 0.0

    def working_days(self, start: date, end: date) -> list[date]:
        return [d for d in date_range(start, end) if self.is_working_day(d)]

    def next_working_day(self, d: date, max_lookahead_days: int = 366) -> date | None:
        for offset in range(max_lookahead_days + 1):
            candidate = d + timedelta(days=offset)
            if self.is_working_day(candidate):
                return candidate
        return None


# --- functional API as specified in architecture §8 ------------------------------


def is_working_day(
    d: date, settings: Settings, holidays: frozenset[date], absences: Sequence[Absence]
) -> bool:
    """Configured weekday, not a public holiday, not inside any absence."""
    return CalendarContext(settings, frozenset(holidays), tuple(absences)).is_working_day(d)


def capacity_h(
    d: date, settings: Settings, holidays: frozenset[date], absences: Sequence[Absence]
) -> float:
    """WL-02: weekly hours / number of working weekdays x plannable fraction, else 0."""
    return CalendarContext(settings, frozenset(holidays), tuple(absences)).capacity_h(d)


def working_days(
    start: date,
    end: date,
    settings: Settings,
    holidays: frozenset[date],
    absences: Sequence[Absence],
) -> list[date]:
    """Working days in [start, end], both inclusive."""
    return CalendarContext(settings, frozenset(holidays), tuple(absences)).working_days(start, end)


def next_working_day(
    d: date,
    settings: Settings,
    holidays: frozenset[date],
    absences: Sequence[Absence],
    max_lookahead_days: int = 366,
) -> date | None:
    """First working day >= d, or None if there is none within the lookahead."""
    ctx = CalendarContext(settings, frozenset(holidays), tuple(absences))
    return ctx.next_working_day(d, max_lookahead_days)


# --- helpers -------------------------------------------------------------------


def daily_capacity(settings: Settings) -> float:
    if not settings.working_weekdays:
        return 0.0
    return settings.weekly_hours / len(settings.working_weekdays) * settings.plannable_fraction


def date_range(start: date, end: date) -> list[date]:
    """All dates in [start, end]; empty if end < start."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _expand_absences(absences: Sequence[Absence]) -> frozenset[date]:
    days: set[date] = set()
    for a in absences:
        days.update(date_range(a.start_date, a.end_date))
    return frozenset(days)
