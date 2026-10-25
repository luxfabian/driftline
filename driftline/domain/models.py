"""Frozen domain models mirroring data_model_spec §3 (architecture §5.1).

Types: ``date`` for planning dates, timezone-aware ``datetime`` for
timestamps, enums from ``enums.py``, ``bool`` for flags. Conversion from and
to database text happens in the repositories.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType

from driftline.domain.enums import (
    ChangeKind,
    CommentKind,
    EntityType,
    MilestoneStatus,
    Priority,
    TaskStatus,
)

# Fields written to change_log (data_model_spec §3.8) - exactly these, no others.
TASK_LOGGED_FIELDS: tuple[str, ...] = (
    "baseline_start",
    "baseline_end",
    "forecast_start",
    "forecast_end",
    "remaining_effort_h",
    "status",
)
MILESTONE_LOGGED_FIELDS: tuple[str, ...] = (
    "baseline_date",
    "forecast_date",
    "status",
)


@dataclass(frozen=True)
class Task:  # [DAT-01]
    id: int
    title: str
    description: str | None
    baseline_start: date
    baseline_end: date
    forecast_start: date
    forecast_end: date
    estimated_effort_h: float
    remaining_effort_h: float
    status: TaskStatus
    priority: Priority
    at_risk: bool
    milestone_id: int | None
    last_review_at: datetime
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    # Filled by the repository for convenience (architecture §5.1).
    label_ids: frozenset[int] = frozenset()
    predecessor_ids: frozenset[int] = frozenset()

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


@dataclass(frozen=True)
class Milestone:  # [DAT-05]
    id: int
    name: str
    description: str | None
    baseline_date: date
    forecast_date: date
    status: MilestoneStatus
    achieved_date: date | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


@dataclass(frozen=True)
class Label:  # [DAT-04]
    id: int
    name: str
    name_key: str


@dataclass(frozen=True)
class Comment:  # [FUN-03]
    id: int
    task_id: int
    kind: CommentKind
    text: str
    created_at: datetime


@dataclass(frozen=True)
class ChangeLogEntry:  # [DAT-09]
    """One change_log row. ``id`` is None until inserted.

    ``old_value`` / ``new_value`` hold the encoded text form (data_model_spec §3.8).
    """

    entity_type: EntityType
    entity_id: int
    change_kind: ChangeKind
    field: str | None
    old_value: str | None
    new_value: str | None
    reason: str | None
    batch_id: str | None
    changed_at: datetime
    id: int | None = None


@dataclass(frozen=True)
class Settings:  # app_settings, data_model_spec §3.9
    weekly_hours: float = 40.0
    working_weekdays: tuple[int, ...] = (1, 2, 3, 4, 5)  # ISO: Mon = 1 ... Sun = 7
    plannable_fraction: float = 0.65
    default_horizon_weeks: int = 4
    load_green_max: float = 0.85
    load_amber_max: float = 1.00
    stale_after_days: int = 14
    backup_keep_count: int = 10
    top_delayed_n: int = 10
    theme: str = "no309"  # a ColorTheme value [schema version 2]


@dataclass(frozen=True)
class Absence:  # [WL-01]
    id: int
    start_date: date  # inclusive
    end_date: date  # inclusive
    note: str | None = None


@dataclass(frozen=True)
class Holiday:  # [WL-01]
    date: date
    name: str | None = None


@dataclass(frozen=True)
class TaskDetail:
    """Read model for the task detail view (architecture §7.3, FUN-03, FUN-06)."""

    task: Task
    labels: tuple[Label, ...]
    comments: tuple[Comment, ...]  # newest first
    history: tuple[ChangeLogEntry, ...]  # oldest first
    predecessors: tuple[Task, ...]
    successors: tuple[Task, ...]
    risk_reason: str | None  # latest risk_set text while at_risk, else None


def _frozen_mapping(data: Mapping | None = None) -> Mapping:
    return MappingProxyType(dict(data or {}))


@dataclass(frozen=True)
class Snapshot:
    """Immutable read model for one view refresh (architecture P5)."""

    tasks: tuple[Task, ...]  # active only unless include_archived
    milestones: tuple[Milestone, ...]
    labels: tuple[Label, ...]
    settings: Settings
    absences: tuple[Absence, ...]
    holidays: frozenset[date]
    risk_reasons: Mapping[int, str] = field(default_factory=_frozen_mapping)
    # milestone_id -> its change_log entries for field forecast_date (for MTA)
    milestone_forecast_log: Mapping[int, tuple[ChangeLogEntry, ...]] = field(
        default_factory=_frozen_mapping
    )
