"""Workload forecast [WL-03..WL-07] (data_model_spec §5, architecture §8).

Inputs are already filtered tasks (FUN-10). Only open tasks with remaining
effort count; Blocked tasks count too (WL-05).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import pandas as pd

from driftline.calc.calendar import CalendarContext, date_range
from driftline.calc.status import is_open
from driftline.domain.enums import Priority, TaskStatus
from driftline.domain.models import Settings, Task

NO_LABEL = "(no label)"
LoadLevel = Literal["green", "amber", "red", "na"]


def due_date(t: Task, today: date) -> date:
    """WL-04: overdue work is due today."""
    return max(t.forecast_end, today)


def demand_tasks(tasks: Iterable[Task]) -> list[Task]:
    """Tasks that create demand: open (incl. Blocked) with remaining effort > 0."""
    return [t for t in tasks if is_open(t) and t.remaining_effort_h > 0]


def cumulative_curves(
    tasks: Sequence[Task], today: date, horizon_end: date, calendar_ctx: CalendarContext
) -> pd.DataFrame:
    """WL-03: one row per day from today to horizon_end (inclusive).

    Columns: date, demand_h, capacity_h, shortfall_h (all cumulative).
    """
    days = date_range(today, horizon_end)
    due: dict[date, float] = defaultdict(float)
    for t in demand_tasks(tasks):
        due[due_date(t, today)] += t.remaining_effort_h

    rows = []
    demand = capacity = 0.0
    for d in days:
        demand += due.get(d, 0.0)
        capacity += calendar_ctx.capacity_h(d)
        rows.append((d, demand, capacity, max(0.0, demand - capacity)))
    return pd.DataFrame(rows, columns=["date", "demand_h", "capacity_h", "shortfall_h"])


def daily_allocation(
    tasks: Sequence[Task], today: date, horizon_end: date, calendar_ctx: CalendarContext
) -> pd.DataFrame:
    """WL-06: remaining effort spread evenly over working days.

    Interval: [max(today, forecast start), forecast end]. If it holds no working
    day, all effort goes to the next working day >= max(today, forecast start)
    (for overdue tasks that is the next working day from today). If no working
    day exists within a year, the effort stays on the interval start so it is
    not lost. Rows after horizon_end are dropped. Columns: date, task_id, hours.
    """
    rows: list[tuple[date, int, float]] = []
    for t in demand_tasks(tasks):
        start = max(today, t.forecast_start)
        days = calendar_ctx.working_days(start, t.forecast_end)
        if not days:
            fallback = calendar_ctx.next_working_day(start)
            days = [fallback if fallback is not None else start]
        share = t.remaining_effort_h / len(days)
        rows.extend((d, t.id, share) for d in days if d <= horizon_end)
    return pd.DataFrame(rows, columns=["date", "task_id", "hours"])


def week_start(d: date) -> date:
    """Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def weekly_load(
    allocation: pd.DataFrame,
    tasks: Sequence[Task],
    group_by: Literal["priority", "label"],
    calendar_ctx: CalendarContext,
    labels: Mapping[int, str] | None = None,
) -> pd.DataFrame:
    """WL-06: hours per week and group. Columns: week_start, group, hours, capacity_h.

    group_by "priority": group = priority label, ordered Critical..Low.
    group_by "label": a task with several labels counts in EACH of its label
    groups (the chart must say so); tasks without labels go to "(no label)".
    ``labels`` maps label id -> name (unknown ids show as "#<id>").
    ``capacity_h`` is the plannable capacity of that whole week.
    """
    if group_by not in ("priority", "label"):
        raise ValueError(f"group_by must be 'priority' or 'label', not {group_by!r}")
    columns = ["week_start", "group", "hours", "capacity_h"]
    if allocation.empty:
        return pd.DataFrame(columns=columns)

    by_id = {t.id: t for t in tasks}
    names = labels or {}
    hours: dict[tuple[date, str], float] = defaultdict(float)
    for d, task_id, h in allocation[["date", "task_id", "hours"]].itertuples(index=False):
        t = by_id.get(task_id)
        if t is None:
            continue
        for group in _groups(t, group_by, names):
            hours[(week_start(d), group)] += h

    order = _group_order(group_by, {g for _, g in hours})
    rows = [
        (w, g, h, weekly_capacity_h(w, calendar_ctx))
        for (w, g), h in sorted(hours.items(), key=lambda kv: (kv[0][0], order[kv[0][1]]))
    ]
    return pd.DataFrame(rows, columns=columns)


def weekly_capacity(today: date, horizon_end: date, calendar_ctx: CalendarContext) -> pd.DataFrame:
    """Plannable capacity per week overlapping [today, horizon_end].

    Columns: week_start, capacity_h. Full weeks (Mon-Sun), so the first and last
    week match the bars of weekly_load.
    """
    rows = []
    w = week_start(today)
    while w <= horizon_end:
        rows.append((w, weekly_capacity_h(w, calendar_ctx)))
        w += timedelta(days=7)
    return pd.DataFrame(rows, columns=["week_start", "capacity_h"])


def weekly_capacity_h(monday: date, calendar_ctx: CalendarContext) -> float:
    return sum(calendar_ctx.capacity_h(monday + timedelta(days=i)) for i in range(7))


def horizon_end(today: date, horizon_weeks: int) -> date:
    """Last day of a horizon of N weeks starting today."""
    return today + timedelta(days=7 * horizon_weeks - 1)


def load_ratio(
    tasks: Sequence[Task], today: date, horizon_weeks: int, calendar_ctx: CalendarContext
) -> float | None:
    """WL-07: demand due within the horizon / capacity within it. None = n/a."""
    end = horizon_end(today, horizon_weeks)
    demand = sum(t.remaining_effort_h for t in demand_tasks(tasks) if due_date(t, today) <= end)
    capacity = sum(calendar_ctx.capacity_h(d) for d in date_range(today, end))
    if capacity <= 0:
        return None
    return demand / capacity


def load_level(ratio: float | None, settings: Settings) -> LoadLevel:
    """Traffic light: < green_max green, <= amber_max amber, above that red."""
    if ratio is None:
        return "na"
    if ratio < settings.load_green_max:
        return "green"
    if ratio <= settings.load_amber_max:
        return "amber"
    return "red"


def _groups(t: Task, group_by: str, names: Mapping[int, str]) -> list[str]:
    if group_by == "priority":
        return [t.priority.label]
    if group_by == "label":
        if not t.label_ids:
            return [NO_LABEL]
        return sorted({names.get(i, f"#{i}") for i in t.label_ids})
    raise ValueError(f"group_by must be 'priority' or 'label', not {group_by!r}")


def _group_order(group_by: str, groups: set[str]) -> dict[str, tuple]:
    if group_by == "priority":
        rank = {p.label: p.value for p in Priority}
        return {g: (rank.get(g, 99), g) for g in groups}
    return {g: (g == NO_LABEL, g.lower()) for g in groups}


# --- the plan for one day (dashboard "Your day") ------------------------------------------


@dataclass(frozen=True)
class DayItem:
    task_id: int
    hours: float  # this task's share of the day (WL-06 spreading)
    due: date  # due_date: overdue work is due today (WL-04)
    overdue: bool
    blocked: bool
    within_capacity: bool  # starts before the day's plannable capacity is used up


@dataclass(frozen=True)
class DayPlan:
    day: date | None  # today, or the next working day; None if none within a year
    capacity_h: float
    items: tuple[DayItem, ...]  # workable tasks in focus order, then blocked ones

    @property
    def planned_h(self) -> float:
        return sum(i.hours for i in self.items)

    @property
    def workable_h(self) -> float:
        return sum(i.hours for i in self.items if not i.blocked)


def plan_day(today: date, calendar_ctx: CalendarContext) -> date | None:
    """The day to plan: today if it is a working day, else the next working day."""
    return calendar_ctx.next_working_day(today)


def day_plan(tasks: Sequence[Task], today: date, calendar_ctx: CalendarContext) -> DayPlan:
    """What the workload model puts on the next working day, in the order to work on it.

    Hours per task come from ``daily_allocation`` (same model as the weekly chart).
    Focus order: priority (Critical first), then due date, then at-risk tasks first,
    then id. Blocked tasks keep their hours (WL-05) but go last, since they cannot be
    worked on. ``within_capacity`` marks the workable tasks that start before the
    running total reaches the day's plannable capacity.
    """
    day = plan_day(today, calendar_ctx)
    if day is None:
        return DayPlan(None, 0.0, ())
    allocation = daily_allocation(tasks, today, day, calendar_ctx)
    hours: dict[int, float] = defaultdict(float)
    for d, task_id, h in allocation[["date", "task_id", "hours"]].itertuples(index=False):
        if d == day:
            hours[task_id] += h
    by_id = {t.id: t for t in tasks}
    blocked = TaskStatus.BLOCKED

    def key(task_id: int) -> tuple:
        t = by_id[task_id]
        return (t.status is blocked, int(t.priority), due_date(t, today), not t.at_risk, t.id)

    capacity = calendar_ctx.capacity_h(day)
    items, used = [], 0.0
    for task_id in sorted(hours, key=key):
        t = by_id[task_id]
        is_blocked = t.status is blocked
        items.append(
            DayItem(
                task_id=task_id,
                hours=hours[task_id],
                due=due_date(t, today),
                overdue=t.forecast_end < today,
                blocked=is_blocked,
                within_capacity=not is_blocked and used < capacity,
            )
        )
        if not is_blocked:
            used += hours[task_id]
    return DayPlan(day, capacity, tuple(items))
