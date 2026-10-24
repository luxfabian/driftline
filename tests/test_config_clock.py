from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from pathlib import Path

from driftline.clock import FixedClock, SystemClock
from driftline.config import DEFAULT_DATA_DIR, DEFAULT_PORT, HOST, load_config
from driftline.domain.enums import Priority, TaskStatus
from driftline.domain.models import Task
from driftline.errors import ConfirmationRequired, DomainError, ValidationError
from tests.helpers import T0


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = load_config({})
        self.assertEqual(cfg.data_dir, DEFAULT_DATA_DIR)
        self.assertEqual(cfg.port, DEFAULT_PORT)
        self.assertEqual(cfg.db_path, DEFAULT_DATA_DIR / "driftline.db")
        self.assertEqual(cfg.backup_dir, DEFAULT_DATA_DIR / "backups")
        self.assertEqual(cfg.log_path, DEFAULT_DATA_DIR / "driftline.log")

    def test_env_overrides(self):
        cfg = load_config({"DRIFTLINE_DATA_DIR": "/tmp/x", "DRIFTLINE_PORT": "9000"})
        self.assertEqual(cfg.data_dir, Path("/tmp/x"))
        self.assertEqual(cfg.port, 9000)

    def test_host_is_always_localhost(self):  # [NFR-02]
        self.assertEqual(load_config({"DRIFTLINE_HOST": "0.0.0.0"}).host, "127.0.0.1")
        self.assertEqual(HOST, "127.0.0.1")

    def test_invalid_port(self):
        for bad in ("abc", "0", "70000"):
            with self.assertRaises(ValueError):
                load_config({"DRIFTLINE_PORT": bad})


class ClockTest(unittest.TestCase):
    def test_fixed_clock(self):
        clock = FixedClock(T0)
        self.assertEqual(clock.today(), date(2026, 10, 10))
        clock.advance(days=1, hours=16)
        self.assertEqual(clock.today(), date(2026, 10, 12))

    def test_fixed_clock_rejects_naive(self):
        with self.assertRaises(ValueError):
            FixedClock(datetime(2026, 10, 10, 9, 0))

    def test_system_clock_is_aware(self):
        now = SystemClock().now()
        self.assertIsNotNone(now.utcoffset())
        self.assertEqual(now.microsecond, 0)


class ErrorsAndModelsTest(unittest.TestCase):
    def test_domain_error_carries_code(self):
        err = ValidationError("VAL-01", "End before start")
        self.assertIsInstance(err, DomainError)
        self.assertEqual((err.code, err.message), ("VAL-01", "End before start"))
        self.assertIn("VAL-01", str(err))
        self.assertTrue(issubclass(ConfirmationRequired, DomainError))

    def test_models_are_frozen(self):
        task = Task(
            id=1, title="t", description=None,
            baseline_start=date(2026, 10, 12), baseline_end=date(2026, 10, 16),
            forecast_start=date(2026, 10, 12), forecast_end=date(2026, 10, 16),
            estimated_effort_h=8, remaining_effort_h=8, status=TaskStatus.PLANNED,
            priority=Priority.MEDIUM, at_risk=False, milestone_id=None,
            last_review_at=T0, created_at=T0, updated_at=T0, archived_at=None,
        )  # fmt: skip
        with self.assertRaises(FrozenInstanceError):
            task.title = "x"  # type: ignore[misc]
        self.assertFalse(task.is_archived)
        self.assertEqual(task.label_ids, frozenset())

    def test_enum_labels(self):
        self.assertEqual(TaskStatus.IN_PROGRESS.label, "In progress")
        self.assertEqual(Priority.CRITICAL.label, "Critical")
        self.assertEqual(TaskStatus("done"), TaskStatus.DONE)


if __name__ == "__main__":
    unittest.main()
