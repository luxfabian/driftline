"""Per-task status flags (data_model_spec §5)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta

from pmtool.domain.enums import TaskStatus
from pmtool.domain.models import Task


def is_open(t: Task) -> bool:
    """Active and not done."""
    return t.archived_at is None and t.status is not TaskStatus.DONE


def is_overdue(t: Task, today: date) -> bool:  # [FUN-12]
    return is_open(t) and t.forecast_end < today


def is_stale(t: Task, now: datetime, stale_after_days: int) -> bool:  # [WL-08]
    """Open and not reviewed for more than ``stale_after_days`` days."""
    return is_open(t) and (now - t.last_review_at) > timedelta(days=stale_after_days)


def is_effort_overrun(t: Task) -> bool:  # [VAL-04]
    return t.remaining_effort_h > t.estimated_effort_h


def current_risk_reason(t: Task, risk_reasons: Mapping[int, str]) -> str | None:  # [FUN-04]
    return risk_reasons.get(t.id) if t.at_risk else None
