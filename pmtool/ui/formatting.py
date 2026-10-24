"""Display helpers shared by pages and components (no Dash imports)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from pmtool.calc.status import is_effort_overrun, is_overdue, is_stale
from pmtool.domain.enums import Priority, TaskStatus
from pmtool.domain.models import Snapshot, Task

AT_RISK_MARK = "⚠"

FLAG_AT_RISK = f"{AT_RISK_MARK} At risk"
FLAG_OVERDUE = "Overdue"
FLAG_STALE = "Stale"
FLAG_OVERRUN = "Effort overrun"
FLAG_DEPENDENCY = "Predecessor late"
FLAG_ARCHIVED = "Archived"


def fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def priority_label(p: Priority | int) -> str:
    p = Priority(int(p))
    return f"{int(p)} {p.label}"


def task_flags(
    t: Task,
    today: date,
    now: datetime,
    stale_after_days: int,
    dependency_warnings: Mapping[int, Sequence[int]],
) -> list[str]:
    """Visual markers of one task, most important first (FUN-04, FUN-07, FUN-12, WL-08)."""
    flags = []
    if t.is_archived:
        flags.append(FLAG_ARCHIVED)
    if t.at_risk:
        flags.append(FLAG_AT_RISK)
    if is_overdue(t, today):
        flags.append(FLAG_OVERDUE)
    if t.id in dependency_warnings:
        flags.append(FLAG_DEPENDENCY)
    if is_stale(t, now, stale_after_days):
        flags.append(FLAG_STALE)
    if is_effort_overrun(t):
        flags.append(FLAG_OVERRUN)
    return flags


def lookups(snap: Snapshot) -> dict[str, Any]:
    """Dropdown data for the LOOKUPS store. Load the snapshot with archived items.

    Archived milestones and tasks are kept so existing links still display, but
    they are marked so the dropdowns can disable them.
    """
    ordered = sorted(snap.labels, key=lambda lb: lb.name.lower())
    return {
        "labels": [lb.name for lb in ordered],
        "label_items": [{"id": lb.id, "name": lb.name} for lb in ordered],
        "milestones": [
            {"id": m.id, "name": m.name, "archived": m.is_archived}
            for m in sorted(snap.milestones, key=lambda m: (m.forecast_date, m.id))
        ],
        "tasks": [
            {"id": t.id, "title": t.title, "archived": t.is_archived}
            for t in sorted(snap.tasks, key=lambda t: t.id)
        ],
    }


def milestone_options(lookup: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [
        {
            "label": m["name"] + (" (archived)" if m["archived"] else ""),
            "value": m["id"],
            "disabled": m["archived"],
        }
        for m in (lookup or {}).get("milestones", [])
    ]


def task_options(
    lookup: Mapping[str, Any] | None, exclude: int | None = None
) -> list[dict[str, Any]]:
    return [
        {
            "label": f"#{t['id']} {t['title']}" + (" (archived)" if t["archived"] else ""),
            "value": t["id"],
            "disabled": t["archived"],
        }
        for t in (lookup or {}).get("tasks", [])
        if t["id"] != exclude
    ]


def label_options(
    lookup: Mapping[str, Any] | None, selected: Sequence[str] | None, typed: str | None
) -> list[dict[str, str]]:
    """Existing labels, the selected ones, and the typed text as a new label (DAT-04).

    Matching is case-insensitive: typing "Work" when "work" exists offers "work".
    """
    names: dict[str, str] = {}
    for name in [*(lookup or {}).get("labels", []), *(selected or [])]:
        names.setdefault(name.strip().lower(), name)
    options = [{"label": n, "value": n} for n in names.values()]
    text = (typed or "").strip()
    if text and text.lower() not in names:
        options.append({"label": f"+ new label “{text}”", "value": text})
    return options


def status_options() -> list[dict[str, str]]:
    return [{"label": s.label, "value": s.value} for s in TaskStatus]


def priority_options(as_text: bool = False) -> list[dict[str, int | str]]:
    """``as_text`` for dbc.Select, which always reports string values."""
    return [
        {"label": priority_label(p), "value": str(int(p)) if as_text else int(p)} for p in Priority
    ]
