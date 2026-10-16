"""Milestone write rules (architecture §7.3): R-02, R-03, R-09, R-10, R-11, R-14."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from pmtool.domain.commands import MilestoneCreate, MilestoneUpdate
from pmtool.domain.enums import ChangeKind, EntityType, MilestoneStatus
from pmtool.domain.models import MILESTONE_LOGGED_FIELDS, Milestone
from pmtool.errors import ConfirmationRequired, NotFound, ValidationError
from pmtool.repo import changelog_repo, milestone_repo
from pmtool.services._base import (
    ServiceBase,
    clean_text,
    diff_and_log,
    log_event,
    new_batch_id,
    require_text,
)


class MilestoneService(ServiceBase):
    def create(self, cmd: MilestoneCreate) -> int:
        """R-02: baseline = forecast; log create rows."""
        name = require_text(cmd.name, "DAT-05", "Name")
        if cmd.forecast_date is None:
            raise ValidationError("DAT-05", "Forecast date is required.")
        now = self.clock.now()
        values: dict[str, Any] = {
            "name": name,
            "description": clean_text(cmd.description),
            "baseline_date": cmd.forecast_date,
            "forecast_date": cmd.forecast_date,
            "status": MilestoneStatus.OPEN,
            "achieved_date": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._write() as conn:
            milestone_id = milestone_repo.insert(conn, values)
            diff_and_log(
                conn, EntityType.MILESTONE, milestone_id, {}, values, MILESTONE_LOGGED_FIELDS,
                ChangeKind.CREATE, None, new_batch_id(), now,
            )  # fmt: skip
        return milestone_id

    def update(self, cmd: MilestoneUpdate) -> None:
        """R-03, R-14. The forecast of an achieved milestone is fixed (R-09)."""
        now = self.clock.now()
        with self._write() as conn:
            ms = _get_active(conn, cmd.milestone_id)
            changes: dict[str, Any] = {}
            if cmd.name is not None:
                changes["name"] = require_text(cmd.name, "DAT-05", "Name")
            if cmd.description is not None:
                changes["description"] = clean_text(cmd.description)
            if cmd.forecast_date is not None and cmd.forecast_date != ms.forecast_date:
                if ms.status is MilestoneStatus.ACHIEVED:
                    raise ValidationError(
                        "R-09",
                        "An achieved milestone's forecast equals its achieved date. "
                        "Reopen it to change the forecast.",
                    )
                changes["forecast_date"] = cmd.forecast_date
            changes = {k: v for k, v in changes.items() if getattr(ms, k) != v}
            if not changes:
                return
            changes["updated_at"] = now
            self._apply(conn, ms, changes, clean_text(cmd.reason), now)

    def set_achieved(self, milestone_id: int, achieved_date: date | None = None) -> None:
        """R-09: status achieved, achieved_date (default today), forecast = achieved."""
        now = self.clock.now()
        day = achieved_date or self.clock.today()
        with self._write() as conn:
            ms = _get_active(conn, milestone_id)
            changes = {
                "status": MilestoneStatus.ACHIEVED,
                "achieved_date": day,
                "forecast_date": day,
            }
            changes = {k: v for k, v in changes.items() if getattr(ms, k) != v}
            if not changes:
                return
            changes["updated_at"] = now
            self._apply(conn, ms, changes, None, now)

    def reopen(self, milestone_id: int) -> None:
        """R-09: back to open, achieved_date cleared, forecast kept."""
        now = self.clock.now()
        with self._write() as conn:
            ms = _get_active(conn, milestone_id)
            if ms.status is MilestoneStatus.OPEN:
                return
            changes = {"status": MilestoneStatus.OPEN, "achieved_date": None, "updated_at": now}
            self._apply(conn, ms, changes, None, now)

    def archive(self, milestone_id: int) -> None:
        """R-10. Linked tasks are NOT archived."""
        now = self.clock.now()
        with self._write() as conn:
            ms = _get_any(conn, milestone_id)
            if ms.is_archived:
                return
            milestone_repo.update_fields(
                conn, milestone_id, {"archived_at": now, "updated_at": now}
            )
            log_event(conn, EntityType.MILESTONE, milestone_id, ChangeKind.ARCHIVE, now)

    def restore(self, milestone_id: int) -> None:
        """R-10."""
        now = self.clock.now()
        with self._write() as conn:
            ms = _get_any(conn, milestone_id)
            if not ms.is_archived:
                return
            milestone_repo.update_fields(
                conn, milestone_id, {"archived_at": None, "updated_at": now}
            )
            log_event(conn, EntityType.MILESTONE, milestone_id, ChangeKind.RESTORE, now)

    def delete_permanently(self, milestone_id: int, confirmed: bool = False) -> None:
        """R-11. Linked tasks lose the link (ON DELETE SET NULL)."""
        with self._write() as conn:
            ms = _get_any(conn, milestone_id)
            if not ms.is_archived:
                raise ValidationError(
                    "R-11", "Archive the milestone before deleting it permanently."
                )
            if not confirmed:
                raise ConfirmationRequired(
                    "R-11",
                    f"Delete milestone '{ms.name}' permanently, including its history? "
                    "Linked tasks keep existing but lose the link. This cannot be undone.",
                )
            changelog_repo.delete_for_entity(conn, EntityType.MILESTONE, milestone_id)
            milestone_repo.delete(conn, milestone_id)

    def get(self, milestone_id: int) -> Milestone:
        with self._read() as conn:
            return _get_any(conn, milestone_id)

    def _apply(
        self,
        conn: sqlite3.Connection,
        ms: Milestone,
        changes: dict[str, Any],
        reason: str | None,
        now,
    ) -> None:
        milestone_repo.update_fields(conn, ms.id, changes)
        before = {f: getattr(ms, f) for f in MILESTONE_LOGGED_FIELDS}
        diff_and_log(
            conn, EntityType.MILESTONE, ms.id, before, changes, MILESTONE_LOGGED_FIELDS,
            ChangeKind.EDIT, reason, new_batch_id(), now,
        )  # fmt: skip


def _get_any(conn: sqlite3.Connection, milestone_id: int) -> Milestone:
    ms = milestone_repo.get(conn, milestone_id)
    if ms is None:
        raise NotFound("NOT-FOUND", f"Milestone {milestone_id} does not exist.")
    return ms


def _get_active(conn: sqlite3.Connection, milestone_id: int) -> Milestone:
    ms = _get_any(conn, milestone_id)
    if ms.is_archived:
        raise ValidationError("DAT-08", f"Milestone '{ms.name}' is archived. Restore it first.")
    return ms
