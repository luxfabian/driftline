"""Read model for every view (architecture P5)."""

from __future__ import annotations

from collections import defaultdict
from types import MappingProxyType

from pmtool.domain.enums import EntityType
from pmtool.domain.models import ChangeLogEntry, Snapshot
from pmtool.repo import (
    calendar_repo,
    changelog_repo,
    comment_repo,
    label_repo,
    milestone_repo,
    settings_repo,
    task_repo,
)
from pmtool.services._base import ServiceBase


class SnapshotService(ServiceBase):
    def load(self, include_archived: bool = False) -> Snapshot:
        """One consistent read of everything a view needs."""
        with self._read() as conn:
            conn.execute("BEGIN")  # one read transaction = one consistent view
            try:
                tasks = task_repo.list_all(conn, include_archived)
                milestones = milestone_repo.list_all(conn, include_archived)
                labels = label_repo.list_all(conn)
                settings = settings_repo.get(conn)
                absences = calendar_repo.list_absences(conn)
                holidays = frozenset(h.date for h in calendar_repo.list_holidays(conn))
                reasons = comment_repo.latest_risk_reasons(conn)
                forecast_log = changelog_repo.list_field(
                    conn, EntityType.MILESTONE, "forecast_date"
                )
            finally:
                conn.execute("COMMIT")

        at_risk_ids = {t.id for t in tasks if t.at_risk}
        milestone_ids = {m.id for m in milestones}
        grouped: dict[int, list[ChangeLogEntry]] = defaultdict(list)
        for entry in forecast_log:
            if entry.entity_id in milestone_ids:
                grouped[entry.entity_id].append(entry)

        return Snapshot(
            tasks=tuple(tasks),
            milestones=tuple(milestones),
            labels=tuple(labels),
            settings=settings,
            absences=tuple(absences),
            holidays=holidays,
            risk_reasons=MappingProxyType({k: v for k, v in reasons.items() if k in at_risk_ids}),
            milestone_forecast_log=MappingProxyType({k: tuple(v) for k, v in grouped.items()}),
        )
