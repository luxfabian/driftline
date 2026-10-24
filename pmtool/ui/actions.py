"""User actions as JSON-serializable dicts, executed against the services.

Every write callback builds an action and runs it through :func:`execute`.
Because an action is plain data, it can wait in the ``PENDING_ACTION`` store
while the confirm modal is open, and is then repeated with ``confirmed=True``
(architecture §9.2). This module has no Dash imports, so it is tested directly.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pmtool.domain.commands import (
    UNLINK,
    MilestoneCreate,
    MilestoneUpdate,
    TaskCreate,
    TaskUpdate,
)
from pmtool.domain.enums import Priority
from pmtool.errors import ConfirmationRequired, DomainError, ValidationError
from pmtool.services import Services
from pmtool.ui.state import parse_date

Action = Mapping[str, Any]


@dataclass(frozen=True)
class Outcome:
    status: Literal["ok", "confirm", "error"]
    message: str
    action: Action | None = None  # the action to repeat after confirmation
    result: Any = None  # e.g. the id of a created task

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def execute(services: Services, action: Action, confirmed: bool = False) -> Outcome:
    """Run one action. Domain errors become an error or confirm outcome, never raise."""
    kind = action.get("kind")
    handler = _HANDLERS.get(kind)
    if handler is None:
        return Outcome("error", f"Unknown action {kind!r}.")
    try:
        message, result = handler(services, action, confirmed)
    except ConfirmationRequired as exc:
        return Outcome("confirm", exc.message, action=dict(action))
    except DomainError as exc:
        return Outcome("error", exc.message)
    return Outcome("ok", message, result=result)


# --- handlers ---------------------------------------------------------------------
# Each returns (success message, result) and may raise DomainError.


def _create_task(services: Services, a: Action, confirmed: bool) -> tuple[str, int]:
    task_id = services.tasks.create(
        TaskCreate(
            title=a.get("title") or "",
            description=a.get("description"),
            forecast_start=parse_date(a.get("forecast_start")),
            forecast_end=parse_date(a.get("forecast_end")),
            estimated_effort_h=_number(a.get("estimated_effort_h"), "Estimated"),
            priority=_priority(a.get("priority")),
            label_names=tuple(a.get("labels") or ()),
            predecessor_ids=tuple(int(i) for i in a.get("predecessor_ids") or ()),
            milestone_id=_optional_int(a.get("milestone_id")),
        )
    )
    return f"Task {task_id} created.", task_id


def _save_task(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    """Full edit form: fields via update (R-05 may ask), then labels."""
    task_id = int(a["task_id"])
    milestone = _optional_int(a.get("milestone_id"))
    estimated = a.get("estimated_effort_h")
    remaining = a.get("remaining_effort_h")
    services.tasks.update(
        TaskUpdate(
            task_id=task_id,
            title=a.get("title") or "",
            description=a.get("description") or "",  # "" clears, None would mean unchanged
            forecast_start=_required_date(a.get("forecast_start")),
            forecast_end=_required_date(a.get("forecast_end")),
            estimated_effort_h=None if estimated is None else _number(estimated, "Estimated"),
            remaining_effort_h=None if remaining is None else _number(remaining, "Remaining"),
            status=a.get("status") or None,
            status_reason=a.get("status_reason"),
            priority=_priority(a.get("priority")),
            milestone_id=UNLINK if milestone is None else milestone,
            reason=a.get("reason"),
        ),
        confirmed=confirmed,
    )
    # TODO(spec): labels are a second transaction; the form saves both with one click.
    if "labels" in a:
        services.tasks.set_labels(task_id, a.get("labels") or ())
    return f"Task {task_id} saved.", None


def _set_predecessors(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    task_id = int(a["task_id"])
    services.tasks.set_predecessors(task_id, [int(i) for i in a.get("predecessor_ids") or ()])
    return f"Dependencies of task {task_id} saved.", None


def _set_risk(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    task_id, at_risk = int(a["task_id"]), bool(a.get("at_risk"))
    services.tasks.set_at_risk(task_id, at_risk, a.get("reason"))
    state = "flagged at risk" if at_risk else "no longer at risk"
    return f"Task {task_id} {state}.", None


def _add_comment(services: Services, a: Action, confirmed: bool) -> tuple[str, int]:
    comment_id = services.tasks.add_comment(int(a["task_id"]), a.get("text") or "")
    return "Comment added.", comment_id


def _mark_reviewed(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    ids = _task_ids(a)
    for task_id in ids:
        services.tasks.mark_reviewed(task_id)
    return f"{_tasks(ids)} marked as reviewed.", None


def _archive(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    ids = _task_ids(a)
    for task_id in ids:
        services.tasks.archive(task_id)
    return f"{_tasks(ids)} archived.", None


def _restore(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    ids = _task_ids(a)
    for task_id in ids:
        services.tasks.restore(task_id)
    return f"{_tasks(ids)} restored.", None


def _rebaseline(services: Services, a: Action, confirmed: bool) -> tuple[str, str]:
    ids = _task_ids(a)
    batch_id = services.baselines.rebaseline_tasks(ids, a.get("reason") or "")
    return f"{_tasks(ids)} re-baselined.", batch_id


def _create_milestone(services: Services, a: Action, confirmed: bool) -> tuple[str, int]:
    milestone_id = services.milestones.create(
        MilestoneCreate(
            name=a.get("name") or "",
            forecast_date=parse_date(a.get("forecast_date")),
            description=a.get("description"),
        )
    )
    return f"Milestone {milestone_id} created.", milestone_id


def _update_milestone(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    milestone_id = int(a["milestone_id"])
    services.milestones.update(
        MilestoneUpdate(
            milestone_id=milestone_id,
            name=a.get("name") or "",
            description=a.get("description") or "",  # "" clears
            forecast_date=_required_date(a.get("forecast_date"), "Forecast date is required."),
            reason=a.get("reason"),
        )
    )
    return f"Milestone {milestone_id} saved.", None


def _achieve_milestone(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    milestone_id = int(a["milestone_id"])
    services.milestones.set_achieved(milestone_id, parse_date(a.get("achieved_date")))
    return f"Milestone {milestone_id} achieved.", None


def _reopen_milestone(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    milestone_id = int(a["milestone_id"])
    services.milestones.reopen(milestone_id)
    return f"Milestone {milestone_id} reopened.", None


def _rebaseline_milestones(services: Services, a: Action, confirmed: bool) -> tuple[str, str]:
    ids = _milestone_ids(a)
    batch_id = services.baselines.rebaseline_milestones(ids, a.get("reason") or "")
    return f"{_milestones(ids)} re-baselined.", batch_id


def _archive_milestones(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    ids = _milestone_ids(a)
    for milestone_id in ids:
        services.milestones.archive(milestone_id)
    return f"{_milestones(ids)} archived.", None


def _restore_milestones(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    ids = _milestone_ids(a)
    for milestone_id in ids:
        services.milestones.restore(milestone_id)
    return f"{_milestones(ids)} restored.", None


def _update_settings(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    services.settings.update(**dict(a.get("values") or {}))
    return "Settings saved.", None


def _add_absence(services: Services, a: Action, confirmed: bool) -> tuple[str, int]:
    absence_id = services.settings.add_absence(
        parse_date(a.get("start_date")), parse_date(a.get("end_date")), a.get("note")
    )
    return "Absence added.", absence_id


def _remove_absence(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    services.settings.remove_absence(int(a["absence_id"]))
    return "Absence removed.", None


def _add_holiday(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    services.settings.add_holiday(parse_date(a.get("date")), a.get("name"))
    return "Holiday added.", None


def _remove_holiday(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    day = _required_date(a.get("date"), "Holiday date is required.")
    services.settings.remove_holiday(day)
    return "Holiday removed.", None


def _delete_task(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    task_id = int(a["task_id"])
    services.tasks.delete_permanently(task_id, confirmed=confirmed)  # R-11 asks first
    return f"Task {task_id} deleted permanently.", None


def _delete_milestone(services: Services, a: Action, confirmed: bool) -> tuple[str, None]:
    milestone_id = int(a["milestone_id"])
    services.milestones.delete_permanently(milestone_id, confirmed=confirmed)  # R-11
    return f"Milestone {milestone_id} deleted permanently.", None


_HANDLERS: dict[str, Callable[[Services, Action, bool], tuple[str, Any]]] = {
    "create_task": _create_task,
    "save_task": _save_task,
    "set_predecessors": _set_predecessors,
    "set_risk": _set_risk,
    "add_comment": _add_comment,
    "mark_reviewed": _mark_reviewed,
    "archive_tasks": _archive,
    "restore_tasks": _restore,
    "rebaseline_tasks": _rebaseline,
    "create_milestone": _create_milestone,
    "update_milestone": _update_milestone,
    "achieve_milestone": _achieve_milestone,
    "reopen_milestone": _reopen_milestone,
    "rebaseline_milestones": _rebaseline_milestones,
    "archive_milestones": _archive_milestones,
    "restore_milestones": _restore_milestones,
    "update_settings": _update_settings,
    "add_absence": _add_absence,
    "remove_absence": _remove_absence,
    "add_holiday": _add_holiday,
    "remove_holiday": _remove_holiday,
    "delete_task": _delete_task,
    "delete_milestone": _delete_milestone,
}


# --- conversion helpers -------------------------------------------------------------


def _task_ids(a: Action) -> list[int]:
    ids = sorted({int(i) for i in a.get("task_ids") or ()})
    if not ids:
        raise ValidationError("UI-01", "Select at least one task.")
    return ids


def _tasks(ids: list[int]) -> str:
    return f"Task {ids[0]}" if len(ids) == 1 else f"{len(ids)} tasks"


def _milestone_ids(a: Action) -> list[int]:
    ids = sorted({int(i) for i in a.get("milestone_ids") or ()})
    if not ids:
        raise ValidationError("UI-01", "Select at least one milestone.")
    return ids


def _milestones(ids: list[int]) -> str:
    return f"Milestone {ids[0]}" if len(ids) == 1 else f"{len(ids)} milestones"


def _required_date(value: Any, message: str = "Start and end date are required."):
    parsed = parse_date(value)
    if parsed is None:
        raise ValidationError("VAL-01", message)
    return parsed


def _number(value: Any, what: str) -> float:
    if value is None or value == "":
        raise ValidationError("VAL-02", f"{what} effort is required.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("VAL-02", f"{what} effort must be a number.") from exc


def _priority(value: Any) -> Priority:
    if value is None or value == "":
        return Priority.MEDIUM
    try:
        return Priority(int(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError("DAT-03", "Priority must be 1, 2, 3 or 4.") from exc


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
