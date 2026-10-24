"""NFR-05: with 500 tasks and 5,000 history entries every view updates in under 2 s.

Architecture §11: snapshot.load + full workload calc + all figure builders must
stay under 1.5 s, leaving margin for rendering in the browser. Each view's
callback work (its own snapshot load + calculations + figures) is also timed
against the same 1.5 s budget. Run only these with ``pytest -m perf``; skip
them with ``pytest -m "not perf"``.
"""

from __future__ import annotations

import random
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path

import pytest

from pmtool.clock import FixedClock
from pmtool.db.connection import connect, transaction
from pmtool.db.migrations import apply_migrations
from pmtool.domain.commands import MilestoneCreate, TaskCreate
from pmtool.domain.enums import ChangeKind, EntityType, Priority
from pmtool.domain.filters import Filter
from pmtool.domain.models import ChangeLogEntry
from pmtool.repo import changelog_repo, dependency_repo
from pmtool.services import build_services
from pmtool.services.task_service import insert_task
from pmtool.ui import charts
from pmtool.ui.formatting import filter_text
from pmtool.ui.pages.dashboard import dashboard_data
from pmtool.ui.pages.milestones import milestone_rows, mta_figure
from pmtool.ui.pages.tasks import task_rows
from pmtool.ui.pages.timeline import timeline_figure
from pmtool.ui.pages.workload import workload_data
from tests.helpers import T0

pytestmark = pytest.mark.perf

N_TASKS = 500
N_LOG_ROWS = 5_000
N_MILESTONES = 20
BUDGET_S = 1.5
LABELS = ("work", "admin", "research", "writing", "teaching", "home", "health", "finance")


class ViewPerformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        db = Path(cls._tmp.name) / "perf.db"
        conn = connect(db)
        apply_migrations(conn)
        conn.close()
        cls.clock = FixedClock(T0)
        cls.svc = build_services(db, cls.clock)
        cls.today = T0.date()
        _fill(cls.svc, db, cls.today)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_data_volume(self):
        snap = self.svc.snapshot.load()
        log_rows = len(self.svc.export.tables()["change_log"])
        self.assertGreaterEqual(len(snap.tasks), N_TASKS)
        self.assertGreaterEqual(log_rows, N_LOG_ROWS)

    def test_load_workload_and_all_builders(self):  # architecture §11
        def work():
            snap = self.svc.snapshot.load()
            f = Filter()
            for group_by in ("priority", "label"):
                data = workload_data(snap, f, self.today, 12, group_by)
                charts.build_cumulative(data.curves, "x")
                charts.build_weekly_load(data.weekly, data.capacity, group_by, "x", data.colors)
            timeline_figure(snap, f, self.today, True)
            mta_figure(snap, f, self.today, None)

        self.assertFaster(work)

    def test_each_view(self):  # NFR-05, per view as its callback does it
        f = Filter()
        views = {
            "dashboard": lambda s: dashboard_data(s, f, self.today, self.clock.now()),
            "tasks": lambda s: task_rows(s, f, self.today, self.clock.now()),
            "timeline": lambda s: timeline_figure(s, f, self.today, True),
            "milestones": lambda s: (milestone_rows(s, f), mta_figure(s, f, self.today, None)),
            "workload": lambda s: workload_data(s, f, self.today, 12, "label"),
        }
        for name, view in views.items():
            with self.subTest(view=name):

                def work(view=view):
                    snap = self.svc.snapshot.load()
                    view(snap)
                    filter_text(snap, f)

                self.assertFaster(work)

    def assertFaster(self, work, budget: float = BUDGET_S) -> None:
        work()  # warm-up (imports, caches)
        best = min(_timed(work) for _ in range(3))
        self.assertLess(best, budget, f"took {best:.2f} s (budget {budget} s)")


def _timed(work) -> float:
    start = time.perf_counter()
    work()
    return time.perf_counter() - start


def _fill(svc, db: Path, today: date) -> None:
    """500 tasks (3,000 create rows) + milestone drift rows up to 5,000 entries."""
    rng = random.Random(7)
    ms_ids = [
        svc.milestones.create(MilestoneCreate(f"Milestone {i}", today + timedelta(days=7 * i)))
        for i in range(1, N_MILESTONES + 1)
    ]
    conn = connect(db)
    try:
        with transaction(conn):
            task_ids: list[int] = []
            for i in range(N_TASKS):
                start = today + timedelta(days=rng.randint(-30, 80))
                cmd = TaskCreate(
                    title=f"Task {i}",
                    forecast_start=start,
                    forecast_end=start + timedelta(days=rng.randint(0, 20)),
                    estimated_effort_h=rng.choice((1, 2, 4, 8, 16)),
                    priority=Priority(rng.randint(1, 4)),
                    label_names=tuple(rng.sample(LABELS, rng.randint(0, 3))),
                    milestone_id=rng.choice([None, *ms_ids]),
                )
                task_ids.append(insert_task(conn, cmd, T0))
            for i in range(1, len(task_ids), 3):  # some dependency chains
                dependency_repo.set_predecessors(conn, task_ids[i], [task_ids[i - 1]])
            existing = conn.execute("SELECT count(*) FROM change_log").fetchone()[0]
            entries = []
            for n in range(max(0, N_LOG_ROWS - existing)):
                ms = ms_ids[n % len(ms_ids)]
                entries.append(
                    ChangeLogEntry(
                        entity_type=EntityType.MILESTONE,
                        entity_id=ms,
                        change_kind=ChangeKind.EDIT,
                        field="forecast_date",
                        old_value=None,
                        new_value=(today + timedelta(days=rng.randint(10, 150))).isoformat(),
                        reason=None,
                        batch_id=None,
                        changed_at=T0 - timedelta(hours=n),
                    )
                )
            changelog_repo.insert_many(conn, entries)
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
