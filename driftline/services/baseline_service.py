"""Re-baselining (R-08, SCH-02). Earlier baselines stay readable in change_log."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime

from driftline.domain.enums import ChangeKind, EntityType, MilestoneStatus, TaskStatus
from driftline.domain.models import MILESTONE_LOGGED_FIELDS, TASK_LOGGED_FIELDS
from driftline.errors import NotFound, ValidationError
from driftline.repo import milestone_repo, task_repo
from driftline.services._base import ServiceBase, diff_and_log, new_batch_id, require_text


class BaselineService(ServiceBase):
    def rebaseline_tasks(self, task_ids: Iterable[int], reason: str) -> str:
        """Copy forecast -> baseline for the given active tasks. Returns the batch_id."""
        text = require_text(reason, "R-08", "A reason for re-baselining")
        ids = _ids(task_ids)
        batch_id, now = new_batch_id(), self.clock.now()
        with self._write() as conn:
            for task_id in ids:
                _rebaseline_task(conn, task_id, text, batch_id, now)
        return batch_id

    def rebaseline_milestones(self, milestone_ids: Iterable[int], reason: str) -> str:
        text = require_text(reason, "R-08", "A reason for re-baselining")
        ids = _ids(milestone_ids)
        batch_id, now = new_batch_id(), self.clock.now()
        with self._write() as conn:
            for milestone_id in ids:
                _rebaseline_milestone(conn, milestone_id, text, batch_id, now)
        return batch_id

    def rebaseline_all(self, reason: str) -> str:
        """All active open tasks and all active open milestones, one batch.

        TODO(spec): "all items" is read as open items; done tasks and achieved
        milestones keep their baseline so their final variance stays visible.
        """
        text = require_text(reason, "R-08", "A reason for re-baselining")
        batch_id, now = new_batch_id(), self.clock.now()
        with self._write() as conn:
            for task in task_repo.list_all(conn, include_archived=False):
                if task.status is not TaskStatus.DONE:
                    _rebaseline_task(conn, task.id, text, batch_id, now)
            for ms in milestone_repo.list_all(conn, include_archived=False):
                if ms.status is MilestoneStatus.OPEN:
                    _rebaseline_milestone(conn, ms.id, text, batch_id, now)
        return batch_id


def _ids(values: Iterable[int]) -> list[int]:
    ids = sorted(set(values))
    if not ids:
        raise ValidationError("R-08", "Select at least one item to re-baseline.")
    return ids


def _rebaseline_task(
    conn: sqlite3.Connection, task_id: int, reason: str, batch_id: str, now: datetime
) -> None:
    task = task_repo.get(conn, task_id)
    if task is None:
        raise NotFound("NOT-FOUND", f"Task {task_id} does not exist.")
    if task.is_archived:
        raise ValidationError("DAT-08", f"Task {task_id} is archived. Restore it first.")
    before = {f: getattr(task, f) for f in TASK_LOGGED_FIELDS}
    changes = {"baseline_start": task.forecast_start, "baseline_end": task.forecast_end}
    changes = {k: v for k, v in changes.items() if before[k] != v}
    if not changes:
        return
    diff_and_log(
        conn, EntityType.TASK, task_id, before, changes, TASK_LOGGED_FIELDS,
        ChangeKind.REBASELINE, reason, batch_id, now,
    )  # fmt: skip
    task_repo.update_fields(conn, task_id, {**changes, "updated_at": now})


def _rebaseline_milestone(
    conn: sqlite3.Connection, milestone_id: int, reason: str, batch_id: str, now: datetime
) -> None:
    ms = milestone_repo.get(conn, milestone_id)
    if ms is None:
        raise NotFound("NOT-FOUND", f"Milestone {milestone_id} does not exist.")
    if ms.is_archived:
        raise ValidationError("DAT-08", f"Milestone '{ms.name}' is archived. Restore it first.")
    if ms.baseline_date == ms.forecast_date:
        return
    before = {f: getattr(ms, f) for f in MILESTONE_LOGGED_FIELDS}
    changes = {"baseline_date": ms.forecast_date}
    diff_and_log(
        conn, EntityType.MILESTONE, milestone_id, before, changes, MILESTONE_LOGGED_FIELDS,
        ChangeKind.REBASELINE, reason, batch_id, now,
    )  # fmt: skip
    milestone_repo.update_fields(conn, milestone_id, {**changes, "updated_at": now})
