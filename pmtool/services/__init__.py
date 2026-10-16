"""Services: business rules R-01..R-14, one transaction per method (architecture §7)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pmtool.clock import Clock
from pmtool.services.baseline_service import BaselineService
from pmtool.services.export_service import ExportService
from pmtool.services.import_service import ImportService
from pmtool.services.milestone_service import MilestoneService
from pmtool.services.settings_service import SettingsService
from pmtool.services.snapshot_service import SnapshotService
from pmtool.services.task_service import TaskService


@dataclass
class Services:
    snapshot: SnapshotService
    tasks: TaskService
    milestones: MilestoneService
    baselines: BaselineService
    settings: SettingsService
    export: ExportService
    importer: ImportService


def build_services(db_path: Path | str, clock: Clock) -> Services:
    return Services(
        snapshot=SnapshotService(db_path, clock),
        tasks=TaskService(db_path, clock),
        milestones=MilestoneService(db_path, clock),
        baselines=BaselineService(db_path, clock),
        settings=SettingsService(db_path, clock),
        export=ExportService(db_path, clock),
        importer=ImportService(db_path, clock),
    )


__all__ = ["Services", "build_services"]
