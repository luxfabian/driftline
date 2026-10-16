"""Task filter [FUN-09, FUN-10] (data_model_spec §6, architecture §5.3)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pmtool.domain.enums import TaskStatus
from pmtool.domain.models import Task

OPEN_STATUSES = frozenset({TaskStatus.PLANNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED})
SEPARATOR = " · "


@dataclass(frozen=True)
class Filter:
    """Empty sets mean "no restriction". Default: all open tasks."""

    labels: frozenset[int] = frozenset()
    label_mode: Literal["any", "all"] = "any"
    priorities: frozenset[int] = frozenset()
    statuses: frozenset[TaskStatus] = OPEN_STATUSES
    at_risk_only: bool = False
    milestone_ids: frozenset[int] = frozenset()
    date_from: date | None = None
    date_to: date | None = None
    include_archived: bool = False

    def __post_init__(self) -> None:
        if self.label_mode not in ("any", "all"):
            raise ValueError(f"label_mode must be 'any' or 'all', not {self.label_mode!r}")

    @property
    def is_default(self) -> bool:
        return self == Filter()


def matches(t: Task, f: Filter) -> bool:
    if t.archived_at is not None and not f.include_archived:
        return False
    if f.labels:
        hits = f.labels & t.label_ids
        if f.label_mode == "any" and not hits:
            return False
        if f.label_mode == "all" and hits != f.labels:
            return False
    if f.priorities and int(t.priority) not in f.priorities:
        return False
    if f.statuses and t.status not in f.statuses:
        return False
    if f.at_risk_only and not t.at_risk:
        return False
    if f.milestone_ids and t.milestone_id not in f.milestone_ids:
        return False
    # Overlap of [forecast_start, forecast_end] with [date_from, date_to].
    if f.date_from is not None and t.forecast_end < f.date_from:
        return False
    if f.date_to is not None and t.forecast_start > f.date_to:
        return False
    return True


def apply_filter(tasks: Iterable[Task], f: Filter) -> list[Task]:
    return [t for t in tasks if matches(t, f)]


def describe(f: Filter, labels: Mapping[int, str], milestones: Mapping[int, str]) -> str:
    """One-line summary for chart subtitles; "No filter" for the default filter."""
    if f.is_default:
        return "No filter"
    parts: list[str] = []
    if f.labels:
        names = sorted((labels.get(i, f"#{i}") for i in f.labels), key=str.lower)
        parts.append(f"Labels: {', '.join(names)} ({f.label_mode})")
    if f.priorities:
        parts.append(f"Priority: {_ranges(sorted(f.priorities))}")
    if f.statuses != OPEN_STATUSES:
        if not f.statuses or f.statuses == frozenset(TaskStatus):
            parts.append("Status: all")
        else:
            ordered = [s.label for s in TaskStatus if s in f.statuses]
            parts.append(f"Status: {', '.join(ordered)}")
    if f.at_risk_only:
        parts.append("At risk only")
    if f.milestone_ids:
        names = sorted((milestones.get(i, f"#{i}") for i in f.milestone_ids), key=str.lower)
        parts.append(f"Milestones: {', '.join(names)}")
    if f.date_from or f.date_to:
        start = f.date_from.isoformat() if f.date_from else "…"
        end = f.date_to.isoformat() if f.date_to else "…"
        parts.append(f"Dates: {start} – {end}")
    if f.include_archived:
        parts.append("incl. archived")
    return SEPARATOR.join(parts)


def _ranges(values: list[int]) -> str:
    """[1, 2, 4] -> "1–2, 4"."""
    chunks: list[str] = []
    start = prev = values[0]
    for v in values[1:] + [None]:  # type: ignore[list-item]
        if v is not None and v == prev + 1:
            prev = v
            continue
        chunks.append(str(start) if start == prev else f"{start}–{prev}")
        if v is not None:
            start = prev = v
    return ", ".join(chunks)
