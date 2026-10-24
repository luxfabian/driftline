"""(De)serialize UI state kept in ``dcc.Store`` (architecture §9.2).

Stores hold JSON only, so sets become sorted lists and dates ISO strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from driftline.domain.enums import TaskStatus
from driftline.domain.filters import Filter


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


def merge_into_store(store: Mapping[str, Any] | None, changes: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the values of the filter controls on one page to the stored filter.

    Only the fields present in ``changes`` change; the rest is kept, so a page
    that shows fewer controls (e.g. Workload) does not reset the others.
    """
    merged = filter_to_store(filter_from_store(store))
    merged.update({k: v for k, v in changes.items() if k in merged})
    return filter_to_store(filter_from_store(merged))
