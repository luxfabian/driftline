"""Write commands (architecture §5.2).

In ``*Update`` commands every optional field means "unchanged" when None.
Validation happens in the services, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from driftline.domain.enums import Priority, TaskStatus

UNLINK = -1  # TaskUpdate.milestone_id value that removes the milestone link


@dataclass(frozen=True)
class TaskCreate:
    title: str
    forecast_start: date
    forecast_end: date
    estimated_effort_h: float
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    label_names: tuple[str, ...] = ()
    predecessor_ids: tuple[int, ...] = ()
    milestone_id: int | None = None


@dataclass(frozen=True)
class TaskUpdate:
    task_id: int
    title: str | None = None
    description: str | None = None
    forecast_start: date | None = None
    forecast_end: date | None = None
    estimated_effort_h: float | None = None
    remaining_effort_h: float | None = None
    status: TaskStatus | None = None
    status_reason: str | None = None  # required when status becomes BLOCKED [VAL-06]
    priority: Priority | None = None
    milestone_id: int | None = None  # UNLINK removes the link
    reason: str | None = None  # optional reason stored in change_log


@dataclass(frozen=True)
class MilestoneCreate:
    name: str
    forecast_date: date
    description: str | None = None


@dataclass(frozen=True)
class MilestoneUpdate:
    milestone_id: int
    name: str | None = None
    description: str | None = None
    forecast_date: date | None = None
    reason: str | None = None
