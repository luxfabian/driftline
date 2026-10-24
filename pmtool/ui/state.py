"""(De)serialize UI state kept in ``dcc.Store`` (architecture §9.2).

Stores hold JSON only, so sets become sorted lists and dates ISO strings.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from pmtool.domain.enums import TaskStatus
from pmtool.domain.filters import Filter


def filter_to_store(f: Filter) -> dict[str, Any]:
    return {
        "labels": sorted(f.labels),
        "label_mode": f.label_mode,
        "priorities": sorted(f.priorities),
        "statuses": [s.value for s in TaskStatus if s in f.statuses],
        "at_risk_only": f.at_risk_only,
        "milestone_ids": sorted(f.milestone_ids),
        "date_from": f.date_from.isoformat() if f.date_from else None,
        "date_to": f.date_to.isoformat() if f.date_to else None,
        "include_archived": f.include_archived,
    }


def filter_from_store(data: Mapping[str, Any] | None) -> Filter:
    """Missing or broken values fall back to the default filter field by field."""
    if not data:
        return Filter()
    default = Filter()
    statuses = data.get("statuses")
    return Filter(
        labels=_ints(data.get("labels")),
        label_mode="all" if data.get("label_mode") == "all" else "any",
        priorities=_ints(data.get("priorities")) & {1, 2, 3, 4},
        statuses=(
            default.statuses
            if statuses is None
            else frozenset(TaskStatus(s) for s in statuses if s in set(TaskStatus))
        ),
        at_risk_only=bool(data.get("at_risk_only")),
        milestone_ids=_ints(data.get("milestone_ids")),
        date_from=parse_date(data.get("date_from")),
        date_to=parse_date(data.get("date_to")),
        include_archived=bool(data.get("include_archived")),
    )


def filter_from_controls(
    labels: Iterable[Any] | None,
    label_mode: str | None,
    priorities: Iterable[Any] | None,
    statuses: Iterable[str] | None,
    at_risk_only: bool | None,
    milestone_ids: Iterable[Any] | None,
    date_from: str | None,
    date_to: str | None,
    include_archived: bool | None,
) -> Filter:
    """Filter panel values -> Filter. ``statuses=None`` keeps the default (open)."""
    return filter_from_store(
        {
            "labels": list(labels or []),
            "label_mode": label_mode,
            "priorities": list(priorities or []),
            "statuses": None if statuses is None else list(statuses),
            "at_risk_only": at_risk_only,
            "milestone_ids": list(milestone_ids or []),
            "date_from": date_from,
            "date_to": date_to,
            "include_archived": include_archived,
        }
    )


def parse_date(value: Any) -> date | None:
    """ISO date string (or the date part of an ISO timestamp) -> date; else None."""
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _ints(values: Any) -> frozenset[int]:
    result = set()
    for v in values or []:
        try:
            result.add(int(v))
        except (TypeError, ValueError):
            continue
    return frozenset(result)
