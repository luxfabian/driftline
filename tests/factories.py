"""Pure domain-object factories for calc and filter tests (architecture §11).

Plain functions rather than pytest fixtures, so the suite also runs under unittest.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from itertools import count

from driftline.domain.enums import ChangeKind, EntityType, MilestoneStatus, Priority, TaskStatus
from driftline.domain.models import ChangeLogEntry, Milestone, Task
from tests.helpers import T0

D = date.fromisoformat
TODAY = D("2026-10-12")  # a Monday
_ids = count(1)


def make_task(**overrides) -> Task:
    start = overrides.pop("start", D("2026-10-12"))
    end = overrides.pop("end", D("2026-10-16"))
    hours = overrides.pop("hours", 10.0)
    base = Task(
        id=next(_ids),
        title="Task",
        description=None,
        baseline_start=start,
        baseline_end=end,
        forecast_start=start,
        forecast_end=end,
        estimated_effort_h=hours,
        remaining_effort_h=hours,
        status=TaskStatus.PLANNED,
        priority=Priority.MEDIUM,
        at_risk=False,
        milestone_id=None,
        last_review_at=T0,
        created_at=T0,
        updated_at=T0,
        archived_at=None,
    )
    return replace(base, **overrides)


def make_milestone(**overrides) -> Milestone:
    day = overrides.pop("day", D("2026-11-30"))
    base = Milestone(
        id=next(_ids),
        name="Milestone",
        description=None,
        baseline_date=day,
        forecast_date=day,
        status=MilestoneStatus.OPEN,
        achieved_date=None,
        created_at=T0,
        updated_at=T0,
        archived_at=None,
    )
    return replace(base, **overrides)


def forecast_entry(milestone_id: int, on: date, value: str, hour: int = 9) -> ChangeLogEntry:
    when = T0.replace(year=on.year, month=on.month, day=on.day, hour=hour)
    return ChangeLogEntry(
        entity_type=EntityType.MILESTONE,
        entity_id=milestone_id,
        change_kind=ChangeKind.EDIT,
        field="forecast_date",
        old_value=None,
        new_value=value,
        reason=None,
        batch_id=None,
        changed_at=when,
        id=next(_ids),
    )


def days(n: int) -> timedelta:
    return timedelta(days=n)
