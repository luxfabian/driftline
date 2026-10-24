"""Base class for service tests: file DB (services open one connection per call)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from driftline.clock import FixedClock
from driftline.db.connection import connect
from driftline.db.migrations import apply_migrations
from driftline.domain.commands import MilestoneCreate, TaskCreate
from driftline.services import build_services
from tests.helpers import T0

D = date.fromisoformat


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        conn = connect(self.db_path)
        apply_migrations(conn)
        conn.close()
        self.clock = FixedClock(T0)
        self.svc = build_services(self.db_path, self.clock)

    def tearDown(self):
        self._tmp.cleanup()

    # --- factories --------------------------------------------------------------

    def make_task(self, **overrides) -> int:
        values = dict(
            title="Write report",
            forecast_start=D("2026-10-12"),
            forecast_end=D("2026-10-16"),
            estimated_effort_h=10.0,
        )
        values.update(overrides)
        return self.svc.tasks.create(TaskCreate(**values))

    def make_milestone(self, **overrides) -> int:
        values = dict(name="Design review", forecast_date=D("2026-11-30"))
        values.update(overrides)
        return self.svc.milestones.create(MilestoneCreate(**values))

    def task(self, task_id: int):
        return self.svc.tasks.detail(task_id).task

    # --- raw database access for assertions ------------------------------------

    def query(self, sql: str, params=()) -> list[dict]:
        conn = connect(self.db_path)
        try:
            return [dict(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()

    def log(self, entity_type: str, entity_id: int, kind: str | None = None) -> list[dict]:
        sql = "SELECT * FROM change_log WHERE entity_type = ? AND entity_id = ?"
        params: list = [entity_type, entity_id]
        if kind:
            sql += " AND change_kind = ?"
            params.append(kind)
        return self.query(sql + " ORDER BY id", params)

    def comments(self, task_id: int) -> list[dict]:
        return self.query("SELECT * FROM comment WHERE task_id = ? ORDER BY id", (task_id,))
