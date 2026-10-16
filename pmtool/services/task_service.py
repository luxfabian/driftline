"""Task write rules and task detail (architecture §7.3).

Rules: R-01, R-03..R-07, R-10..R-14 and VAL-01..VAL-06 (data_model_spec §4).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any

from pmtool.domain.commands import UNLINK, TaskCreate, TaskUpdate
from pmtool.domain.enums import ChangeKind, CommentKind, EntityType, Priority, TaskStatus
from pmtool.domain.models import TASK_LOGGED_FIELDS, Task, TaskDetail
from pmtool.errors import ConfirmationRequired, NotFound, ValidationError
from pmtool.repo import (
    changelog_repo,
    comment_repo,
    dependency_repo,
    label_repo,
    milestone_repo,
    task_repo,
)
from pmtool.services._base import (
    ServiceBase,
    clean_text,
    diff_and_log,
    log_event,
    new_batch_id,
    require_effort,
    require_text,
)

# Changes to these fields count as a review (R-07).
REVIEW_FIELDS = ("remaining_effort_h", "status", "forecast_start", "forecast_end")
RISK_CLEARED_DEFAULT_TEXT = "Risk cleared."


class TaskService(ServiceBase):
    # --- create / update ---------------------------------------------------------

    def create(self, cmd: TaskCreate) -> int:
        """R-01 (+ R-12 labels, R-13 predecessors)."""
        title = require_text(cmd.title, "DAT-01", "Title")
        _check_dates(cmd.forecast_start, cmd.forecast_end)
        estimated = require_effort(cmd.estimated_effort_h, "Estimated effort")
        priority = _priority(cmd.priority)
        label_names = _clean_label_names(cmd.label_names)
        predecessor_ids = sorted(set(cmd.predecessor_ids))

        now = self.clock.now()
        with self._write() as conn:
            if cmd.milestone_id is not None:
                _require_milestone(conn, cmd.milestone_id)
            _require_tasks_exist(conn, predecessor_ids)

            values: dict[str, Any] = {
                "title": title,
                "description": clean_text(cmd.description),
                "baseline_start": cmd.forecast_start,  # SCH-01
                "baseline_end": cmd.forecast_end,
                "forecast_start": cmd.forecast_start,
                "forecast_end": cmd.forecast_end,
                "estimated_effort_h": estimated,
                "remaining_effort_h": estimated,
                "status": TaskStatus.PLANNED,
                "priority": priority,
                "at_risk": False,
                "milestone_id": cmd.milestone_id,
                "last_review_at": now,
                "created_at": now,
                "updated_at": now,
            }
            task_id = task_repo.insert(conn, values)
            diff_and_log(
                conn, EntityType.TASK, task_id, {}, values, TASK_LOGGED_FIELDS,
                ChangeKind.CREATE, None, new_batch_id(), now,
            )  # fmt: skip
            if label_names:
                ids = [label_repo.get_or_create(conn, n) for n in label_names]
                label_repo.set_task_labels(conn, task_id, ids)
            if predecessor_ids:
                dependency_repo.set_predecessors(conn, task_id, predecessor_ids)
        return task_id

    def update(self, cmd: TaskUpdate, confirmed: bool = False) -> None:
        """R-03, R-04, R-05, R-06 (blocked), R-07, R-14; VAL-01..VAL-03, VAL-06."""
        now = self.clock.now()
        with self._write() as conn:
            task = _get_active(conn, cmd.task_id)
            changes: dict[str, Any] = {}

            if cmd.title is not None:
                changes["title"] = require_text(cmd.title, "DAT-01", "Title")
            if cmd.description is not None:
                changes["description"] = clean_text(cmd.description)

            start = cmd.forecast_start or task.forecast_start
            end = cmd.forecast_end or task.forecast_end
            _check_dates(start, end)
            changes["forecast_start"] = start
            changes["forecast_end"] = end

            if cmd.estimated_effort_h is not None:
                changes["estimated_effort_h"] = require_effort(
                    cmd.estimated_effort_h, "Estimated effort"
                )
            remaining = task.remaining_effort_h
            if cmd.remaining_effort_h is not None:
                remaining = require_effort(cmd.remaining_effort_h, "Remaining effort")
            if cmd.priority is not None:
                changes["priority"] = _priority(cmd.priority)
            if cmd.milestone_id is not None:
                if cmd.milestone_id == UNLINK:
                    changes["milestone_id"] = None
                else:
                    _require_milestone(conn, cmd.milestone_id)
                    changes["milestone_id"] = cmd.milestone_id

            # Status and remaining effort interact (VAL-03). A status equal to the
            # current one counts as "not changed", so a full form can resend it.
            requested = _status(cmd.status) if cmd.status is not None else None
            status_changed = requested is not None and requested != task.status
            status = requested if status_changed else task.status
            blocked_reason = None

            if status_changed and status is TaskStatus.DONE:
                remaining = 0.0  # R-04
            elif task.status is TaskStatus.DONE and not status_changed and remaining > 0:
                if not confirmed:  # R-05
                    raise ConfirmationRequired(
                        "R-05",
                        "This task is done. Setting remaining effort above 0 reopens it "
                        "(status In progress). Continue?",
                    )
                status = TaskStatus.IN_PROGRESS
            if status_changed and status is TaskStatus.BLOCKED:  # VAL-06
                blocked_reason = require_text(
                    cmd.status_reason, "VAL-06", "A reason for status Blocked"
                )
            changes["status"] = status
            changes["remaining_effort_h"] = remaining

            changes = {k: v for k, v in changes.items() if getattr(task, k) != v}
            if not changes:
                return
            if any(f in changes for f in REVIEW_FIELDS):
                changes["last_review_at"] = now  # R-07
            changes["updated_at"] = now  # R-14

            task_repo.update_fields(conn, task.id, changes)
            diff_and_log(
                conn, EntityType.TASK, task.id, _logged(task), changes, TASK_LOGGED_FIELDS,
                ChangeKind.EDIT, clean_text(cmd.reason), new_batch_id(), now,
            )  # fmt: skip
            if blocked_reason is not None:
                comment_repo.insert(conn, task.id, CommentKind.BLOCKED, blocked_reason, now)

    # --- labels, dependencies, risk, comments -------------------------------------

    def set_labels(self, task_id: int, label_names: Iterable[str]) -> None:
        """R-12: reuse labels case-insensitively, create missing ones."""
        names = _clean_label_names(label_names)
        now = self.clock.now()
        with self._write() as conn:
            task = _get_active(conn, task_id)
            ids = [label_repo.get_or_create(conn, n) for n in names]
            if set(ids) == set(task.label_ids):
                return
            label_repo.set_task_labels(conn, task_id, ids)
            task_repo.update_fields(conn, task_id, {"updated_at": now})

    def set_predecessors(self, task_id: int, predecessor_ids: Iterable[int]) -> None:
        """R-13 / VAL-05: existing tasks only, no self-reference. Cycles are allowed."""
        ids = sorted(set(predecessor_ids))
        if task_id in ids:
            raise ValidationError("VAL-05", "A task cannot depend on itself.")
        now = self.clock.now()
        with self._write() as conn:
            task = _get_active(conn, task_id)
            _require_tasks_exist(conn, ids)
            if set(ids) == set(task.predecessor_ids):
                return
            dependency_repo.set_predecessors(conn, task_id, ids)
            task_repo.update_fields(conn, task_id, {"updated_at": now})

    def set_at_risk(self, task_id: int, at_risk: bool, reason: str | None = None) -> None:
        """R-06 / VAL-06: setting needs a reason; clearing logs a risk_cleared comment."""
        now = self.clock.now()
        if at_risk:
            text = require_text(reason, "VAL-06", "A reason for the at-risk flag")
        with self._write() as conn:
            task = _get_active(conn, task_id)
            if at_risk:
                comment_repo.insert(conn, task_id, CommentKind.RISK_SET, text, now)
                if not task.at_risk:
                    task_repo.update_fields(conn, task_id, {"at_risk": True, "updated_at": now})
            elif task.at_risk:
                text = clean_text(reason) or RISK_CLEARED_DEFAULT_TEXT
                comment_repo.insert(conn, task_id, CommentKind.RISK_CLEARED, text, now)
                task_repo.update_fields(conn, task_id, {"at_risk": False, "updated_at": now})

    def add_comment(self, task_id: int, text: str) -> int:
        """FUN-03: append-only, timestamped."""
        body = require_text(text, "FUN-03", "Comment")
        now = self.clock.now()
        with self._write() as conn:
            _get_active(conn, task_id)
            return comment_repo.insert(conn, task_id, CommentKind.NOTE, body, now)

    def mark_reviewed(self, task_id: int) -> None:
        """R-07: explicit review without changing data."""
        now = self.clock.now()
        with self._write() as conn:
            _get_active(conn, task_id)
            task_repo.update_fields(conn, task_id, {"last_review_at": now})

    # --- archive / restore / delete ---------------------------------------------

    def archive(self, task_id: int) -> None:
        """R-10. Links (labels, dependencies, milestone) are kept."""
        now = self.clock.now()
        with self._write() as conn:
            task = _get_any(conn, task_id)
            if task.is_archived:
                return
            task_repo.update_fields(conn, task_id, {"archived_at": now, "updated_at": now})
            log_event(conn, EntityType.TASK, task_id, ChangeKind.ARCHIVE, now)

    def restore(self, task_id: int) -> None:
        """R-10."""
        now = self.clock.now()
        with self._write() as conn:
            task = _get_any(conn, task_id)
            if not task.is_archived:
                return
            task_repo.update_fields(conn, task_id, {"archived_at": None, "updated_at": now})
            log_event(conn, EntityType.TASK, task_id, ChangeKind.RESTORE, now)

    def delete_permanently(self, task_id: int, confirmed: bool = False) -> None:
        """R-11: archived tasks only, after confirmation. Removes its history too."""
        with self._write() as conn:
            task = _get_any(conn, task_id)
            if not task.is_archived:
                raise ValidationError("R-11", "Archive the task before deleting it permanently.")
            if not confirmed:
                raise ConfirmationRequired(
                    "R-11",
                    f"Delete task {task_id} '{task.title}' permanently, including its "
                    "comments and history? This cannot be undone.",
                )
            changelog_repo.delete_for_entity(conn, EntityType.TASK, task_id)
            task_repo.delete(conn, task_id)

    # --- read -------------------------------------------------------------------

    def detail(self, task_id: int) -> TaskDetail:
        with self._read() as conn:
            task = _get_any(conn, task_id)
            risk_reason = None
            if task.at_risk:
                risk_reason = comment_repo.latest_risk_reasons(conn).get(task_id)
            return TaskDetail(
                task=task,
                labels=tuple(label_repo.list_for_task(conn, task_id)),
                comments=tuple(comment_repo.list_for_task(conn, task_id)),
                history=tuple(changelog_repo.list_for_entity(conn, EntityType.TASK, task_id)),
                predecessors=tuple(task_repo.get_many(conn, task.predecessor_ids)),
                successors=tuple(
                    task_repo.get_many(conn, dependency_repo.successor_ids(conn, task_id))
                ),
                risk_reason=risk_reason,
            )


# --- module helpers ------------------------------------------------------------


def _get_any(conn: sqlite3.Connection, task_id: int) -> Task:
    task = task_repo.get(conn, task_id)
    if task is None:
        raise NotFound("NOT-FOUND", f"Task {task_id} does not exist.")
    return task


def _get_active(conn: sqlite3.Connection, task_id: int) -> Task:
    task = _get_any(conn, task_id)
    if task.is_archived:
        raise ValidationError("DAT-08", f"Task {task_id} is archived. Restore it first.")
    return task


def _logged(task: Task) -> dict[str, Any]:
    return {f: getattr(task, f) for f in TASK_LOGGED_FIELDS}


def _check_dates(start, end) -> None:  # VAL-01
    if start is None or end is None:
        raise ValidationError("VAL-01", "Start and end date are required.")
    if end < start:
        raise ValidationError("VAL-01", "End date must not be earlier than start date.")


def _priority(value: Any) -> Priority:
    try:
        return Priority(int(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError("DAT-03", "Priority must be 1, 2, 3 or 4.") from exc


def _status(value: Any) -> TaskStatus:
    try:
        return TaskStatus(value)
    except ValueError as exc:
        raise ValidationError("DAT-02", f"Unknown status {value!r}.") from exc


def _clean_label_names(names: Iterable[str]) -> list[str]:
    """Drop blanks and case-insensitive duplicates, keep first spelling."""
    seen: set[str] = set()
    result = []
    for name in names:
        cleaned = clean_text(name)
        if cleaned is None:
            continue
        key = label_repo.name_key(cleaned)
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _require_milestone(conn: sqlite3.Connection, milestone_id: int) -> None:
    if not milestone_repo.existing_ids(conn, [milestone_id]):
        raise NotFound("NOT-FOUND", f"Milestone {milestone_id} does not exist.")


def _require_tasks_exist(conn: sqlite3.Connection, task_ids: list[int]) -> None:  # VAL-05
    missing = sorted(set(task_ids) - task_repo.existing_ids(conn, task_ids))
    if missing:
        raise ValidationError(
            "VAL-05", f"Predecessor task(s) {', '.join(map(str, missing))} do not exist."
        )
